"""ConfigManager — Python port of managers/configManager.js.

The original read Vite-baked `import.meta.env.VITE_*` values. Here we fetch the
same values from the Python backend's /api/config endpoint (which exposes the
server's VITE_* environment), then parse them identically.
"""

import json

from js import window
from pyodide.http import pyfetch


class ConfigManager:
    def __init__(self):
        self.env = {}

    async def load(self):
        try:
            resp = await pyfetch("/api/config")
            text = await resp.string()
            self.env = json.loads(text)
        except Exception as e:  # noqa: BLE001
            print(f"ConfigManager: failed to load /api/config: {e}")
            self.env = {}
        return self.env

    def _get(self, key, default=""):
        val = self.env.get(key)
        return default if val is None else val

    def get_api_key(self):
        return self._get("VITE_API_KEY", "")

    def get_model(self):
        configured = str(self._get("VITE_GEMINI_LIVE_MODEL", "")).strip()
        return configured or "gemini-3.1-flash-live-preview"

    def get_render_settings(self):
        device_ratio = window.devicePixelRatio or 1
        cap_env = self.parse_number(self._get("VITE_RENDER_PIXEL_RATIO_CAP"), 1)
        pixel_ratio_cap = min(device_ratio, cap_env)
        pixel_ratio_cap = min(pixel_ratio_cap, 2) if pixel_ratio_cap and pixel_ratio_cap > 0 else 1
        return {
            "antialias": self.parse_boolean(self._get("VITE_RENDER_ANTIALIAS"), False),
            "alpha": self.parse_boolean(self._get("VITE_RENDER_ALPHA"), False),
            "shadows": self.parse_boolean(self._get("VITE_RENDER_SHADOWS"), False),
            "powerPreference": self._get("VITE_RENDER_POWER_PREFERENCE", "") or "high-performance",
            "pixelRatioCap": pixel_ratio_cap,
        }

    def get_telegram_settings(self):
        vision_clip = self.parse_number(self._get("VITE_TELEGRAM_VISION_CLIP_SECONDS"), 5, 1, 120)
        vision_interval = self.parse_number(self._get("VITE_TELEGRAM_VISION_INTERVAL_SECONDS"), 5, 1, 300)
        vision_cooldown = self.parse_number(self._get("VITE_TELEGRAM_VISION_COOLDOWN_SECONDS"), 20, 2, 600)
        log_cooldown = self.parse_number(self._get("VITE_TELEGRAM_LOG_COOLDOWN_SECONDS"), 3, 1, 120)
        return {
            "enabled": self.parse_boolean(self._get("VITE_TELEGRAM_ENABLED"), True),
            "relayBaseUrl": str(self._get("VITE_TELEGRAM_RELAY_BASE_URL", "/api/telegram")).strip() or "/api/telegram",
            "chatId": self._get("VITE_TELEGRAM_CHAT_ID", ""),
            "sendVideoClips": self.parse_boolean(self._get("VITE_TELEGRAM_SEND_VIDEO"), False),
            "sendImages": self.parse_boolean(self._get("VITE_TELEGRAM_SEND_IMAGE"), False),
            "sendLogs": self.parse_boolean(self._get("VITE_TELEGRAM_SEND_LOGS"), False),
            "continuousVisionForwarding": self.parse_boolean(
                self._get("VITE_TELEGRAM_CONTINUOUS_VISION_FORWARDING"), True
            ),
            "visionClipMs": round(vision_clip * 1000),
            "visionIntervalMs": round(vision_interval * 1000),
            "visionCooldownMs": round(vision_cooldown * 1000),
            "logCooldownMs": round(log_cooldown * 1000),
            "logTimezone": str(self._get("VITE_TELEGRAM_LOG_TIMEZONE", "Asia/Tashkent")).strip(),
        }

    @staticmethod
    def parse_boolean(value, fallback=False):
        if isinstance(value, bool):
            return value
        if not isinstance(value, str):
            return fallback
        n = value.strip().lower()
        if n in ("1", "true", "yes", "on"):
            return True
        if n in ("0", "false", "no", "off"):
            return False
        return fallback

    @staticmethod
    def parse_number(value, fallback, lo=float("-inf"), hi=float("inf")):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return fallback
        if parsed != parsed:  # NaN
            return fallback
        if parsed < lo:
            return lo
        if parsed > hi:
            return hi
        return parsed

    # camelCase aliases for orchestrator parity
    getApiKey = get_api_key
    getModel = get_model
    getRenderSettings = get_render_settings
    getTelegramSettings = get_telegram_settings
