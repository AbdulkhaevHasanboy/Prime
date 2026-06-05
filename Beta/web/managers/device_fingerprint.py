"""device_fingerprint — Python port of src/utils/deviceFingerprint.js.

Best-effort stable client ID from browser characteristics (navigator, screen,
timezone, canvas fingerprint). Hashing is done in Python (hashlib) instead of
crypto.subtle. Not a security feature.
"""

import hashlib
import random

from js import window, document


async def generate_device_fingerprint():
    try:
        components = []

        nav = window.navigator
        if nav:
            components.append(getattr(nav, "userAgent", "") or "")
            components.append(getattr(nav, "language", "") or "")
            components.append(str(getattr(nav, "hardwareConcurrency", "") or ""))
            components.append(str(getattr(nav, "deviceMemory", "") or ""))
            components.append(getattr(nav, "platform", "") or "")

        screen = window.screen
        if screen:
            components.append(f"{screen.width}x{screen.height}")
            components.append(f"{screen.colorDepth}")
            components.append(f"{screen.pixelDepth}")

        try:
            components.append(window.Intl.DateTimeFormat.new().resolvedOptions().timeZone)
        except Exception:  # noqa: BLE001
            components.append(str(window.Date.new().getTimezoneOffset()))

        try:
            canvas = document.createElement("canvas")
            ctx = canvas.getContext("2d")
            if ctx:
                canvas.width = 200
                canvas.height = 50
                ctx.textBaseline = "top"
                ctx.font = '14px "Arial"'
                ctx.textBaseline = "alphabetic"
                ctx.fillStyle = "#f60"
                ctx.fillRect(125, 1, 62, 20)
                ctx.fillStyle = "#069"
                ctx.fillText("VRM_User_Id_v1", 2, 15)
                ctx.fillStyle = "rgba(102, 204, 0, 0.7)"
                ctx.fillText("VRM_User_Id_v1", 4, 17)
                ctx.globalCompositeOperation = "multiply"
                import math
                two_pi = math.pi * 2
                ctx.fillStyle = "rgb(255,0,255)"
                ctx.beginPath(); ctx.arc(50, 50, 50, 0, two_pi, True); ctx.closePath(); ctx.fill()
                ctx.fillStyle = "rgb(0,255,255)"
                ctx.beginPath(); ctx.arc(100, 50, 50, 0, two_pi, True); ctx.closePath(); ctx.fill()
                ctx.fillStyle = "rgb(255,255,0)"
                ctx.beginPath(); ctx.arc(75, 100, 50, 0, two_pi, True); ctx.closePath(); ctx.fill()
                components.append(canvas.toDataURL())
        except Exception:  # noqa: BLE001
            components.append("canvas-failed")

        joined = "||".join(str(c) for c in components)
        hash_hex = hashlib.sha256(joined.encode("utf-8")).hexdigest()
        return f"usr-{hash_hex[:16]}"
    except Exception as error:  # noqa: BLE001
        print(f"Fingerprint generation failed, falling back to random ID {error}")
        rnd = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(12))
        return f"usr-rnd-{rnd}"
