"""Quantum VRM — Python entry point (runs in the browser via PyScript/Pyodide).

100% Python. Boots the full application UI (ui/app_ui.py), which gates on the
consent dialog, creates the VRM chat system (scene + avatar + animations, driven
through Three.js from Python) and wires every control + Gemini Live voice session.
Three.js is only the WebGL drawing engine, driven from Python.
"""

import asyncio

from js import window, document


def _set_boot(label, sub=None):
    boot = document.getElementById("boot")
    if not boot:
        return
    lab = boot.querySelector(".label")
    if lab:
        lab.textContent = label
    if sub is not None:
        s = boot.querySelector(".sub")
        if s:
            s.textContent = sub


async def main():
    try:
        _set_boot("Loading 3D libraries", "Three.js + three-vrm + Gemini")
        await window.__libsReady  # wait for THREE / three-vrm / GoogleGenAI on window

        # The full UI (ui/app_ui.py) owns its own canvas/loader/HUD, so remove the
        # iteration-1 placeholder elements to avoid them sitting on top of the shell.
        for _id in ("boot", "hud", "app-canvas"):
            el = document.getElementById(_id)
            if el and el.parentNode:
                el.parentNode.removeChild(el)

        from ui.app_ui import start
        await start()
    except Exception as error:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        print(f"❌ Boot error: {error}")
        _set_boot("Boot failed", str(error))
        hud = document.getElementById("hud")
        if hud:
            hud.textContent = f"error: {error}"


asyncio.ensure_future(main())
