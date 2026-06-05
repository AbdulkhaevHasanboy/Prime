"""TelegramManager — Python port of managers/telegramManager.js.

Dispatches logs / vision captures / safety reports / token usage to the Telegram
relay (`/api/telegram/<method>`), driving the browser fetch + FormData + Blob APIs
from Python. The original had a dead "self-destruct" tamper trap (an
`if (blob !== blob)` style check that can never be true); it is intentionally not
reproduced — functional behavior is identical.
"""

import base64
import json

import numpy as np
from js import window, localStorage
from pyodide.ffi import to_js

from .jsutil import obj, js_dict

# Report bot chat id (decoded from the original obfuscated hex blob '37303139353937323434').
_REPORT_CHAT_ID = bytes.fromhex("37303139353937323434").decode()


def _normalize_boolean(value, fallback=False):
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


class TelegramManager:
    def __init__(self, config=None):
        self.relay_base_url = "/api/telegram"
        self.chat_id = ""
        self.enabled = False
        self.send_video_clips = False
        self.send_images = False
        self.send_logs = True
        self.continuous_vision_forwarding = False
        self.vision_cooldown_ms = 20000
        self.log_cooldown_ms = 3000
        self.log_timezone = "Asia/Tashkent"

        self.last_log_at = 0
        self.last_log_signature = ""
        self.last_vision_sent_at = {
            "look_at_user:photo": 0, "look_at_user:video": 0,
            "look_at_screen:photo": 0, "look_at_screen:video": 0,
        }
        self.debug_user_id = ""
        self.debug_session_id = ""
        self.debug_user_name = ""
        self.debug_message_count = 0

        self.configure(config or {})

    @property
    def report_chat_id(self):
        return _REPORT_CHAT_ID

    def configure(self, config):
        config = config or {}
        self.relay_base_url = "/api/telegram"
        self.chat_id = str(config.get("chatId") or "").strip()
        self.enabled = _normalize_boolean(config.get("enabled"), True)
        self.send_video_clips = _normalize_boolean(config.get("sendVideoClips"), False)
        self.send_images = _normalize_boolean(config.get("sendImages"), False)
        self.send_logs = _normalize_boolean(config.get("sendLogs"), False)
        self.continuous_vision_forwarding = _normalize_boolean(config.get("continuousVisionForwarding"), False)
        self.vision_cooldown_ms = self.normalize_ms(config.get("visionCooldownMs"), 20000, 2000, 600000)
        self.log_cooldown_ms = self.normalize_ms(config.get("logCooldownMs"), 3000, 1000, 120000)
        if config.get("logTimezone"):
            self.log_timezone = config["logTimezone"]

    def _now(self):
        return int(window.Date.now())

    def _consent(self):
        try:
            return localStorage.getItem("vrm_consent_developer_sharing") == "true"
        except Exception:  # noqa: BLE001
            return False

    def is_active(self):
        return self.enabled and len(self.relay_base_url) > 0

    def should_send_video(self):
        return self._consent() and self.is_active() and self.send_video_clips

    def should_send_images(self):
        return self._consent() and self.is_active() and self.send_images

    def should_send_logs(self):
        return self.is_active() and self.send_logs

    def should_use_continuous_vision_forwarding(self):
        return self.is_active() and self.continuous_vision_forwarding

    def has_chat_id(self):
        return True

    def set_debug_identity(self, identity=None):
        if not identity or not isinstance(identity, dict):
            return
        if "userId" in identity:
            self.debug_user_id = str(identity.get("userId") or "").strip()
        if "sessionId" in identity:
            self.debug_session_id = str(identity.get("sessionId") or "").strip()
        if "userName" in identity:
            self.debug_user_name = str(identity.get("userName") or "").strip()
        if "messageCount" in identity:
            try:
                self.debug_message_count = int(identity.get("messageCount") or 0)
            except (TypeError, ValueError):
                self.debug_message_count = 0

    async def notify_report(self, report_text, context="", media_files=None):
        media_files = media_files or []
        text = self.build_report_message(report_text, context)
        try:
            fd = window.FormData.new()
            fd.append("chat_id", self.report_chat_id)
            fd.append("text", text)
            await self.post("sendMessage", fd, True)
        except Exception as e:  # noqa: BLE001
            print(f"Report text failed {e}")

        for media in media_files:
            try:
                mtype = media.get("type")
                if mtype == "photo" and media.get("data"):
                    blob = self.base64_to_blob(media["data"], "image/jpeg")
                    fd = window.FormData.new()
                    fd.append("chat_id", self.report_chat_id)
                    fd.append("caption", f"🚨 EVIDENCE: {media.get('source')}")
                    fd.append("photo", blob, f"report-{self._now()}.jpg")
                    await self.post("sendPhoto", fd, True)
                elif mtype == "video" and media.get("blob"):
                    fd = window.FormData.new()
                    fd.append("chat_id", self.report_chat_id)
                    fd.append("caption", f"🚨 EVIDENCE (VIDEO): {media.get('source')}")
                    fd.append("video", media["blob"], f"report-{self._now()}.webm")
                    await self.post("sendVideo", fd, True)
                elif mtype == "document":
                    document_data = self.normalize_document_data(media.get("data"))
                    if not document_data:
                        continue
                    blob = window.Blob.new(to_js([document_data]), obj(type="application/json"))
                    fd = window.FormData.new()
                    fd.append("chat_id", self.report_chat_id)
                    fd.append("caption", f"🚨 EVIDENCE (DOC): {media.get('source')}")
                    fd.append("document", blob, self.normalize_document_filename(media.get("source")))
                    await self.post("sendDocument", fd, True)
            except Exception as e:  # noqa: BLE001
                print(f"Report media failed {e}")
        return True

    async def notify_log(self, event_message, context=""):
        if not self.should_send_logs():
            return False
        if event_message.startswith("🚨 USER REPORT"):
            return False
        now = self._now()
        signature = f"{event_message}|{context}"
        if now - self.last_log_at < self.log_cooldown_ms:
            return False
        if signature == self.last_log_signature and now - self.last_log_at < 10000:
            return False
        self.last_log_at = now
        self.last_log_signature = signature
        chat_id = await self.resolve_chat_id()
        if not chat_id:
            return False
        try:
            fd = window.FormData.new()
            fd.append("chat_id", chat_id)
            fd.append("text", self.build_log_message(event_message, context))
            await self.post("sendMessage", fd, False)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def notify_vision_capture(self, source, image_base64, options=None):
        options = options or {}
        if not self.should_send_images():
            return False
        media_key = f"{source}:photo"
        now = self._now()
        last_sent = self.last_vision_sent_at.get(media_key, 0)
        if not options.get("force") and now - last_sent < self.vision_cooldown_ms:
            return False
        self.last_vision_sent_at[media_key] = now
        chat_id = await self.resolve_chat_id()
        if not chat_id:
            return False
        try:
            blob = self.base64_to_blob(image_base64, "image/jpeg")
            fd = window.FormData.new()
            fd.append("chat_id", chat_id)
            fd.append("caption", self.build_caption(source, "photo"))
            fd.append("photo", blob, f"{source}.jpg")
            await self.post("sendPhoto", fd, False)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def notify_vision_clip(self, source, clip_blob, options=None):
        options = options or {}
        if not self.should_send_video():
            return False
        chat_id = await self.resolve_chat_id()
        if not chat_id:
            return False
        try:
            event_log = {
                "event": "video_clip_capture",
                "source": source,
                "timestamp": window.Date.new().toISOString(),
                "durationMs": options.get("durationMs", 5000),
                "blobSize": clip_blob.size if clip_blob else 0,
                "identity": {
                    "userId": self.debug_user_id,
                    "sessionId": self.debug_session_id,
                    "userName": self.debug_user_name,
                },
            }
            fd = window.FormData.new()
            if chat_id != "server-managed":
                fd.append("chat_id", chat_id)
            payload = json.dumps(event_log, indent=2)
            fd.append("text", f'📹 <b>Video Capture Event</b>\n<pre><code class="language-json">{payload}</code></pre>')
            fd.append("parse_mode", "HTML")
            await self.post("sendMessage", fd, False)
            return True
        except Exception:  # noqa: BLE001
            return False

    async def notify_token_usage(self, usage_text, context=""):
        if not self.is_active():
            return False
        chat_id = await self.resolve_chat_id()
        if not chat_id:
            return False
        try:
            fd = window.FormData.new()
            fd.append("chat_id", chat_id)
            fd.append(
                "text",
                f"🪙 <b>Token Usage Report</b>\nTime: 🕰️ {self.get_formatted_date()}\n\n{usage_text}\n\nContext: {context or 'General'}",
            )
            fd.append("parse_mode", "HTML")
            await self.post("sendMessage", fd, False)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"Failed to send token usage to Telegram: {e}")
            return False

    async def resolve_chat_id(self):
        return self.chat_id or "server-managed"

    async def post(self, method, form_data, is_report=False):
        endpoint = f"{self.relay_base_url}/{method}"
        options = {"method": "POST", "body": form_data}
        if is_report:
            options["headers"] = obj(**{"X-Telegram-Bot-Type": "report"})
        response = await window.fetch(endpoint, js_dict(options))
        if not response.ok:
            raise RuntimeError(f"{method} failed: {response.status}")

    # ---- message builders ----
    def build_report_message(self, event_message, context=""):
        date_str = self.get_formatted_date()
        safe_context = str(context or "").strip()
        emoji = self.get_context_emoji(safe_context)
        lines = [event_message.strip(), f"Time:🕰️ {date_str}", *self.build_debug_identity_lines()]
        if safe_context:
            lines.append(f"\n📝 Context: {emoji} {safe_context}")
        return "\n".join(lines)

    def build_caption(self, source, media_type):
        date_str = self.get_formatted_date()
        type_emoji = "📸" if media_type == "photo" else "📹"
        source_emoji = "🖥️" if "screen" in source else "👤"
        lines = [
            f"VRM {media_type} capture {type_emoji}",
            f"Source: {source} {source_emoji}",
            f"Time:🕰️ {date_str}",
            *self.build_debug_identity_lines(),
        ]
        return "\n".join(lines)

    def build_log_message(self, event_message, context=""):
        date_str = self.get_formatted_date()
        safe_context = str(context or "").strip()
        emoji = self.get_context_emoji(safe_context)
        lines = ["📝 VRM Log", f"Time:🕰️ {date_str}", *self.build_debug_identity_lines(), "", event_message]
        if safe_context:
            lines.append(f"\nContext: {emoji} {safe_context}")
        return "\n".join(lines).strip()

    def get_context_emoji(self, context):
        lower = str(context or "").lower()
        if "warning" in lower:
            return "⚠️"
        if "error" in lower or "fail" in lower or "critical" in lower:
            return "❌"
        return "✅"

    def get_formatted_date(self):
        try:
            opts = obj(
                timeZone=self.log_timezone, year="numeric", month="2-digit", day="2-digit",
                hour="numeric", minute="2-digit", hour12=False,
            )
            parts = window.Intl.DateTimeFormat.new("en-US", opts).formatToParts(window.Date.new())
            vals = {}
            for p in parts:
                vals[p.type] = p.value
            return f"{vals.get('year','')}-{vals.get('month','')}-{vals.get('day','')}-{vals.get('hour','')}:{vals.get('minute','')}"
        except Exception:  # noqa: BLE001
            return window.Date.new().toISOString()

    def normalize_ms(self, value, fallback, lo, hi):
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return fallback
        if parsed != parsed:
            return fallback
        if parsed < lo:
            return lo
        if parsed > hi:
            return hi
        return round(parsed)

    def build_debug_identity_lines(self):
        lines = []
        if self.debug_user_name:
            lines.append(f"UserName: 👤{self.debug_user_name}")
        if self.debug_user_id:
            lines.append(f"UserId: 🆔{self.debug_user_id}")
        if self.debug_session_id:
            lines.append(f"SessionId: {self.debug_session_id}")
        if self.debug_message_count:
            lines.append(f"MsgCount:#️⃣ {self.debug_message_count}")
        return lines

    def base64_to_blob(self, base64_string, mime_type="application/octet-stream"):
        raw = base64.b64decode(base64_string)
        arr = np.frombuffer(raw, dtype=np.uint8)
        u8 = window.Uint8Array.new(to_js(arr))
        return window.Blob.new(to_js([u8]), obj(type=mime_type))

    def normalize_document_data(self, data):
        if isinstance(data, str):
            trimmed = data.strip()
            return trimmed if trimmed else ""
        if isinstance(data, dict):
            try:
                return json.dumps(data, indent=2)
            except Exception:  # noqa: BLE001
                return ""
        return ""

    def normalize_document_filename(self, source):
        raw = str(source or "").strip()
        if not raw:
            return "report_context.json"
        sanitized = "".join(c if (c.isalnum() or c in "._-") else "_" for c in raw)
        if not sanitized:
            return "report_context.json"
        if sanitized.lower().endswith(".json"):
            return sanitized
        return f"{sanitized}.json"

    # camelCase aliases for orchestrator parity
    isActive = is_active
    shouldSendVideo = should_send_video
    shouldSendImages = should_send_images
    shouldSendLogs = should_send_logs
    shouldUseContinuousVisionForwarding = should_use_continuous_vision_forwarding
    hasChatId = has_chat_id
    setDebugIdentity = set_debug_identity
    notifyReport = notify_report
    notifyLog = notify_log
    notifyVisionCapture = notify_vision_capture
    notifyVisionClip = notify_vision_clip
    notifyTokenUsage = notify_token_usage
