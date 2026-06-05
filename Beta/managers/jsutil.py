"""JS interop helpers for driving Three.js from Python (Pyodide).

The browser only runs JavaScript/WASM, so the WebGL renderer is JS. These helpers
make it ergonomic for the Python managers to construct and call into JS objects.
"""

from js import Object, window  # noqa: F401  (window re-exported for convenience)
from pyodide.ffi import to_js, create_proxy  # noqa: F401


def obj(**kwargs):
    """Build a plain JS object from kwargs (not a Map), e.g. obj(antialias=True)."""
    return to_js(kwargs, dict_converter=Object.fromEntries)


def js_dict(mapping):
    """Build a plain JS object from a Python dict."""
    return to_js(mapping, dict_converter=Object.fromEntries)


# Keep created proxies alive for the lifetime of the app so JS callbacks
# (requestAnimationFrame, event listeners, loader plugins) are not GC'd.
_KEEP_ALIVE = []


def proxy(fn):
    """Wrap a Python callable as a persistent JS proxy."""
    p = create_proxy(fn)
    _KEEP_ALIVE.append(p)
    return p
