"""FusionBridge: a minimal local bridge that lets Claude run Fusion API Python
inside the live Fusion session.

Security model:
  * listens on 127.0.0.1 only (never reachable from the network)
  * the Host header must be 127.0.0.1:PORT or localhost:PORT (DNS-rebinding guard)
  * every /eval request must carry the secret from ~/.fusion-bridge-token
    (file mode 0600) as a Bearer token
  * code is executed on Fusion's main thread via a CustomEvent
Stop the add-in in Fusion (Shift+S > Add-Ins > FusionBridge > Stop) to close it.
"""
import contextlib
import io
import json
import os
import secrets
import threading
import traceback
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import adsk.core
import adsk.fusion

HOST = '127.0.0.1'
PORT = 8765
EVENT_ID = 'ClaudeBridgeRunCode'
TOKEN_PATH = os.path.expanduser('~/.fusion-bridge-token')
TIMEOUT = 90
MAX_BODY = 4 * 1024 * 1024          # reject absurd request bodies
ALLOWED_HOSTS = {'127.0.0.1:%d' % PORT, 'localhost:%d' % PORT}   # blocks DNS-rebinding style requests

_app = None
_ui = None
_server = None
_event = None
_handler = None
_token = None
_jobs = {}
_jobs_lock = threading.Lock()


def _load_token():
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH) as f:
            t = f.read().strip()
        if t:
            return t
    t = secrets.token_hex(24)
    fd = os.open(TOKEN_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as f:
        f.write(t)
    return t


class _RunHandler(adsk.core.CustomEventHandler):
    """Runs on Fusion's main thread."""

    def notify(self, args):
        job_id = args.additionalInfo
        with _jobs_lock:
            job = _jobs.get(job_id)
        if job is None:
            return
        buf = io.StringIO()
        try:
            env = {
                'adsk': adsk,
                'app': _app,
                'ui': _ui,
                'design': adsk.fusion.Design.cast(_app.activeProduct),
                'result': None,
            }
            with contextlib.redirect_stdout(buf):
                exec(job['code'], env)
            out = {'ok': True, 'result': env.get('result')}
        except Exception:
            out = {'ok': False, 'error': traceback.format_exc()}
        out['stdout'] = buf.getvalue()
        job['out'] = out
        job['done'].set()


class _Http(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authed(self):
        got = self.headers.get('Authorization', '')
        return secrets.compare_digest(got.encode(), ('Bearer ' + _token).encode())

    def _host_ok(self):
        return self.headers.get('Host', '') in ALLOWED_HOSTS

    def do_GET(self):
        if not self._host_ok():
            return self._send(403, {'ok': False, 'error': 'bad Host header'})
        if self.path == '/ping':
            self._send(200, {'ok': True, 'service': 'fusion-bridge'})
        else:
            self._send(404, {'ok': False, 'error': 'not found'})

    def do_POST(self):
        if not self._host_ok():
            return self._send(403, {'ok': False, 'error': 'bad Host header'})
        if self.path != '/eval':
            return self._send(404, {'ok': False, 'error': 'not found'})
        if not self._authed():
            return self._send(401, {'ok': False, 'error': 'unauthorized'})
        try:
            n = int(self.headers.get('Content-Length', 0))
            if n > MAX_BODY:
                return self._send(413, {'ok': False, 'error': 'request too large'})
            code = json.loads(self.rfile.read(n))['code']
        except Exception:
            return self._send(400, {'ok': False, 'error': 'body must be JSON {"code": "..."}'})
        job_id = uuid.uuid4().hex
        job = {'code': code, 'done': threading.Event(), 'out': None}
        with _jobs_lock:
            _jobs[job_id] = job
        try:
            _app.fireCustomEvent(EVENT_ID, job_id)
            if job['done'].wait(TIMEOUT):
                self._send(200, job['out'])
            else:
                self._send(504, {'ok': False, 'error': 'timed out waiting for Fusion main thread'})
        finally:
            with _jobs_lock:
                _jobs.pop(job_id, None)


def run(context):
    global _app, _ui, _server, _event, _handler, _token
    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface
        _token = _load_token()
        try:
            _app.unregisterCustomEvent(EVENT_ID)
        except Exception:
            pass
        _event = _app.registerCustomEvent(EVENT_ID)
        _handler = _RunHandler()
        _event.add(_handler)
        _server = ThreadingHTTPServer((HOST, PORT), _Http)
        threading.Thread(target=_server.serve_forever, daemon=True).start()
        _app.log('FusionBridge listening on %s:%d' % (HOST, PORT))
    except Exception:
        if _ui:
            _ui.messageBox('FusionBridge failed to start:\n' + traceback.format_exc())


def stop(context):
    global _server
    try:
        if _server:
            _server.shutdown()
            _server.server_close()
            _server = None
        if _event and _handler:
            _event.remove(_handler)
        _app.unregisterCustomEvent(EVENT_ID)
    except Exception:
        pass
