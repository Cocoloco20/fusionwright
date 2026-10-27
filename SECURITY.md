# Security model

fusionwright lets an AI run Python **inside your Fusion session**. That is inherently powerful, so the design goal is: nothing outside your own machine can reach it, and the obvious foot-guns are fenced off.

## The bridge add-in (`addin/FusionBridge.py`)

* Listens on `127.0.0.1:8765` only. It is never reachable from the network.
* `POST /eval` requires `Authorization: Bearer <token>`. The token is created on first run at `~/.fusion-bridge-token` with mode `0600` and compared in constant time. Wrong or missing token returns 401.
* The `Host` header must be `127.0.0.1:8765` or `localhost:8765` (blocks DNS-rebinding style attacks from web pages). Anything else returns 403.
* Request bodies are capped at 4 MiB.
* Code runs on Fusion's main thread with a 90-second timeout.
* Stop it any time in Fusion: `Shift+S` > Add-Ins > FusionBridge > Stop.
* `GET /ping` is unauthenticated and returns only `{"ok": true}`.

## The MCP server

* Talks to the client over stdio (no network listener of its own).
* `fusion_run` refuses code containing file-deletion, subprocess, socket/urllib/requests, or `.save(`/`saveAs(` patterns unless you set `FUSIONWRIGHT_UNSAFE=1`. **This is a safety net, not a sandbox**: a determined or compromised model can find other ways. Do not connect untrusted models or prompts.
* Every `fusion_run` returns a timeline checkpoint; `fusion_rollback` removes later items.
* Nothing is ever saved to the Autodesk cloud by this project. Exports go to local paths you control.
* Tool annotations mark read-only vs destructive tools so clients can ask for approval appropriately.

## Recommendations

* Save your Fusion work before letting an AI drive it.
* Treat `~/.fusion-bridge-token` like a password. Delete it to rotate (the add-in makes a new one on next run).
* Review code in `fusion_run` calls if your client lets you.

## Reporting vulnerabilities

Please open a private security advisory on the GitHub repository rather than a public issue.
