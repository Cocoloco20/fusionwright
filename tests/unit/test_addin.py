"""Exercise the add-in's HTTP layer with a stubbed `adsk` module (no Fusion needed): auth, Host guard,
size cap, and that code really executes and returns `result` / stdout / tracebacks."""
import http.client
import importlib.util
import json
import sys
import threading
import types
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

ADDIN = Path(__file__).resolve().parents[2] / "addin" / "FusionBridge.py"


@pytest.fixture()
def addin():
    adsk = types.ModuleType("adsk")
    core = types.ModuleType("adsk.core")
    fusion = types.ModuleType("adsk.fusion")
    core.CustomEventHandler = type("CustomEventHandler", (), {})
    fusion.Design = types.SimpleNamespace(cast=lambda x: None)
    adsk.core, adsk.fusion = core, fusion
    sys.modules.update({"adsk": adsk, "adsk.core": core, "adsk.fusion": fusion})
    spec = importlib.util.spec_from_file_location("fusionbridge_under_test", ADDIN)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)

    class App:
        activeProduct = None
        def fireCustomEvent(self, _id, job_id):
            m._RunHandler().notify(types.SimpleNamespace(additionalInfo=job_id))

    m._app, m._ui, m._token = App(), None, "secret-token"
    srv = ThreadingHTTPServer(("127.0.0.1", 0), m._Http)
    port = srv.server_address[1]
    m.ALLOWED_HOSTS = {f"127.0.0.1:{port}", f"localhost:{port}"}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield m, port
    srv.shutdown()


def _req(port, method, path, body=None, headers=None):
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    return r.status, json.loads(r.read() or b"{}")


def _eval(port, code, token="secret-token", host=None):
    h = {"Content-Type": "application/json"}
    if token is not None:
        h["Authorization"] = "Bearer " + token
    if host:
        h["Host"] = host
    return _req(port, "POST", "/eval", json.dumps({"code": code}), h)


def test_ping_needs_no_token(addin):
    _, port = addin
    assert _req(port, "GET", "/ping")[0] == 200


def test_eval_requires_correct_token(addin):
    _, port = addin
    assert _eval(port, "result=1", token=None)[0] == 401
    assert _eval(port, "result=1", token="wrong")[0] == 401
    st, body = _eval(port, "result = 6 * 7; print('hi')")
    assert st == 200 and body["ok"] and body["result"] == 42 and body["stdout"] == "hi\n"


def test_errors_come_back_with_traceback(addin):
    _, port = addin
    st, body = _eval(port, "raise ValueError('nope')")
    assert st == 200 and not body["ok"] and "ValueError: nope" in body["error"]


def test_foreign_host_header_is_rejected(addin):
    _, port = addin
    assert _eval(port, "result=1", host="evil.example.com")[0] == 403
    assert _req(port, "GET", "/ping", headers={"Host": "evil.example.com"})[0] == 403


def test_oversized_body_is_rejected(addin):
    m, port = addin
    c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    c.putrequest("POST", "/eval")
    c.putheader("Authorization", "Bearer secret-token")
    c.putheader("Content-Length", str(m.MAX_BODY + 1))
    c.endheaders()
    assert c.getresponse().status == 413
