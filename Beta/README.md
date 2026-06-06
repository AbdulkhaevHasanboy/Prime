# 3d Mentor — Python Edition 🐍🌌

A full rewrite of **`VRM_1`** (a Vue 3 + Three.js/WebGL + Gemini Live app) where **all
application code is Python**, running **in the browser** via **PyScript / Pyodide**
(Python compiled to WebAssembly).

There is no Vue and no JavaScript application code. The UI, the avatar control, the
managers, the Gemini Live client, audio lip-sync, vision, telegram telemetry, memory,
consent and daily-limit logic are **`.py` files that execute in the browser tab.**

> **Why Three.js is still here:** a browser can only execute JavaScript/WASM, and its
> only 3D API is WebGL — there is no Python WebGL or Python VRM library. So Three.js +
> `@pixiv/three-vrm` remain *only as the drawing engine*, loaded from a CDN and **driven
> from Python** via Pyodide interop — exactly the role Vue used to play on top of them.
> Likewise the mic/camera/WebRTC use browser APIs called from Python.

---

## Run

```bash
pip install -r requirements.txt
python server.py                 # http://localhost:5173
python server.py --ssl           # https (needed for camera/mic over a LAN IP)
```
or `./run.sh` (auto-creates a venv). Then open **http://localhost:5173**.

The Python **FastAPI server** (`server.py`) serves the PyScript app from `web/` and
provides the backend the browser needs: `/api/get-token` (Gemini ephemeral token),
`/api/search-image`, `/api/proxy-image`, `/api/telegram/<method>`, and `/api/config`
(exposes the `VITE_*` env the frontend reads). VRM models/animations are served from
`dist/`. Config comes from `.env` (copied from VRM_1).

---

## Architecture

```
VRM_1_py/
├── server.py                 # FastAPI: serves web/ + all /api/* endpoints (Python)
├── web/
│   ├── index.html            # PyScript boot + exposes THREE / three-vrm / @google/genai on window (esm.sh)
│   ├── pyscript.toml         # Pyodide config: numpy + mounts every .py module
│   ├── main.py               # entry: await libs, then ui.app_ui.start()
│   ├── ui/app_ui.py          # the entire UI (port of Speaking.vue + 7 components) — Python builds the DOM
│   └── managers/             # Python ports of /managers/*.js + /src utils
│       ├── scene_manager.py        (sceneManager.js)
│       ├── vrm_loader.py           (vrmLoader.js)
│       ├── config_manager.py       (configManager.js)
│       ├── audio_manager.py        (audioManager.js — numpy PCM + lip-sync)
│       ├── vision_manager.py       (visionManager.js — camera/screen/clips)
│       ├── telegram_manager.py     (telegramManager.js)
│       ├── animation_manager.py    (animationManager.js — VRMA + 260+ expressions)
│       ├── ai_client.py            (aiClient.js — Gemini Live via @google/genai, driven from Python)
│       ├── orchestrator.py         (index.js createVRMChatSystem — the integration spine)
│       ├── cache_manager.py, speech_manager.py, utils.py
│       ├── device_fingerprint.py   (src/utils/deviceFingerprint.js)
│       ├── i18n.py                 (src/i18n/ui.js — en/uz/ru)
│       └── jsutil.py               (Pyodide↔JS interop helpers)
└── dist/                     # original VRM_1 build — kept ONLY for the .vrm models + .vrma animations
```

Every manager keeps the original public method names (camelCase aliases over snake_case)
so the orchestrator wires them exactly like `index.js` did.

---

## Status & what was verified

Verified in a real (headless Chrome) browser:
- Python boots via PyScript; all 15 manager modules import and instantiate in-runtime.
- The `riko.vrm` avatar loads and renders in 3D, driven entirely by Python.
- The full glassmorphic UI builds: sci-fi loader, HUD, ControlDock, and the
  **Security & Consent Matrix** gate (AI-training required + developer-sharing optional).
- No console/page errors through boot + consent flow.

Needs a **real browser with mic/camera + consent** (cannot be tested headlessly):
- The live Gemini voice session handshake, audio lip-sync against real audio, and
  camera/screen vision capture. All code paths are ported and load cleanly; they require
  the live API + real devices to exercise end-to-end.

---

## Notes on faithful-but-omitted code
- The original `telegramRelay.js` (server) and `telegramManager.js`/`aiClient.js` contained
  **dead "self-destruct"/unreachable fallback branches** (always-false tamper checks that
  delete files / loop forever). These never executed; the destructive branches are
  intentionally **not** reproduced. All functional behavior is identical.

The original VRM_1 README is preserved as [`README.original.md`](./README.original.md).
