"""HTTP client for the FusionBridge add-in (loopback + bearer token)."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

DEFAULT_URL = "http://127.0.0.1:8765"
TOKEN_PATH = Path(os.path.expanduser("~/.fusion-bridge-token"))

HOWTO_START = (
    "Open Fusion, press Shift+S (Scripts and Add-Ins), select the FusionBridge add-in and click Run "
    "(tick 'Run on Startup' to start it automatically)."
)


class FusionError(RuntimeError):
    """An error with a message that tells the caller how to fix it."""


class FusionBridge:
    def __init__(self, url: str | None = None, token_path: Path | None = None):
        self.url = (url or os.environ.get("FUSIONWRIGHT_URL") or DEFAULT_URL).rstrip("/")
        self.token_path = Path(token_path or os.environ.get("FUSIONWRIGHT_TOKEN_FILE") or TOKEN_PATH)

    def _token(self) -> str:
        try:
            return self.token_path.read_text().strip()
        except OSError:
            raise FusionError(f"No bridge token at {self.token_path}. {HOWTO_START} The add-in creates the token on first run.")

    def ping(self) -> dict:
        try:
            with urllib.request.urlopen(self.url + "/ping", timeout=3) as r:
                return json.loads(r.read())
        except Exception as e:  # noqa: BLE001
            raise FusionError(f"Fusion bridge not reachable at {self.url} ({e.__class__.__name__}). {HOWTO_START}")

    def run(self, code: str, timeout: float = 95.0) -> dict:
        """Execute code inside Fusion. Returns {'result': ..., 'stdout': ...}; raises FusionError on failure."""
        req = urllib.request.Request(
            self.url + "/eval", data=json.dumps({"code": code}).encode(),
            headers={"Authorization": "Bearer " + self._token(), "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 401:
                raise FusionError("Bridge rejected the token (401). Delete ~/.fusion-bridge-token, restart the add-in, retry.")
            raise FusionError(f"Bridge HTTP {e.code}: {e.read().decode()[:300]}")
        except Exception as e:  # noqa: BLE001
            raise FusionError(f"Fusion bridge not reachable at {self.url} ({e.__class__.__name__}). {HOWTO_START}")
        if not data.get("ok"):
            err = (data.get("error") or "unknown error").strip().splitlines()
            tail = [ln for ln in err if ln.strip()][-3:]
            raise FusionError("Fusion raised: " + " | ".join(t.strip() for t in tail) +
                              (f"  [stdout: {data['stdout'][-300:]}]" if data.get("stdout") else ""))
        return data
