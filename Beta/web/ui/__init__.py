"""ui — Python DOM UI layer for the Quantum VRM app (PyScript/Pyodide).

The Vue UI (Speaking.vue + components) is ported to plain Python that builds and
updates the DOM directly. The single entry point is :func:`ui.app_ui.start`.
"""

from .app_ui import start

__all__ = ["start"]
