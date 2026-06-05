"""app_ui — Python DOM port of the Vue Speaking.vue app shell + components.

ALL UI is built here by Python creating/updating the DOM directly via the
``js`` interop and ``pyodide.ffi``. The single entry point is :func:`start`,
which constructs the whole UI, gates on the consent dialog, boots the 3D system
via ``managers.orchestrator.create_vrm_chat_system`` and wires every control.

This mirrors the original Vue components:
  * Speaking.vue              -> AppUI (shell, HUD, toasts, drag-drop, flows)
  * SciFiLoader.vue           -> boot/loading overlay
  * ControlDock.vue           -> bottom dock
  * ChatSidebar.vue           -> chat panel
  * SettingsPanel.vue         -> settings panel
  * PersonaManagerDialog.vue  -> persona manager dialog
  * TimerWidget.vue           -> floating timer
  * ConfirmTermsDialog.vue    -> two-stage consent gate

localStorage keys used (same as the Vue app):
  vrm_consent_ai_training, vrm_consent_developer_sharing,
  vrm_daily_limit_left, vrm_daily_limit_date,
  vrm_chat_history, vrm_user_memories, vrm_user_name,
  vrm_avatar_scale, vrm_background_color,
  vrm_look_at_user, vrm_look_at_screen,
  vrm_personas, vrm_selected_persona_id,
  vrm_ui_language (UI_LANGUAGE_STORAGE_KEY), vrm_debug_user_id,
  vrm_selected_model_key
"""

import asyncio
import json
import random

from js import window, document, localStorage, console
from pyodide.ffi import create_proxy  # noqa: F401  (proxy helper below wraps it)

from managers.jsutil import proxy
from managers.orchestrator import create_vrm_chat_system
from managers.cache_manager import cache_manager
from managers.i18n import (
    translate_ui,
    SUPPORTED_LANGUAGES,
    UI_LANGUAGE_STORAGE_KEY,
    resolve_language,
    get_locale_for_language,
    build_ai_runtime_language_hint,
)
from managers.device_fingerprint import generate_device_fingerprint


# --------------------------------------------------------------------------- #
# Constants (ported from Speaking.vue)
# --------------------------------------------------------------------------- #
MAX_CHAT_HISTORY_ITEMS = 12000
ASSISTANT_ACTOR_ID = "assistant-riko"
DEBUG_USER_ID_STORAGE_KEY = "vrm_debug_user_id"
RECONNECT_WINDOW_MS = 180000
RECONNECT_HINT_THRESHOLD = 3
DAILY_LIMIT_MS = 10 * 60 * 1000  # 10 minutes
BACKGROUND_COLOR_STORAGE_KEY = "vrm_background_color"

PERSONAS_STORAGE_KEY = "vrm_personas"
SELECTED_PERSONA_STORAGE_KEY = "vrm_selected_persona_id"
DEFAULT_PERSONA_ID = "persona-default-riko"
BUILTIN_PERSONA_IDS = {
    "default": DEFAULT_PERSONA_ID,
    "mentor": "persona-sample-mentor",
    "reviewer": "persona-sample-reviewer",
    "friend": "persona-sample-friend",
}
BUILTIN_PERSONA_ID_SET = set(BUILTIN_PERSONA_IDS.values())

BUILTIN_PERSONA_LOCALIZED = {
    "en": {
        "default": {"title": "Default Riko", "description": "Original Riko personality used by the app.", "prompt": ""},
        "mentor": {"title": "Calm Mentor", "description": "Patient teacher that explains clearly and keeps a supportive tone.",
                   "prompt": "You are a calm and practical mentor. Explain clearly, avoid drama, and guide the user step-by-step. Be friendly, direct, and solution-focused. Keep answers concise but complete."},
        "reviewer": {"title": "Strict Reviewer", "description": "Direct technical reviewer focused on correctness, risks, and tradeoffs.",
                     "prompt": "You are a strict technical reviewer. Focus on correctness, edge cases, and practical tradeoffs. Point out flaws quickly, propose concrete fixes, and avoid vague advice."},
        "friend": {"title": "Friendly Companion", "description": "Warm, casual, and upbeat conversational style with short responses.",
                   "prompt": "You are a warm and friendly AI companion. Keep a casual tone, use simple language, and give short helpful replies. Be kind and positive while staying useful."},
    },
    "uz": {
        "default": {"title": "Standart Riko", "description": "Ilovadagi asl Riko personasi.", "prompt": ""},
        "mentor": {"title": "Sokin Mentor", "description": "Sabrli o'qituvchi, tushunchalarni aniq tushuntiradi va qo'llab-quvvatlovchi ohangni ushlaydi.",
                   "prompt": "Siz sokin va amaliy mentorsiz. Tushuntirishni aniq bering, dramadan qoching va foydalanuvchini bosqichma-bosqich yo'naltiring. Do'stona, to'g'ridan-to'g'ri va yechimga qaratilgan bo'ling. Javoblarni qisqa, lekin to'liq bering."},
        "reviewer": {"title": "Qattiqqo'l Tekshiruvchi", "description": "To'g'rilik, xavflar va muvozanatlarga e'tibor beradigan to'g'ridan-to'g'ri texnik tekshiruvchi.",
                     "prompt": "Siz qattiqqo'l texnik tekshiruvchisiz. To'g'rilik, chekka holatlar va amaliy muvozanatlarga e'tibor qarating. Kamchiliklarni tez ayting, aniq tuzatishlarni taklif qiling va mavhum maslahatdan qoching."},
        "friend": {"title": "Do'stona Hamroh", "description": "Iliq, erkin va ko'tarinki uslubdagi, qisqa javob beruvchi suhbatdosh.",
                   "prompt": "Siz iliq va do'stona AI hamrohsiz. Erkin ohangni saqlang, sodda tilda yozing va qisqa, foydali javoblar bering. Mehribon va ijobiy bo'ling, lekin amaliy foydani yo'qotmang."},
    },
    "ru": {
        "default": {"title": "Riko по умолчанию", "description": "Оригинальная персона Riko, используемая в приложении.", "prompt": ""},
        "mentor": {"title": "Спокойный Наставник", "description": "Терпеливый учитель, который объясняет понятно и сохраняет поддерживающий тон.",
                   "prompt": "Вы спокойный и практичный наставник. Объясняйте ясно, избегайте лишней драмы и ведите пользователя пошагово. Будьте дружелюбны, прямолинейны и ориентированы на решение. Отвечайте кратко, но полно."},
        "reviewer": {"title": "Строгий Ревьюер", "description": "Прямой технический ревьюер, сфокусированный на корректности, рисках и компромиссах.",
                     "prompt": "Вы строгий технический ревьюер. Сосредотачивайтесь на корректности, пограничных случаях и практических компромиссах. Быстро указывайте на проблемы, предлагайте конкретные исправления и избегайте расплывчатых советов."},
        "friend": {"title": "Дружелюбный Спутник", "description": "Теплый, неформальный и бодрый собеседник с короткими ответами.",
                   "prompt": "Вы теплый и дружелюбный AI-собеседник. Держите разговорный тон, используйте простой язык и давайте короткие полезные ответы. Будьте доброжелательны и позитивны, оставаясь практичными."},
    },
}

BUILTIN_PERSONA_ENGLISH_PROMPTS = {
    BUILTIN_PERSONA_IDS["mentor"]: BUILTIN_PERSONA_LOCALIZED["en"]["mentor"]["prompt"],
    BUILTIN_PERSONA_IDS["reviewer"]: BUILTIN_PERSONA_LOCALIZED["en"]["reviewer"]["prompt"],
    BUILTIN_PERSONA_IDS["friend"]: BUILTIN_PERSONA_LOCALIZED["en"]["friend"]["prompt"],
}

LANGUAGE_LABEL_KEY_BY_CODE = {
    "en": "aiLanguage.english",
    "uz": "aiLanguage.uzbek",
    "ru": "aiLanguage.russian",
}

LOADER_TEXTS = {
    "en": {
        "Booting Engine": "Booting Engine", "Preparing workspace": "Preparing workspace",
        "Preparing managers": "Preparing managers", "Initializing client": "Initializing client",
        "Reading Configuration": "Reading Configuration", "Resolving API and model settings": "Resolving API and model settings",
        "Initializing Scene": "Initializing Scene", "Setting up renderer and camera": "Setting up renderer and camera",
        "Initializing Audio": "Initializing Audio", "Preparing playback pipeline": "Preparing playback pipeline",
        "Initializing Vision": "Initializing Vision", "Preparing camera and capture buffers": "Preparing camera and capture buffers",
        "Loading Avatar": "Loading Avatar", "Trying local model asset": "Trying local model asset",
        "Local model unavailable, trying remote source": "Local model unavailable, trying remote source",
        "Avatar Loaded": "Avatar Loaded", "Preparing animation system": "Preparing animation system",
        "Loading Core Animation": "Loading Core Animation", "Avatar Missing": "Avatar Missing",
        "Default model unavailable. Upload a .vrm file to continue": "Default model unavailable. Upload a .vrm file to continue",
        "Finalizing Scene": "Finalizing Scene", "Starting render loop": "Starting render loop",
        "System Ready": "System Ready", "All subsystems online": "All subsystems online",
        "Avatar online": "Avatar online", "Restored User Avatar": "Restored User Avatar",
        "Upload a VRM model to continue": "Upload a VRM model to continue", "Initialization Failed": "Initialization Failed",
    },
    "uz": {
        "Booting Engine": "Dvigatel ishga tushmoqda", "Preparing workspace": "Ish muhiti tayyorlanmoqda",
        "Preparing managers": "Menejerlar tayyorlanmoqda", "Initializing client": "Mijoz ishga tushirilmoqda",
        "Reading Configuration": "Konfiguratsiya o'qilmoqda", "Resolving API and model settings": "API va model sozlamalari aniqlanmoqda",
        "Initializing Scene": "Sahna ishga tushirilmoqda", "Setting up renderer and camera": "Render va kamera sozlanmoqda",
        "Initializing Audio": "Audio ishga tushirilmoqda", "Preparing playback pipeline": "Ijro pipeline tayyorlanmoqda",
        "Initializing Vision": "Ko'rish tizimi ishga tushirilmoqda", "Preparing camera and capture buffers": "Kamera va capture buferlari tayyorlanmoqda",
        "Loading Avatar": "Avatar yuklanmoqda", "Trying local model asset": "Lokal model fayli tekshirilmoqda",
        "Local model unavailable, trying remote source": "Lokal model topilmadi, masofaviy manba sinovdan o'tmoqda",
        "Avatar Loaded": "Avatar yuklandi", "Preparing animation system": "Animatsiya tizimi tayyorlanmoqda",
        "Loading Core Animation": "Asosiy animatsiyalar yuklanmoqda", "Avatar Missing": "Avatar topilmadi",
        "Default model unavailable. Upload a .vrm file to continue": "Standart model topilmadi. Davom etish uchun .vrm fayl yuklang",
        "Finalizing Scene": "Sahna yakunlanmoqda", "Starting render loop": "Render tsikli ishga tushirilmoqda",
        "System Ready": "Tizim tayyor", "All subsystems online": "Barcha quyi tizimlar faol",
        "Avatar online": "Avatar faol", "Restored User Avatar": "Foydalanuvchi avatari tiklandi",
        "Upload a VRM model to continue": "Davom etish uchun VRM model yuklang", "Initialization Failed": "Ishga tushirish muvaffaqiyatsiz",
    },
    "ru": {
        "Booting Engine": "Запуск движка", "Preparing workspace": "Подготовка рабочего пространства",
        "Preparing managers": "Подготовка менеджеров", "Initializing client": "Инициализация клиента",
        "Reading Configuration": "Чтение конфигурации", "Resolving API and model settings": "Определение настроек API и модели",
        "Initializing Scene": "Инициализация сцены", "Setting up renderer and camera": "Настройка рендера и камеры",
        "Initializing Audio": "Инициализация аудио", "Preparing playback pipeline": "Подготовка аудио-конвейера",
        "Initializing Vision": "Инициализация визуального модуля", "Preparing camera and capture buffers": "Подготовка камеры и буферов захвата",
        "Loading Avatar": "Загрузка аватара", "Trying local model asset": "Пробуем локальную модель",
        "Local model unavailable, trying remote source": "Локальная модель недоступна, пробуем удаленный источник",
        "Avatar Loaded": "Аватар загружен", "Preparing animation system": "Подготовка системы анимации",
        "Loading Core Animation": "Загрузка основных анимаций", "Avatar Missing": "Аватар не найден",
        "Default model unavailable. Upload a .vrm file to continue": "Модель по умолчанию недоступна. Загрузите .vrm файл для продолжения",
        "Finalizing Scene": "Финализация сцены", "Starting render loop": "Запуск цикла рендера",
        "System Ready": "Система готова", "All subsystems online": "Все подсистемы онлайн",
        "Avatar online": "Аватар онлайн", "Restored User Avatar": "Аватар пользователя восстановлен",
        "Upload a VRM model to continue": "Загрузите VRM модель для продолжения", "Initialization Failed": "Ошибка инициализации",
    },
}


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _now():
    return int(window.Date.now())


def _set_timeout(fn, ms):
    return window.setTimeout(proxy(fn), ms)


def _clear_timeout(handle):
    if handle is not None:
        window.clearTimeout(handle)


def _set_interval(fn, ms):
    return window.setInterval(proxy(fn), ms)


def _clear_interval(handle):
    if handle is not None:
        window.clearInterval(handle)


def _ls_get(key, default=None):
    value = localStorage.getItem(key)
    return default if value is None else value


def _ls_set(key, value):
    localStorage.setItem(key, value)


def _create_debug_id(prefix="id"):
    try:
        crypto = getattr(window, "crypto", None)
        uuid = crypto.randomUUID() if crypto and hasattr(crypto, "randomUUID") else None
    except Exception:  # noqa: BLE001
        uuid = None
    if uuid:
        random_part = str(uuid).replace("-", "")[:12]
    else:
        rnd = "".join(random.choice("abcdefghijklmnopqrstuvwxyz0123456789") for _ in range(8))
        random_part = f"{_now():x}{rnd}"
    return f"{prefix}-{random_part}"


def _normalize_hex_color(value, fallback="#111827"):
    raw = value.strip() if isinstance(value, str) else ""
    with_hash = raw if raw.startswith("#") else f"#{raw}"
    if len(with_hash) == 7 and all(c in "0123456789abcdefABCDEF" for c in with_hash[1:]):
        return with_hash.lower()
    return fallback


def _today_str():
    # JS toLocaleDateString('sv') == 'YYYY-MM-DD'
    return window.Date.new().toLocaleDateString("sv")


def _format_remaining_time(ms):
    import math
    total_seconds = max(0, math.ceil(ms / 1000))
    minutes = total_seconds // 60
    seconds = total_seconds % 60
    return f"{minutes}:{seconds:02d}"


def _strip_control_characters(value):
    out = []
    for ch in value:
        code = ord(ch)
        if code in (9, 10, 13) or (code >= 32 and code != 127):
            out.append(ch)
    return "".join(out)


def _sanitize_transcript_text(value):
    if not isinstance(value, str):
        return ""
    import re
    text = _strip_control_characters(value)
    text = re.sub(r"<ctrl\d+>", "", text, flags=re.I)
    text = re.sub(r"<[^>]*ctrl[^>]*>", "", text, flags=re.I)
    text = re.sub(r"<noise>", "", text, flags=re.I)
    text = re.sub(r"<silence>", "", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _sanitize_persona_text(value, max_length):
    normalized = value.strip() if isinstance(value, str) else ""
    if len(normalized) <= max_length:
        return normalized
    return normalized[:max_length].strip()


def _is_builtin_persona_id(persona_id):
    return str(persona_id or "") in BUILTIN_PERSONA_ID_SET


# --------------------------------------------------------------------------- #
# Persona logic (ported from Speaking.vue)
# --------------------------------------------------------------------------- #
def build_builtin_personas(language):
    lang = resolve_language(language)
    localized = BUILTIN_PERSONA_LOCALIZED.get(lang, BUILTIN_PERSONA_LOCALIZED["en"])
    return [
        {"id": BUILTIN_PERSONA_IDS["default"], "title": localized["default"]["title"],
         "description": localized["default"]["description"], "prompt": localized["default"]["prompt"],
         "promptEnglish": "", "isDefault": True, "isBuiltin": True},
        {"id": BUILTIN_PERSONA_IDS["mentor"], "title": localized["mentor"]["title"],
         "description": localized["mentor"]["description"], "prompt": localized["mentor"]["prompt"],
         "promptEnglish": BUILTIN_PERSONA_ENGLISH_PROMPTS[BUILTIN_PERSONA_IDS["mentor"]],
         "isDefault": False, "isBuiltin": True},
        {"id": BUILTIN_PERSONA_IDS["reviewer"], "title": localized["reviewer"]["title"],
         "description": localized["reviewer"]["description"], "prompt": localized["reviewer"]["prompt"],
         "promptEnglish": BUILTIN_PERSONA_ENGLISH_PROMPTS[BUILTIN_PERSONA_IDS["reviewer"]],
         "isDefault": False, "isBuiltin": True},
        {"id": BUILTIN_PERSONA_IDS["friend"], "title": localized["friend"]["title"],
         "description": localized["friend"]["description"], "prompt": localized["friend"]["prompt"],
         "promptEnglish": BUILTIN_PERSONA_ENGLISH_PROMPTS[BUILTIN_PERSONA_IDS["friend"]],
         "isDefault": False, "isBuiltin": True},
    ]


def _normalize_stored_persona(raw):
    if not isinstance(raw, dict):
        return None
    pid = raw.get("id", "")
    pid = pid.strip() if isinstance(pid, str) else ""
    title = _sanitize_persona_text(raw.get("title"), 60)
    description = _sanitize_persona_text(raw.get("description"), 180)
    prompt = _sanitize_persona_text(raw.get("prompt"), 5000)
    if not pid or not title or not description or not prompt:
        return None
    if pid == DEFAULT_PERSONA_ID or _is_builtin_persona_id(pid):
        return None
    return {"id": pid, "title": title, "description": description, "prompt": prompt,
            "isDefault": False, "isBuiltin": False, "promptEnglish": ""}


def merge_builtins_with_custom(custom_personas, language):
    normalized_custom = []
    for item in (custom_personas or []):
        if not item or _is_builtin_persona_id(item.get("id")):
            continue
        normalized_custom.append({**item, "isDefault": False, "isBuiltin": False, "promptEnglish": ""})
    return [*build_builtin_personas(language), *normalized_custom]


def load_personas_from_storage(language):
    try:
        raw = _ls_get(PERSONAS_STORAGE_KEY)
        if not raw:
            return merge_builtins_with_custom([], language)
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            return merge_builtins_with_custom([], language)
        normalized = [p for p in (_normalize_stored_persona(i) for i in parsed)
                      if p and not _is_builtin_persona_id(p["id"])]
        return merge_builtins_with_custom(normalized, language)
    except Exception:  # noqa: BLE001
        return merge_builtins_with_custom([], language)


# --------------------------------------------------------------------------- #
# History helpers (ported from Speaking.vue / main_chat upsert logic)
# --------------------------------------------------------------------------- #
def _trim_history(items):
    if not isinstance(items, list):
        return []
    return items[-MAX_CHAT_HISTORY_ITEMS:]


# --------------------------------------------------------------------------- #
# CSS — glassmorphic dark/indigo theme (ported key styles)
# --------------------------------------------------------------------------- #
APP_CSS = """
:root { --text-primary:#e5e7eb; --text-muted:#9ca3af; }
* { box-sizing:border-box; }
.qv-shell { position:fixed; inset:0; overflow:hidden; user-select:none;
  font-family: system-ui, -apple-system, sans-serif; color:var(--text-primary); }
.qv-backdrop { position:absolute; inset:0; z-index:0;
  background: radial-gradient(circle at 50% 30%, #1e293b 0%, #0b1120 70%, #05070f 100%); }
.qv-vignette { position:absolute; inset:0; z-index:0; pointer-events:none;
  box-shadow: inset 0 0 220px 40px rgba(0,0,0,0.75); }
.qv-canvas { position:absolute; inset:0; z-index:0; display:block; width:100%; height:100%; outline:none; }

.qv-hidden { display:none !important; }
.qv-fade { transition: opacity .4s ease; }

/* boot / loader overlay */
.qv-loader { position:absolute; inset:0; z-index:50; pointer-events:none;
  display:flex; flex-direction:column; align-items:center; justify-content:center; gap:24px;
  background: radial-gradient(circle at center, rgba(6,182,212,0.08) 0%, #030305 90%);
  transition: opacity 1s ease; }
.qv-loader.qv-loader-done { opacity:0; }
.qv-loader-core { width:120px; height:120px; border-radius:50%;
  border:3px solid transparent; border-left-color:#22d3ee; border-right-color:#22d3ee;
  box-shadow:0 0 50px rgba(34,211,238,0.5); animation: qv-spin 1.2s linear infinite; position:relative; }
.qv-loader-core::after { content:''; position:absolute; inset:14px; border-radius:50%;
  border:2px dashed rgba(168,85,247,0.6); animation: qv-spin 2s linear infinite reverse; }
@keyframes qv-spin { to { transform: rotate(360deg); } }
.qv-loader-title { font-family: ui-monospace, monospace; font-weight:900; letter-spacing:.2em;
  font-size: clamp(20px,5vw,42px); color:#fff; text-shadow:0 0 20px rgba(6,182,212,1); }
.qv-loader-barwrap { width:min(420px, calc(100vw - 2rem)); }
.qv-loader-bar { position:relative; height:8px; width:100%; background:rgba(255,255,255,0.06);
  overflow:hidden; border-left:1px solid rgba(34,211,238,0.3); border-right:1px solid rgba(34,211,238,0.3);
  clip-path: polygon(0 0,100% 0,97% 100%,3% 100%); }
.qv-loader-fill { height:100%; width:2%;
  background:linear-gradient(90deg,#22d3ee,#fff,#9333ea); box-shadow:0 0 30px rgba(34,211,238,1);
  transition: width .15s linear; }
.qv-loader-meta { display:flex; justify-content:space-between; font-family:ui-monospace,monospace;
  font-size:10px; color:rgba(103,232,249,0.9); text-transform:uppercase; letter-spacing:.16em; margin-top:8px; }
.qv-loader-detail { font-family:ui-monospace,monospace; font-size:10px; color:rgba(34,211,238,0.8);
  text-transform:uppercase; letter-spacing:.1em; margin-top:6px; border-left:2px solid rgba(34,211,238,0.2); padding-left:10px; }

/* HUD */
.qv-hud-wrap { position:absolute; left:0; top:0; z-index:20; width:100%; padding:16px;
  pointer-events:none; display:flex; align-items:flex-start; justify-content:space-between; gap:12px; }
.qv-hud-panel { pointer-events:auto; background:rgba(0,0,0,0.55); border:1px solid rgba(34,211,238,0.18);
  border-radius:16px; padding:12px 14px; backdrop-filter:blur(14px); }
.qv-dot { display:inline-block; height:10px; width:10px; border-radius:50%; }
.qv-dot-live { background:#f43f5e; box-shadow:0 0 12px rgba(244,63,94,0.8); }
.qv-dot-standby { background:#fbbf24; box-shadow:0 0 12px rgba(251,191,36,0.55); }
.qv-mono { font-family:ui-monospace,monospace; text-transform:uppercase; letter-spacing:.18em; }
.qv-badge { display:inline-flex; align-items:center; border-radius:9999px; padding:4px 10px;
  font-size:10px; font-weight:600; font-family:ui-monospace,monospace; text-transform:uppercase; letter-spacing:.16em; }
.qv-badge-screen { border:1px solid rgba(125,211,252,0.3); background:rgba(56,189,248,0.12); color:#bae6fd; }
.qv-badge-limit { border:1px solid rgba(245,158,11,0.3); background:rgba(245,158,11,0.12); color:#fcd34d;
  box-shadow:0 0 12px rgba(245,158,11,0.2); animation: qv-pulse 1.8s ease-in-out infinite; }
@keyframes qv-pulse { 0%,100%{opacity:1;} 50%{opacity:.5;} }

/* dock */
.qv-dock-wrap { position:absolute; bottom:24px; left:50%; transform:translateX(-50%); z-index:30;
  width:min(680px, calc(100% - 1.5rem)); pointer-events:none; }
.qv-dock { pointer-events:auto; display:flex; align-items:center; justify-content:space-between; gap:12px;
  margin:0 auto; border-radius:22px; background:rgba(0,0,0,0.6); border:1px solid rgba(34,211,238,0.2);
  padding:8px 12px; backdrop-filter:blur(16px); box-shadow:0 4px 30px rgba(0,0,0,0.5); }
.qv-dock-btn { display:flex; align-items:center; justify-content:center; height:40px; width:40px;
  border-radius:12px; background:rgba(255,255,255,0.05); color:rgba(255,255,255,0.5);
  border:none; cursor:pointer; transition:all .2s ease; font-size:18px; }
.qv-dock-btn:hover { background:rgba(255,255,255,0.1); color:#fff; }
.qv-dock-btn.qv-active { background:rgba(34,211,238,0.2); color:#67e8f9; box-shadow:0 0 15px rgba(34,211,238,0.3); }
.qv-dock-btn.qv-active-purple { background:rgba(168,85,247,0.2); color:#c4b5fd; box-shadow:0 0 15px rgba(168,85,247,0.3); }
.qv-dock-btn:disabled { opacity:.5; cursor:not-allowed; }
.qv-dock-call { display:flex; align-items:center; justify-content:center; height:56px; width:56px;
  border-radius:50%; border:2px solid; cursor:pointer; transition:all .3s ease; font-size:22px; background:transparent; }
.qv-call-idle { border-color:rgba(16,185,129,0.5); background:rgba(16,185,129,0.2); color:#6ee7b7;
  box-shadow:0 0 20px rgba(16,185,129,0.4); }
.qv-call-live { border-color:rgba(244,63,94,0.5); background:rgba(244,63,94,0.2); color:#fda4af;
  box-shadow:0 0 20px rgba(244,63,94,0.4); }
.qv-dock-call:disabled { opacity:.5; cursor:not-allowed; border-color:rgba(255,255,255,0.05); background:rgba(255,255,255,0.05); }

/* generic glass panel */
.qv-panel { background:rgba(0,0,0,0.82); border:1px solid rgba(34,211,238,0.2); border-radius:24px;
  backdrop-filter:blur(18px); box-shadow:0 0 40px rgba(0,0,0,0.6); color:var(--text-primary); }
.qv-panel-head { display:flex; align-items:center; justify-content:space-between;
  border-bottom:1px solid rgba(255,255,255,0.06); padding:12px 16px; }
.qv-x { background:none; border:none; color:rgba(255,255,255,0.4); cursor:pointer; font-size:18px; line-height:1; }
.qv-x:hover { color:#fff; }

/* chat */
.qv-chat { position:absolute; top:80px; bottom:96px; right:16px; z-index:30;
  width:min(420px, calc(100% - 1.5rem)); display:flex; flex-direction:column; overflow:hidden; pointer-events:auto; }
.qv-chat-list { flex:1; overflow-y:auto; padding:16px; display:flex; flex-direction:column; gap:18px; }
.qv-msg-row { display:flex; flex-direction:column; }
.qv-msg-row.qv-user { align-items:flex-end; }
.qv-msg-row.qv-model { align-items:flex-start; }
.qv-bubble { max-width:88%; border-radius:16px; border:1px solid; padding:10px 14px; font-size:13px; line-height:1.5; white-space:pre-wrap; word-break:break-word; }
.qv-bubble-user { border-color:rgba(6,182,212,0.3); background:rgba(8,51,68,0.4); color:#cffafe; }
.qv-bubble-model { border-color:rgba(168,85,247,0.2); background:rgba(76,29,149,0.2); color:#e0e7ff; }
.qv-msg-meta { margin-top:6px; display:flex; gap:8px; align-items:center; padding:0 4px;
  font-size:10px; font-family:ui-monospace,monospace; }
.qv-meta-user { color:#22d3ee; } .qv-meta-model { color:#c084fc; } .qv-meta-time { color:rgba(255,255,255,0.3); }
.qv-chat-empty { flex:1; display:flex; flex-direction:column; align-items:center; justify-content:center;
  gap:8px; color:rgba(255,255,255,0.2); font-family:ui-monospace,monospace; text-transform:uppercase; letter-spacing:.16em; font-size:12px; }

/* settings + persona panels */
.qv-settings { position:absolute; bottom:96px; left:50%; transform:translateX(-50%); z-index:30;
  width:min(420px, calc(100% - 1.5rem)); max-height:calc(100vh - 10rem); overflow-y:auto; padding:20px; }
.qv-section { padding-top:16px; border-top:1px solid rgba(255,255,255,0.06); margin-top:16px; }
.qv-label { font-family:ui-monospace,monospace; font-size:10px; text-transform:uppercase; letter-spacing:.15em;
  color:rgba(34,211,238,0.55); margin:0 0 8px 4px; }
.qv-chip { border-radius:6px; background:rgba(8,51,68,0.5); border:1px solid rgba(34,211,238,0.2);
  padding:2px 8px; font-size:10px; font-family:ui-monospace,monospace; color:#67e8f9; }
.qv-card { border:1px solid rgba(255,255,255,0.1); background:rgba(0,0,0,0.35); border-radius:12px; padding:12px; }
.qv-input, .qv-select, .qv-textarea { width:100%; border-radius:8px; border:1px solid rgba(255,255,255,0.1);
  background:rgba(0,0,0,0.4); padding:8px 12px; font-size:12px; color:#fff; outline:none; }
.qv-input:focus, .qv-select:focus, .qv-textarea:focus { border-color:rgba(34,211,238,0.6); }
.qv-range { width:100%; accent-color:#22d3ee; cursor:pointer; }
.qv-color { height:36px; width:48px; cursor:pointer; border-radius:6px; border:1px solid rgba(255,255,255,0.15); background:rgba(0,0,0,0.4); padding:2px; }
.qv-btn { border-radius:10px; border:1px solid rgba(34,211,238,0.3); background:rgba(34,211,238,0.1);
  color:#a5f3fc; font-size:11px; font-weight:600; padding:6px 12px; cursor:pointer; font-family:ui-monospace,monospace; text-transform:uppercase; letter-spacing:.12em; }
.qv-btn:hover { background:rgba(34,211,238,0.2); }
.qv-btn-ghost { border:1px solid rgba(255,255,255,0.1); background:rgba(255,255,255,0.05); color:rgba(255,255,255,0.7); }
.qv-vision-row { display:flex; gap:8px; }
.qv-vision-btn { flex:1; border-radius:12px; border:1px solid rgba(255,255,255,0.05); background:rgba(255,255,255,0.02);
  padding:12px; text-align:left; cursor:pointer; color:rgba(255,255,255,0.3); transition:all .3s ease; }
.qv-vision-btn.qv-on-user { background:rgba(8,51,68,0.3); border-color:rgba(6,182,212,0.4); color:#cffafe; }
.qv-vision-btn.qv-on-screen { background:rgba(76,29,149,0.2); border-color:rgba(168,85,247,0.4); color:#ede9fe; }
.qv-model-row { display:flex; align-items:center; justify-content:space-between; border:1px solid rgba(255,255,255,0.05);
  background:rgba(255,255,255,0.05); border-radius:12px; padding:12px; cursor:pointer; transition:all .2s ease; }
.qv-model-row:hover { background:rgba(8,51,68,0.2); border-color:rgba(34,211,238,0.3); }
.qv-del { background:none; border:none; color:rgba(255,255,255,0.4); cursor:pointer; padding:4px 8px; border-radius:8px; }
.qv-del:hover { background:rgba(244,63,94,0.2); color:#fda4af; }

/* persona dialog */
.qv-persona { position:absolute; top:50%; left:50%; transform:translate(-50%,-50%); z-index:60;
  width:min(680px, calc(100% - 1.5rem)); max-height:calc(100vh - 2rem); display:flex; flex-direction:column;
  overflow:hidden; padding:16px; }
.qv-persona-grid { display:grid; gap:16px; min-height:0; flex:1; overflow-y:auto; }
@media (min-width:760px){ .qv-persona-grid { grid-template-columns:1fr 1fr; } }
.qv-persona-item { border:1px solid rgba(255,255,255,0.05); background:rgba(255,255,255,0.05);
  border-radius:12px; padding:12px; cursor:pointer; transition:all .2s ease; }
.qv-persona-item.qv-selected { border-color:rgba(6,182,212,0.5); background:rgba(8,51,68,0.25); }
.qv-persona-item.qv-locked { opacity:.4; cursor:not-allowed; }

/* overlays / dialogs */
.qv-overlay { position:fixed; inset:0; z-index:100; display:flex; align-items:center; justify-content:center;
  padding:16px; background:rgba(0,0,0,0.75); backdrop-filter:blur(10px); }
.qv-dialog { width:min(500px, calc(100% - 1rem)); max-height:calc(100vh - 4rem); overflow-y:auto;
  border-radius:24px; padding:24px; color:#fff; }
.qv-dialog-cyan { border:1px solid rgba(6,182,212,0.3); background:rgba(2,6,23,0.92); box-shadow:0 0 50px rgba(6,182,212,0.25); }
.qv-dialog-rose { border:1px solid rgba(244,63,94,0.25); background:rgba(2,6,23,0.9); box-shadow:0 24px 60px rgba(0,0,0,0.7); }
.qv-consent-box { border:1px solid rgba(245,158,11,0.2); background:rgba(245,158,11,0.05);
  border-radius:16px; padding:14px; font-size:13px; line-height:1.6; color:rgba(252,211,77,0.9);
  font-family:ui-monospace,monospace; margin-bottom:18px; }
.qv-terms { max-height:200px; overflow-y:auto; border:1px solid rgba(255,255,255,0.1); background:rgba(255,255,255,0.05);
  border-radius:12px; padding:14px; font-size:12px; color:rgba(255,255,255,0.7); line-height:1.6; margin-bottom:18px; }
.qv-consent-opt { display:flex; align-items:flex-start; gap:12px; border:1px solid rgba(255,255,255,0.05);
  background:rgba(255,255,255,0.02); border-radius:12px; padding:12px; cursor:pointer; margin-bottom:14px; }
.qv-consent-opt.qv-checked { background:rgba(8,51,68,0.2); border-color:rgba(6,182,212,0.4); }
.qv-dialog-actions { display:flex; gap:12px; justify-content:flex-end; flex-wrap:wrap; }
.qv-action-primary { border-radius:12px; background:linear-gradient(90deg,#06b6d4,#2563eb); color:#fff;
  border:none; cursor:pointer; padding:10px 20px; font-size:13px; font-weight:600; }
.qv-action-primary:disabled { opacity:.4; cursor:not-allowed; filter:grayscale(1); }
.qv-action-secondary { border-radius:12px; border:1px solid rgba(255,255,255,0.1); background:rgba(255,255,255,0.05);
  color:rgba(255,255,255,0.7); cursor:pointer; padding:10px 16px; font-size:13px; }

/* drag overlay */
.qv-drag { position:absolute; inset:24px; z-index:40; display:flex; align-items:center; justify-content:center;
  border-radius:24px; border:1px solid rgba(34,211,238,0.4); background:rgba(0,0,0,0.8); backdrop-filter:blur(16px); text-align:center; }

/* toasts */
.qv-toasts { position:absolute; right:16px; top:96px; z-index:50; display:flex; flex-direction:column;
  align-items:flex-end; gap:12px; pointer-events:none; }
.qv-toast { pointer-events:auto; display:flex; gap:12px; width:100%; max-width:360px; border-radius:16px;
  border:1px solid rgba(255,255,255,0.1); background:rgba(2,6,23,0.9); backdrop-filter:blur(14px);
  padding:12px 16px; box-shadow:0 10px 30px rgba(0,0,0,0.5); animation: qv-toast-in .25s ease; }
@keyframes qv-toast-in { from { opacity:0; transform:translateX(20px);} to {opacity:1; transform:none;} }
.qv-toast-icon { font-size:16px; line-height:1.4; }
.qv-toast-success .qv-toast-icon { color:#34d399; }
.qv-toast-error .qv-toast-icon { color:#fb7185; }
.qv-toast-warning .qv-toast-icon { color:#fbbf24; }
.qv-toast-info .qv-toast-icon { color:#67e8f9; }
.qv-toast-title { font-size:13px; font-weight:600; color:var(--text-primary); }
.qv-toast-msg { font-size:11px; color:var(--text-muted); margin-top:4px; line-height:1.5; }

/* timer widget */
.qv-timer { position:fixed; z-index:55; pointer-events:auto; cursor:pointer;
  width:min(360px, calc(100vw - 2rem)); transition: all .5s cubic-bezier(.22,1,.36,1); }
.qv-timer.qv-timer-min { width:182px; top:calc(100dvh - 86px); left:16px; transform:scale(.92); }
.qv-timer.qv-timer-exp-pos { top:50%; left:50%; transform:translate(-50%,-50%); }
.qv-timer-shell { border-radius:16px; border:1px solid rgba(34,211,238,0.25); background:rgba(0,0,0,0.55);
  backdrop-filter:blur(16px); box-shadow:0 20px 44px rgba(1,6,16,0.62); padding:10px 12px; display:flex; align-items:center; gap:12px; }
.qv-timer.qv-urgent .qv-timer-shell { border-color:rgba(251,191,36,0.5); }
.qv-timer.qv-expired .qv-timer-shell { border-color:rgba(244,63,94,0.45); background:rgba(244,63,94,0.12); }
.qv-timer-time { font-family:ui-monospace,monospace; font-size:13px; color:rgba(255,255,255,0.9); }
.qv-timer-label { font-size:13px; font-weight:600; color:rgba(255,255,255,0.9); }
.qv-timer-x { height:28px; width:28px; border-radius:10px; border:1px solid rgba(125,157,189,0.28);
  background:rgba(255,255,255,0.06); color:rgba(255,255,255,0.7); font-size:18px; cursor:pointer; }
.qv-timer-expired-overlay { position:absolute; inset:0; z-index:54; pointer-events:none;
  background:rgba(244,63,94,0.15); backdrop-filter:blur(4px); }

.qv-scroll::-webkit-scrollbar { width:5px; }
.qv-scroll::-webkit-scrollbar-thumb { background:rgba(6,182,212,0.25); border-radius:5px; }
"""


# --------------------------------------------------------------------------- #
# AppUI — the application shell (port of Speaking.vue)
# --------------------------------------------------------------------------- #
class AppUI:
    def __init__(self):
        # 3D system + lifecycle
        self.system = None
        self.cleanup_system = None
        self.system_ready = False
        self.is_connected = False
        self.is_connecting = False
        self.is_sharing_screen = False
        self.assistant_speaking = False

        # consent
        self.consent_ai_training = _ls_get("vrm_consent_ai_training") == "true"
        self.consent_dev_sharing = _ls_get("vrm_consent_developer_sharing") == "true"

        # daily session limit
        self.session_time_remaining = 0
        self.session_timer_interval = None

        # settings state
        self.avatar_scale = self._parse_float(_ls_get("vrm_avatar_scale", "2.0"), 2.0)
        self.background_color = _normalize_hex_color(_ls_get(BACKGROUND_COLOR_STORAGE_KEY, "#111827"), "#111827")
        self.look_at_user_enabled = _ls_get("vrm_look_at_user") != "false"
        self.look_at_screen_enabled = _ls_get("vrm_look_at_screen") != "false"
        self.selected_language = resolve_language(_ls_get(UI_LANGUAGE_STORAGE_KEY, "en") or "en")

        # personas
        self.personas = load_personas_from_storage(self.selected_language)
        self.selected_persona_id = _ls_get(SELECTED_PERSONA_STORAGE_KEY) or DEFAULT_PERSONA_ID
        if not any(p["id"] == self.selected_persona_id for p in self.personas):
            self.selected_persona_id = DEFAULT_PERSONA_ID

        # chat history + memories
        self.chat_history = []
        self.active_user_entry_id = None
        self.active_model_entry_id = None
        self._load_history()

        # identity
        self.user_debug_id = _ls_get(DEBUG_USER_ID_STORAGE_KEY, "") or ""
        self.session_debug_id = _create_debug_id("sess")

        # models
        self.available_models = []
        self.selected_model_key = _ls_get("vrm_selected_model_key") or None

        # loader state
        self.loading_state = {"progress": 0, "stage": "Booting Engine", "detail": "Preparing workspace"}

        # toasts
        self.toast_counter = 0

        # reconnect tracking
        self.reconnect_timestamps = []
        self.last_reconnect_hint_at = 0

        # panel visibility
        self.show_chat = False
        self.show_settings = False
        self.show_persona_manager = False

        # drag
        self.drag_depth = 0

        # fps
        self.fps_interval = None

        # timer widget state
        self.timer_visible = False
        self.timer_minimized = True
        self.timer_label = "Timer"
        self.timer_total_ms = 0
        self.timer_end_at_ms = 0
        self.timer_notified = False
        self.timer_expired_overlay = False
        self.pending_timer_start = None
        self.timer_tick_interval = None
        self.timer_auto_minimize_timeout = None
        self.timer_expiry_dismiss_timeout = None
        self.timer_pending_fallback_timeout = None

        # DOM handles (filled in build)
        self.el = {}
        # Persona dialog form state
        self.persona_form_open = False
        self.persona_editing = False
        self.persona_editing_id = ""
        self.persona_draft = {"title": "", "description": "", "prompt": ""}

    # ----------------------------------------------------------------- #
    @staticmethod
    def _parse_float(value, fallback):
        try:
            return float(value)
        except (TypeError, ValueError):
            return fallback

    def t(self, key, params=None):
        return translate_ui(self.selected_language, key, params or {})

    def language_options(self):
        return [{"code": item["code"],
                 "label": self.t(LANGUAGE_LABEL_KEY_BY_CODE.get(item["code"], LANGUAGE_LABEL_KEY_BY_CODE["en"]))}
                for item in SUPPORTED_LANGUAGES]

    def selected_persona(self):
        for p in self.personas:
            if p["id"] == self.selected_persona_id:
                return p
        return self.personas[0] if self.personas else build_builtin_personas(self.selected_language)[0]

    def selected_persona_prompt(self):
        persona = self.selected_persona()
        if not persona or persona.get("isDefault"):
            return ""
        english = _sanitize_persona_text(persona.get("promptEnglish"), 5000)
        if english:
            return english
        return _sanitize_persona_text(persona.get("prompt"), 5000)

    # ----------------------------------------------------------------- #
    # History
    # ----------------------------------------------------------------- #
    def _create_history_entry(self, role, text, overrides=None):
        overrides = overrides or {}
        normalized_role = "user" if role == "user" else "model"
        ts = overrides.get("timestamp")
        try:
            ts = int(ts)
        except (TypeError, ValueError):
            ts = _now()
        actor = overrides.get("actorId")
        if not isinstance(actor, str) or not actor:
            actor = self.user_debug_id if normalized_role == "user" else ASSISTANT_ACTOR_ID
        oid = overrides.get("id")
        return {
            "id": oid if isinstance(oid, str) and oid else _create_debug_id("msg"),
            "role": normalized_role,
            "text": text,
            "timestamp": ts,
            "actorId": actor,
            "userId": overrides.get("userId") if isinstance(overrides.get("userId"), str) and overrides.get("userId") else self.user_debug_id,
            "sessionId": overrides.get("sessionId") if isinstance(overrides.get("sessionId"), str) and overrides.get("sessionId") else self.session_debug_id,
        }

    def _load_history(self):
        try:
            saved = _ls_get("vrm_chat_history")
            if saved:
                items = json.loads(saved)
                normalized = []
                for raw in (items if isinstance(items, list) else []):
                    role = "user" if (isinstance(raw, dict) and raw.get("role") == "user") else "model"
                    text = _sanitize_transcript_text(raw.get("text", "") if isinstance(raw, dict) else "")
                    if not text:
                        continue
                    normalized.append(self._create_history_entry(role, text, raw if isinstance(raw, dict) else {}))
                self.chat_history = _trim_history(normalized)
        except Exception:  # noqa: BLE001
            self.chat_history = []

    def _persist_history(self):
        self.chat_history = _trim_history(self.chat_history)
        _ls_set("vrm_chat_history", json.dumps(self.chat_history))

    def _set_history(self, items):
        self.chat_history = _trim_history(items)
        self._persist_history()
        self._render_chat()

    def _find_entry_index_by_id(self, items, entry_id):
        if not isinstance(entry_id, str) or not entry_id.strip():
            return -1
        for i, item in enumerate(items):
            if item.get("id") == entry_id:
                return i
        return -1

    def _upsert_gemini_transcript(self, items, role, text, is_final):
        normalized_role = "user" if role == "user" else "model"
        active_id = self.active_user_entry_id if normalized_role == "user" else self.active_model_entry_id
        idx = self._find_entry_index_by_id(items, active_id)
        if idx < 0 and items:
            last = items[-1]
            if normalized_role == "user" and last.get("role") == normalized_role:
                idx = len(items) - 1
        if idx < 0:
            entry = self._create_history_entry(normalized_role, text)
            items.append(entry)
            new_id = entry["id"]
        else:
            entry = items[idx]
            entry["role"] = normalized_role
            entry["text"] = text
            entry["timestamp"] = _now()
            new_id = entry["id"]
        if normalized_role == "user":
            self.active_user_entry_id = None if is_final else new_id
        else:
            self.active_model_entry_id = None if is_final else new_id
        return _trim_history(items)

    # ----------------------------------------------------------------- #
    # Daily limit (ported)
    # ----------------------------------------------------------------- #
    def get_daily_limit_remaining_ms(self):
        today = _today_str()
        saved_date = _ls_get("vrm_daily_limit_date")
        saved_time = _ls_get("vrm_daily_limit_left")
        if saved_date != today:
            _ls_set("vrm_daily_limit_date", today)
            _ls_set("vrm_daily_limit_left", str(DAILY_LIMIT_MS))
            return DAILY_LIMIT_MS
        try:
            remaining = int(saved_time)
        except (TypeError, ValueError):
            return DAILY_LIMIT_MS
        return max(0, min(remaining, DAILY_LIMIT_MS))

    def save_daily_limit_remaining_ms(self, ms):
        _ls_set("vrm_daily_limit_date", _today_str())
        _ls_set("vrm_daily_limit_left", str(max(0, int(ms))))

    def start_session_limit_timer(self):
        self.clear_session_limit_timer()
        if self.consent_dev_sharing:
            return
        remaining = self.get_daily_limit_remaining_ms()
        self.session_time_remaining = remaining
        if remaining <= 0:
            self._force_disconnect_on_limit()
            self._set_daily_limit_dialog(True)
            return
        self._render_hud()

        def tick(*_):
            if self.session_time_remaining > 0:
                self.session_time_remaining -= 1000
                self.save_daily_limit_remaining_ms(self.session_time_remaining)
                self._render_hud()
                if self.session_time_remaining <= 0:
                    self._force_disconnect_on_limit()
                    self.clear_session_limit_timer()
                    self._set_daily_limit_dialog(True)

        self.session_timer_interval = _set_interval(tick, 1000)

    def _force_disconnect_on_limit(self):
        if self.is_connected and self.system and getattr(self.system, "ai_client", None):
            try:
                self.system.ai_client.disconnect("Daily limit reached (10 min free limit)")
            except Exception:  # noqa: BLE001
                pass
            self.is_connected = False
            self._render_dock()
            self._render_hud()

    def clear_session_limit_timer(self):
        _clear_interval(self.session_timer_interval)
        self.session_timer_interval = None
        self.session_time_remaining = 0

    # ----------------------------------------------------------------- #
    # Toasts
    # ----------------------------------------------------------------- #
    def show_toast(self, title, message, type_="info"):
        self.toast_counter += 1
        normalized = type_ if type_ in ("success", "error", "info", "warning") else "info"
        icon = {"success": "✓", "error": "✕", "warning": "!", "info": "ℹ"}[normalized]
        node = document.createElement("div")
        node.className = f"qv-toast qv-toast-{normalized}"
        node.innerHTML = (
            f'<div class="qv-toast-icon">{icon}</div>'
            f'<div><div class="qv-toast-title"></div><div class="qv-toast-msg"></div></div>'
        )
        node.querySelector(".qv-toast-title").textContent = str(title)
        node.querySelector(".qv-toast-msg").textContent = str(message)
        self.el["toasts"].appendChild(node)

        def remove(*_):
            try:
                node.remove()
            except Exception:  # noqa: BLE001
                pass

        _set_timeout(remove, 4200)

    def track_reconnect_issue(self):
        now = _now()
        self.reconnect_timestamps = [ts for ts in self.reconnect_timestamps if now - ts <= RECONNECT_WINDOW_MS]
        self.reconnect_timestamps.append(now)
        should_hint = (len(self.reconnect_timestamps) >= RECONNECT_HINT_THRESHOLD
                       and now - self.last_reconnect_hint_at > RECONNECT_WINDOW_MS / 2)
        if should_hint:
            self.last_reconnect_hint_at = now
            self.show_toast(self.t("toasts.performanceTipTitle"), self.t("toasts.performanceTipMessage"), "info")

    # ----------------------------------------------------------------- #
    # Loader
    # ----------------------------------------------------------------- #
    def localize_loader_text(self, value):
        normalized = value.strip() if isinstance(value, str) else ""
        if not normalized:
            return normalized
        lang = resolve_language(self.selected_language)
        return LOADER_TEXTS.get(lang, {}).get(normalized, normalized)

    def update_loading_state(self, info):
        info = dict(info) if info else {}
        progress = info.get("progress")
        try:
            progress = round(float(progress))
        except (TypeError, ValueError):
            progress = self.loading_state["progress"]
        progress = max(self.loading_state["progress"], min(100, progress))
        stage = self.localize_loader_text(info.get("stage") or self.loading_state["stage"])
        detail_in = info.get("detail")
        detail = self.localize_loader_text(self.loading_state["detail"]) if detail_in in (None, "") else self.localize_loader_text(detail_in)
        self.loading_state = {"progress": progress, "stage": stage, "detail": detail}
        self._render_loader()

    def _render_loader(self):
        st = self.loading_state
        loader = self.el.get("loader")
        if not loader:
            return
        self.el["loader_fill"].style.width = f"{max(2, st['progress'])}%"
        self.el["loader_stage"].textContent = st["stage"]
        self.el["loader_pct"].textContent = f"BUFFER: {round(st['progress'])}% / 100%"
        self.el["loader_detail"].textContent = f"> {st['detail']}..."
        if st["progress"] >= 100:
            loader.classList.add("qv-loader-done")

            def hide(*_):
                loader.classList.add("qv-hidden")

            _set_timeout(hide, 1200)

    # ----------------------------------------------------------------- #
    # DOM construction
    # ----------------------------------------------------------------- #
    def build(self, mount=None):
        # inject CSS once
        if not document.getElementById("qv-style"):
            style = document.createElement("style")
            style.id = "qv-style"
            style.textContent = APP_CSS
            document.head.appendChild(style)

        root = mount or document.body
        shell = document.createElement("div")
        shell.className = "qv-shell"
        self.el["shell"] = shell

        shell.innerHTML = (
            '<div class="qv-backdrop"></div>'
            '<div class="qv-vignette"></div>'
            '<canvas class="qv-canvas" id="qv-canvas"></canvas>'
            '<div class="qv-drag qv-hidden" id="qv-drag">'
            '  <div style="border:1px solid rgba(34,211,238,0.3); border-radius:16px; padding:24px 32px;">'
            '    <p class="qv-mono" id="qv-drag-hint" style="font-size:11px; color:rgba(165,243,252,0.7); letter-spacing:.22em;"></p>'
            '    <p id="qv-drag-title" style="margin-top:8px; font-size:22px; font-weight:600; color:#fff;"></p>'
            '  </div>'
            '</div>'
            '<div class="qv-toasts" id="qv-toasts"></div>'
        )
        root.appendChild(shell)

        self.el["canvas"] = shell.querySelector("#qv-canvas")
        self.el["drag"] = shell.querySelector("#qv-drag")
        self.el["toasts"] = shell.querySelector("#qv-toasts")
        shell.querySelector("#qv-drag-hint").textContent = self.t("app.dragAndDrop")
        shell.querySelector("#qv-drag-title").textContent = self.t("app.uploadAvatar")

        self._build_loader(shell)
        self._build_hud(shell)
        self._build_dock(shell)
        self._build_chat(shell)
        self._build_settings(shell)
        self._build_persona_dialog(shell)
        self._build_timer(shell)
        self._build_dialogs(shell)

        self._wire_drag_and_drop()
        self._render_dock()
        self._render_hud()
        return shell

    def _build_loader(self, shell):
        loader = document.createElement("div")
        loader.className = "qv-loader"
        loader.id = "qv-loader"
        loader.innerHTML = (
            '<div class="qv-loader-core"></div>'
            '<div class="qv-loader-title">QUANTUM AI SYNC</div>'
            '<div class="qv-loader-barwrap">'
            '  <div class="qv-loader-bar"><div class="qv-loader-fill" id="qv-loader-fill"></div></div>'
            '  <div class="qv-loader-meta"><span id="qv-loader-stage"></span><span id="qv-loader-pct"></span></div>'
            '  <div class="qv-loader-detail" id="qv-loader-detail"></div>'
            '</div>'
        )
        shell.appendChild(loader)
        self.el["loader"] = loader
        self.el["loader_fill"] = loader.querySelector("#qv-loader-fill")
        self.el["loader_stage"] = loader.querySelector("#qv-loader-stage")
        self.el["loader_pct"] = loader.querySelector("#qv-loader-pct")
        self.el["loader_detail"] = loader.querySelector("#qv-loader-detail")
        self._render_loader()

    def _build_hud(self, shell):
        wrap = document.createElement("div")
        wrap.className = "qv-hud-wrap"
        wrap.innerHTML = (
            '<div class="qv-hud-panel">'
            '  <div style="display:flex; align-items:center; gap:8px;">'
            '    <span class="qv-dot" id="qv-status-dot"></span>'
            '    <p class="qv-mono" id="qv-status-text" style="font-size:11px; color:rgba(255,255,255,0.5);"></p>'
            '  </div>'
            '  <p id="qv-status-sub" style="margin-top:8px; font-size:13px; color:rgba(255,255,255,0.4);"></p>'
            '  <div style="margin-top:8px; display:flex; flex-wrap:wrap; gap:8px;" id="qv-hud-badges"></div>'
            '</div>'
            '<div class="qv-hud-panel" style="min-width:120px; text-align:right;">'
            '  <p class="qv-mono" id="qv-fps-label" style="font-size:10px; color:var(--text-muted);"></p>'
            '  <p id="qv-fps" style="margin-top:4px; font-size:20px; font-weight:600;">0</p>'
            '  <p id="qv-scene-status" style="margin-top:4px; font-size:11px; color:var(--text-muted);"></p>'
            '</div>'
        )
        shell.appendChild(wrap)
        self.el["status_dot"] = wrap.querySelector("#qv-status-dot")
        self.el["status_text"] = wrap.querySelector("#qv-status-text")
        self.el["status_sub"] = wrap.querySelector("#qv-status-sub")
        self.el["hud_badges"] = wrap.querySelector("#qv-hud-badges")
        self.el["fps_label"] = wrap.querySelector("#qv-fps-label")
        self.el["fps"] = wrap.querySelector("#qv-fps")
        self.el["scene_status"] = wrap.querySelector("#qv-scene-status")

    def _render_hud(self):
        if "status_dot" not in self.el:
            return
        self.el["status_dot"].className = "qv-dot " + ("qv-dot-live" if self.is_connected else "qv-dot-standby")
        self.el["status_text"].textContent = self.t("app.liveSessionActive") if self.is_connected else self.t("app.systemStandby")
        self.el["status_sub"].textContent = self.t("app.voiceLinkStable") if self.is_connected else self.t("app.connectVoiceVision")
        self.el["fps_label"].textContent = self.t("app.renderFps")
        self.el["scene_status"].textContent = self.t("app.sceneReady") if self.system_ready else self.t("app.initializingScene")

        badges = self.el["hud_badges"]
        badges.innerHTML = ""
        if self.is_sharing_screen:
            b = document.createElement("span")
            b.className = "qv-badge qv-badge-screen"
            b.textContent = self.t("app.screenShareEnabled")
            badges.appendChild(b)
        if self.is_connected and not self.consent_dev_sharing:
            b = document.createElement("span")
            b.className = "qv-badge qv-badge-limit"
            b.textContent = f"Session Limit: {_format_remaining_time(self.session_time_remaining)}"
            badges.appendChild(b)

    def _build_dock(self, shell):
        wrap = document.createElement("div")
        wrap.className = "qv-dock-wrap"
        wrap.innerHTML = (
            '<div class="qv-dock">'
            '  <input type="file" accept=".vrm" class="qv-hidden" id="qv-file-input" />'
            '  <button class="qv-dock-btn" id="qv-btn-upload" title="">⬆</button>'
            '  <button class="qv-dock-btn" id="qv-btn-screen" title="">🖥</button>'
            '  <button class="qv-dock-call qv-call-idle" id="qv-btn-call" title="">🎙</button>'
            '  <button class="qv-dock-btn" id="qv-btn-chat" title="">💬</button>'
            '  <button class="qv-dock-btn" id="qv-btn-settings" title="">⚙</button>'
            '</div>'
        )
        shell.appendChild(wrap)
        self.el["file_input"] = wrap.querySelector("#qv-file-input")
        self.el["btn_upload"] = wrap.querySelector("#qv-btn-upload")
        self.el["btn_screen"] = wrap.querySelector("#qv-btn-screen")
        self.el["btn_call"] = wrap.querySelector("#qv-btn-call")
        self.el["btn_chat"] = wrap.querySelector("#qv-btn-chat")
        self.el["btn_settings"] = wrap.querySelector("#qv-btn-settings")

        self.el["btn_upload"].addEventListener("click", proxy(lambda e: self._open_file_picker()))
        self.el["btn_screen"].addEventListener("click", proxy(lambda e: asyncio.ensure_future(self.toggle_screen_share())))
        self.el["btn_call"].addEventListener("click", proxy(lambda e: asyncio.ensure_future(self.toggle_connection())))
        self.el["btn_chat"].addEventListener("click", proxy(lambda e: self.toggle_chat_panel()))
        self.el["btn_settings"].addEventListener("click", proxy(lambda e: self.toggle_settings_panel()))

        def on_file_change(event):
            files = event.target.files
            if files and files.length > 0:
                asyncio.ensure_future(self.load_vrm_file(files.item(0)))
            event.target.value = ""

        self.el["file_input"].addEventListener("change", proxy(on_file_change))

    def _open_file_picker(self):
        if self.system_ready:
            self.el["file_input"].click()

    def _render_dock(self):
        if "btn_call" not in self.el:
            return
        # upload
        self.el["btn_upload"].disabled = not self.system_ready
        self.el["btn_upload"].title = self.t("dock.uploadAvatarTitle")
        # screen
        self.el["btn_screen"].className = "qv-dock-btn" + (" qv-active-purple" if self.is_sharing_screen else "")
        self.el["btn_screen"].title = self.t("dock.toggleScreenShareTitle")
        # call
        call = self.el["btn_call"]
        call.disabled = (not self.system_ready) or self.is_connecting
        call.className = "qv-dock-call " + ("qv-call-live" if self.is_connected else "qv-call-idle")
        call.textContent = "📵" if self.is_connected else "🎙"
        if self.is_connecting:
            call.title = self.t("dock.connecting")
        elif self.is_connected:
            call.title = self.t("dock.disconnect")
        else:
            call.title = self.t("dock.connect")
        # chat / settings
        self.el["btn_chat"].className = "qv-dock-btn" + (" qv-active" if self.show_chat else "")
        self.el["btn_chat"].title = self.t("dock.toggleChatTitle")
        self.el["btn_settings"].className = "qv-dock-btn" + (" qv-active" if self.show_settings else "")
        self.el["btn_settings"].title = self.t("dock.settingsTitle")

    # ----------------------------------------------------------------- #
    # Chat panel
    # ----------------------------------------------------------------- #
    def _build_chat(self, shell):
        panel = document.createElement("div")
        panel.className = "qv-panel qv-chat qv-hidden"
        panel.id = "qv-chat"
        panel.innerHTML = (
            '<div class="qv-panel-head">'
            '  <div style="display:flex; align-items:center; gap:8px;">'
            '    <span class="qv-dot qv-dot-standby" style="height:6px;width:6px;"></span>'
            '    <p class="qv-mono" id="qv-chat-title" style="font-size:11px; color:rgba(207,250,254,0.8);"></p>'
            '  </div>'
            '  <div style="display:flex; align-items:center; gap:12px;">'
            '    <button class="qv-x" id="qv-chat-clear" style="font-size:10px; font-family:ui-monospace,monospace; text-transform:uppercase;"></button>'
            '    <button class="qv-x" id="qv-chat-close">✕</button>'
            '  </div>'
            '</div>'
            '<div class="qv-chat-list qv-scroll" id="qv-chat-list"></div>'
        )
        shell.appendChild(panel)
        self.el["chat"] = panel
        self.el["chat_title"] = panel.querySelector("#qv-chat-title")
        self.el["chat_clear"] = panel.querySelector("#qv-chat-clear")
        self.el["chat_list"] = panel.querySelector("#qv-chat-list")
        panel.querySelector("#qv-chat-close").addEventListener("click", proxy(lambda e: self.toggle_chat_panel()))
        self.el["chat_clear"].addEventListener("click", proxy(lambda e: self.clear_history()))

    def _render_chat(self):
        if "chat_list" not in self.el or self.el["chat"].classList.contains("qv-hidden"):
            # still update label if visible later; skip heavy render when hidden
            if "chat_title" in self.el:
                self.el["chat_title"].textContent = self.t("chat.conversationLog", {"count": len(self.chat_history)})
                self.el["chat_clear"].textContent = self.t("chat.clear")
            return
        self.el["chat_title"].textContent = self.t("chat.conversationLog", {"count": len(self.chat_history)})
        self.el["chat_clear"].textContent = self.t("chat.clear")
        lst = self.el["chat_list"]
        lst.innerHTML = ""
        if not self.chat_history:
            empty = document.createElement("div")
            empty.className = "qv-chat-empty"
            empty.textContent = self.t("chat.noMessagesYet")
            lst.appendChild(empty)
            return
        locale = get_locale_for_language(self.selected_language)
        for msg in self.chat_history:
            is_user = msg.get("role") == "user"
            row = document.createElement("div")
            row.className = "qv-msg-row " + ("qv-user" if is_user else "qv-model")
            bubble = document.createElement("div")
            bubble.className = "qv-bubble " + ("qv-bubble-user" if is_user else "qv-bubble-model")
            bubble.textContent = msg.get("text", "")
            row.appendChild(bubble)
            meta = document.createElement("div")
            meta.className = "qv-msg-meta"
            role_span = document.createElement("span")
            role_span.className = "qv-mono " + ("qv-meta-user" if is_user else "qv-meta-model")
            role_span.style.letterSpacing = "0.14em"
            role_span.textContent = self.t("chat.you") if is_user else self.t("chat.assistant")
            sep = document.createElement("span")
            sep.className = "qv-meta-time"
            sep.textContent = "·"
            time_span = document.createElement("span")
            time_span.className = "qv-meta-time"
            try:
                time_span.textContent = window.Date.new(msg.get("timestamp", _now())).toLocaleTimeString(
                    locale, _time_fmt())
            except Exception:  # noqa: BLE001
                time_span.textContent = ""
            meta.appendChild(role_span)
            meta.appendChild(sep)
            meta.appendChild(time_span)
            row.appendChild(meta)
            lst.appendChild(row)
        lst.scrollTop = lst.scrollHeight

    # ----------------------------------------------------------------- #
    # Settings panel
    # ----------------------------------------------------------------- #
    def _build_settings(self, shell):
        panel = document.createElement("div")
        panel.className = "qv-panel qv-settings qv-scroll qv-hidden"
        panel.id = "qv-settings"
        panel.innerHTML = (
            '<div class="qv-panel-head">'
            '  <p class="qv-mono" id="qv-set-title" style="font-size:11px; color:rgba(207,250,254,0.9);"></p>'
            '  <button class="qv-x" id="qv-set-close">✕</button>'
            '</div>'
            '<div style="margin-top:12px;">'
            '  <p class="qv-label" id="qv-set-id-label"></p>'
            '  <div id="qv-model-list" style="display:flex; flex-direction:column; gap:8px; max-height:160px; overflow-y:auto;"></div>'
            '</div>'
            '<div class="qv-section">'
            '  <div style="display:flex; align-items:center; justify-content:space-between;">'
            '    <p class="qv-label" id="qv-set-persona-label"></p>'
            '    <button class="qv-btn" id="qv-set-edit-personas"></button>'
            '  </div>'
            '  <div class="qv-card" style="margin-top:8px;">'
            '    <p id="qv-set-persona-title" style="font-size:13px; font-weight:600;"></p>'
            '    <p id="qv-set-persona-desc" style="margin-top:4px; font-size:11px; color:rgba(255,255,255,0.5);"></p>'
            '  </div>'
            '</div>'
            '<div class="qv-section">'
            '  <p class="qv-label" id="qv-set-lang-label"></p>'
            '  <div class="qv-card"><select class="qv-select" id="qv-lang-select"></select></div>'
            '</div>'
            '<div class="qv-section">'
            '  <div style="display:flex; align-items:center; justify-content:space-between;">'
            '    <p class="qv-label" id="qv-set-scale-label"></p>'
            '    <span class="qv-chip" id="qv-scale-chip"></span>'
            '  </div>'
            '  <input type="range" min="0.5" max="3.0" step="0.1" class="qv-range" id="qv-scale" style="margin-top:10px;" />'
            '</div>'
            '<div class="qv-section">'
            '  <div style="display:flex; align-items:center; justify-content:space-between;">'
            '    <p class="qv-label" id="qv-set-bg-label"></p>'
            '    <span class="qv-chip" id="qv-bg-chip"></span>'
            '  </div>'
            '  <div class="qv-card" style="display:flex; gap:12px; align-items:center; margin-top:8px;">'
            '    <input type="color" class="qv-color" id="qv-bg-color" />'
            '    <input type="text" maxlength="7" spellcheck="false" class="qv-input" id="qv-bg-text" style="font-family:ui-monospace,monospace;" />'
            '  </div>'
            '</div>'
            '<div class="qv-section">'
            '  <p class="qv-label" id="qv-set-vision-label"></p>'
            '  <div class="qv-vision-row">'
            '    <button class="qv-vision-btn" id="qv-vision-user"><div style="font-size:18px;">👁</div><p id="qv-vision-user-label" style="font-size:12px; margin-top:6px;"></p></button>'
            '    <button class="qv-vision-btn" id="qv-vision-screen"><div style="font-size:18px;">🖥</div><p id="qv-vision-screen-label" style="font-size:12px; margin-top:6px;"></p></button>'
            '  </div>'
            '</div>'
            '<div class="qv-section">'
            '  <p class="qv-label">Privacy &amp; Telemetry</p>'
            '  <div class="qv-card">'
            '    <div style="display:flex; align-items:center; justify-content:space-between;">'
            '      <span style="font-size:12px; color:rgba(255,255,255,0.7);">Developer Data Sharing</span>'
            '      <button class="qv-btn" id="qv-dev-share"></button>'
            '    </div>'
            '    <p style="margin-top:8px; font-size:10px; line-height:1.5; color:rgba(255,255,255,0.4);">'
            '      If allowed, system logs, screenshots, and videos are shared with developers to improve model quality. '
            '      Disabling this limits call time to 10 minutes and blocks media relays.</p>'
            '  </div>'
            '</div>'
        )
        shell.appendChild(panel)
        self.el["settings"] = panel
        # wire close + click-outside
        panel.querySelector("#qv-set-close").addEventListener("click", proxy(lambda e: self.toggle_settings_panel()))
        panel.querySelector("#qv-set-edit-personas").addEventListener("click", proxy(lambda e: self.open_persona_manager()))

        # scale
        scale = panel.querySelector("#qv-scale")

        def on_scale(event):
            self.set_avatar_scale(self._parse_float(event.target.value, self.avatar_scale))

        scale.addEventListener("input", proxy(on_scale))
        self.el["scale"] = scale

        # bg color
        def on_bg(event):
            self.set_background_color(event.target.value)

        panel.querySelector("#qv-bg-color").addEventListener("input", proxy(on_bg))
        panel.querySelector("#qv-bg-text").addEventListener("input", proxy(on_bg))
        self.el["bg_color"] = panel.querySelector("#qv-bg-color")
        self.el["bg_text"] = panel.querySelector("#qv-bg-text")

        # language
        def on_lang(event):
            self.set_language(str(event.target.value or "").strip().lower())

        sel = panel.querySelector("#qv-lang-select")
        sel.addEventListener("change", proxy(on_lang))
        self.el["lang_select"] = sel

        # vision
        panel.querySelector("#qv-vision-user").addEventListener("click", proxy(lambda e: self.set_look_at_user(not self.look_at_user_enabled)))
        panel.querySelector("#qv-vision-screen").addEventListener("click", proxy(lambda e: self.set_look_at_screen(not self.look_at_screen_enabled)))

        # dev sharing
        panel.querySelector("#qv-dev-share").addEventListener("click", proxy(lambda e: self.toggle_consent_dev_sharing()))

        self.el["model_list"] = panel.querySelector("#qv-model-list")

    def _render_settings(self):
        if "settings" not in self.el:
            return
        p = self.el["settings"]
        p.querySelector("#qv-set-title").textContent = self.t("settings.systemControl")
        p.querySelector("#qv-set-id-label").textContent = self.t("settings.identityMatrix")
        p.querySelector("#qv-set-persona-label").textContent = self.t("settings.aiPersona")
        p.querySelector("#qv-set-edit-personas").textContent = self.t("settings.editPersonas")
        persona = self.selected_persona()
        p.querySelector("#qv-set-persona-title").textContent = persona.get("title") or self.t("settings.defaultRiko")
        p.querySelector("#qv-set-persona-desc").textContent = persona.get("description") or self.t("settings.defaultPersonaDescription")
        p.querySelector("#qv-set-lang-label").textContent = self.t("settings.languageMode")
        p.querySelector("#qv-set-scale-label").textContent = self.t("settings.projectionScale")
        p.querySelector("#qv-scale-chip").textContent = f"{self.avatar_scale:.1f}x"
        p.querySelector("#qv-set-bg-label").textContent = self.t("settings.backgroundColor")
        p.querySelector("#qv-bg-chip").textContent = self.background_color
        p.querySelector("#qv-set-vision-label").textContent = self.t("settings.visionSensors")
        p.querySelector("#qv-vision-user-label").textContent = self.t("settings.faceTrack")
        p.querySelector("#qv-vision-screen-label").textContent = self.t("settings.screenSense")

        self.el["scale"].value = str(self.avatar_scale)
        self.el["bg_color"].value = self.background_color
        self.el["bg_text"].value = self.background_color

        # language select
        sel = self.el["lang_select"]
        sel.innerHTML = ""
        for opt in self.language_options():
            o = document.createElement("option")
            o.value = opt["code"]
            o.textContent = opt["label"]
            if opt["code"] == self.selected_language:
                o.selected = True
            sel.appendChild(o)

        # vision buttons
        uvb = p.querySelector("#qv-vision-user")
        uvb.className = "qv-vision-btn" + (" qv-on-user" if self.look_at_user_enabled else "")
        svb = p.querySelector("#qv-vision-screen")
        svb.className = "qv-vision-btn" + (" qv-on-screen" if self.look_at_screen_enabled else "")

        # dev share button
        ds = p.querySelector("#qv-dev-share")
        ds.textContent = "Allowed" if self.consent_dev_sharing else "Blocked"

        self._render_model_list()

    def _render_model_list(self):
        if "model_list" not in self.el:
            return
        lst = self.el["model_list"]
        lst.innerHTML = ""
        # default model row
        default_row = document.createElement("div")
        default_row.className = "qv-model-row"
        default_row.innerHTML = (
            f'<div><p style="font-size:12px; font-weight:600;">{self.t("settings.defaultRiko")}</p>'
            f'<p style="font-size:10px; color:rgba(255,255,255,0.4);">{self.t("settings.systemModel")}</p></div>'
        )
        default_row.addEventListener("click", proxy(lambda e: asyncio.ensure_future(self.handle_model_switch(None))))
        lst.appendChild(default_row)

        for model in self.available_models:
            key = model.get("key") if isinstance(model, dict) else None
            meta = (model.get("meta") or {}) if isinstance(model, dict) else {}
            name = meta.get("name") or self.t("settings.unknownModel")
            row = document.createElement("div")
            row.className = "qv-model-row"
            row.innerHTML = (
                f'<div style="min-width:0;"><p style="font-size:12px; font-weight:600;"></p></div>'
                f'<button class="qv-del">🗑</button>'
            )
            row.querySelector("p").textContent = name
            row.addEventListener("click", proxy(lambda e, k=key: asyncio.ensure_future(self.handle_model_switch(k))))

            def on_del(event, k=key):
                event.stopPropagation()
                asyncio.ensure_future(self.handle_model_delete(k))

            row.querySelector(".qv-del").addEventListener("click", proxy(on_del))
            lst.appendChild(row)

    # ----------------------------------------------------------------- #
    # Persona dialog
    # ----------------------------------------------------------------- #
    def _build_persona_dialog(self, shell):
        overlay = document.createElement("div")
        overlay.className = "qv-overlay qv-hidden"
        overlay.id = "qv-persona-overlay"
        overlay.style.background = "rgba(0,0,0,0.6)"
        panel = document.createElement("div")
        panel.className = "qv-panel qv-persona"
        panel.innerHTML = (
            '<div class="qv-panel-head">'
            '  <p class="qv-mono" id="qv-persona-title" style="font-size:11px; color:rgba(207,250,254,0.9);"></p>'
            '  <button class="qv-x" id="qv-persona-close">✕</button>'
            '</div>'
            '<div class="qv-persona-grid qv-scroll" style="padding-top:12px;">'
            '  <div>'
            '    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">'
            '      <p class="qv-label" id="qv-persona-avail" style="margin:0;"></p>'
            '      <button class="qv-btn" id="qv-persona-new"></button>'
            '    </div>'
            '    <div id="qv-persona-list" style="display:flex; flex-direction:column; gap:8px; max-height:360px; overflow-y:auto;"></div>'
            '  </div>'
            '  <div class="qv-card" id="qv-persona-form-card">'
            '    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:12px;">'
            '      <p class="qv-mono" id="qv-persona-form-title" style="font-size:10px; color:rgba(165,243,252,0.7);"></p>'
            '      <button class="qv-x" id="qv-persona-cancel" style="font-size:10px;"></button>'
            '    </div>'
            '    <div id="qv-persona-form"></div>'
            '    <div id="qv-persona-hint" style="font-size:11px; color:rgba(255,255,255,0.45);"></div>'
            '  </div>'
            '</div>'
        )
        overlay.appendChild(panel)
        shell.appendChild(overlay)
        self.el["persona_overlay"] = overlay
        self.el["persona_list"] = panel.querySelector("#qv-persona-list")
        self.el["persona_form"] = panel.querySelector("#qv-persona-form")
        self.el["persona_hint"] = panel.querySelector("#qv-persona-hint")
        panel.querySelector("#qv-persona-close").addEventListener("click", proxy(lambda e: self.close_persona_manager()))
        panel.querySelector("#qv-persona-new").addEventListener("click", proxy(lambda e: self._persona_start_create()))
        panel.querySelector("#qv-persona-cancel").addEventListener("click", proxy(lambda e: self._persona_cancel_form()))

        def on_overlay_click(event):
            if event.target is overlay:
                self.close_persona_manager()

        overlay.addEventListener("click", proxy(on_overlay_click))

    def _render_persona_dialog(self):
        if "persona_overlay" not in self.el:
            return
        p = self.el["persona_overlay"]
        p.querySelector("#qv-persona-title").textContent = self.t("personaDialog.editPersonas")
        p.querySelector("#qv-persona-avail").textContent = self.t("personaDialog.availablePersonas")
        p.querySelector("#qv-persona-new").textContent = self.t("personaDialog.new")
        p.querySelector("#qv-persona-new").disabled = self._persona_edit_lock_active()
        p.querySelector("#qv-persona-cancel").textContent = self.t("personaDialog.cancel")
        cancel_btn = p.querySelector("#qv-persona-cancel")
        cancel_btn.style.display = "block" if self.persona_form_open else "none"
        title_lbl = self.t("personaDialog.editPersona") if self.persona_editing else self.t("personaDialog.createPersona")
        p.querySelector("#qv-persona-form-title").textContent = title_lbl

        # list
        lst = self.el["persona_list"]
        lst.innerHTML = ""
        for persona in self.personas:
            pid = persona["id"]
            item = document.createElement("div")
            locked = self._persona_locked(pid)
            cls = "qv-persona-item"
            if self.selected_persona_id == pid:
                cls += " qv-selected"
            if locked:
                cls += " qv-locked"
            item.className = cls
            title = persona.get("title", "")
            desc = persona.get("description", "")
            check = " ✓" if self.selected_persona_id == pid else ""
            badge = f' <span class="qv-chip">{self.t("personaDialog.default")}</span>' if persona.get("isDefault") else ""
            actions = ""
            if not persona.get("isDefault") and not persona.get("isBuiltin"):
                actions = ('<button class="qv-x" data-act="edit" style="font-size:14px;">✎</button>'
                           '<button class="qv-x" data-act="del" style="font-size:14px;">🗑</button>')
            item.innerHTML = (
                '<div style="display:flex; justify-content:space-between; gap:8px; align-items:flex-start;">'
                f'  <div style="min-width:0;"><p style="font-size:12px; font-weight:600;"></p>'
                f'    <p style="margin-top:4px; font-size:10px; color:rgba(255,255,255,0.5);"></p></div>'
                f'  <div style="display:flex; gap:4px;">{actions}</div>'
                '</div>'
            )
            ps = item.querySelectorAll("p")
            ps.item(0).innerHTML = title + check + badge
            ps.item(1).textContent = desc

            if not locked:
                item.addEventListener("click", proxy(lambda e, k=pid: self._persona_select(k)))
            edit_btn = item.querySelector('[data-act="edit"]')
            if edit_btn:
                edit_btn.addEventListener("click", proxy(lambda e, pa=persona: self._persona_start_edit(pa, e)))
            del_btn = item.querySelector('[data-act="del"]')
            if del_btn:
                del_btn.addEventListener("click", proxy(lambda e, k=pid: self._persona_delete(k, e)))
            lst.appendChild(item)

        # form
        form = self.el["persona_form"]
        hint = self.el["persona_hint"]
        if self.persona_form_open:
            hint.style.display = "none"
            form.style.display = "block"
            form.innerHTML = (
                f'<label style="display:block; margin-bottom:10px;">'
                f'<span style="font-size:10px; color:rgba(255,255,255,0.5);">{self.t("personaDialog.title")}</span>'
                f'<input class="qv-input" id="qv-pd-title" maxlength="60" style="margin-top:4px;" /></label>'
                f'<label style="display:block; margin-bottom:10px;">'
                f'<span style="font-size:10px; color:rgba(255,255,255,0.5);">{self.t("personaDialog.shortDescription")}</span>'
                f'<input class="qv-input" id="qv-pd-desc" maxlength="180" style="margin-top:4px;" /></label>'
                f'<label style="display:block; margin-bottom:10px;">'
                f'<span style="font-size:10px; color:rgba(255,255,255,0.5);">{self.t("personaDialog.personaPrompt")}</span>'
                f'<textarea class="qv-textarea" id="qv-pd-prompt" rows="6" maxlength="5000" style="margin-top:4px; resize:vertical;"></textarea></label>'
                f'<button class="qv-btn" id="qv-pd-submit" style="width:100%;"></button>'
            )
            ti = form.querySelector("#qv-pd-title")
            di = form.querySelector("#qv-pd-desc")
            pi = form.querySelector("#qv-pd-prompt")
            ti.value = self.persona_draft["title"]
            di.value = self.persona_draft["description"]
            pi.value = self.persona_draft["prompt"]
            ti.placeholder = self.t("personaDialog.titlePlaceholder")
            di.placeholder = self.t("personaDialog.summaryPlaceholder")
            pi.placeholder = self.t("personaDialog.promptPlaceholder")
            sub = form.querySelector("#qv-pd-submit")
            sub.textContent = self.t("personaDialog.saveChanges") if self.persona_editing else self.t("personaDialog.addPersona")
            sub.addEventListener("click", proxy(lambda e: self._persona_submit()))
        else:
            form.style.display = "none"
            form.innerHTML = ""
            hint.style.display = "block"
            hint.textContent = self.t("personaDialog.pickPersonaHint")
            if self._persona_edit_lock_active():
                hint.textContent = self.t("personaDialog.editLockHint")

    def _persona_edit_lock_active(self):
        return self.persona_form_open and self.persona_editing and bool(self.persona_editing_id)

    def _persona_locked(self, pid):
        if not self._persona_edit_lock_active():
            return False
        return pid != self.persona_editing_id

    def _persona_reset_draft(self):
        self.persona_form_open = False
        self.persona_editing = False
        self.persona_editing_id = ""
        self.persona_draft = {"title": "", "description": "", "prompt": ""}

    def _persona_capture_draft(self):
        form = self.el.get("persona_form")
        if not form:
            return
        ti = form.querySelector("#qv-pd-title")
        di = form.querySelector("#qv-pd-desc")
        pi = form.querySelector("#qv-pd-prompt")
        if ti and di and pi:
            self.persona_draft = {"title": ti.value or "", "description": di.value or "", "prompt": pi.value or ""}

    def _persona_start_create(self):
        if self._persona_edit_lock_active():
            return
        self._persona_reset_draft()
        self.persona_form_open = True
        self._render_persona_dialog()

    def _persona_start_edit(self, persona, event=None):
        if event:
            event.stopPropagation()
        if not persona or persona.get("isDefault") or persona.get("isBuiltin"):
            return
        if self._persona_edit_lock_active() and self.persona_editing_id != persona["id"]:
            return
        self.persona_form_open = True
        self.persona_editing = True
        self.persona_editing_id = persona["id"]
        self.persona_draft = {"title": persona.get("title", ""), "description": persona.get("description", ""),
                              "prompt": persona.get("prompt", "")}
        self._render_persona_dialog()

    def _persona_cancel_form(self):
        self._persona_capture_draft()
        self._persona_reset_draft()
        self._render_persona_dialog()

    def _persona_submit(self):
        self._persona_capture_draft()
        draft = {k: (v or "").strip() for k, v in self.persona_draft.items()}
        if not draft["title"] or not draft["description"] or not draft["prompt"]:
            self.show_toast(self.t("toasts.personaErrorTitle"), self.t("toasts.personaRequiredFields"), "error")
            return
        if self.persona_editing and self.persona_editing_id:
            self.handle_persona_update({"id": self.persona_editing_id, **draft})
        else:
            self.handle_persona_create(draft)
        self._persona_reset_draft()
        self._render_persona_dialog()

    def _persona_select(self, pid):
        if self._persona_locked(pid):
            return
        self.handle_persona_select(pid)
        self._render_persona_dialog()
        self._render_settings()

    def _persona_delete(self, pid, event=None):
        if event:
            event.stopPropagation()
        if self._persona_locked(pid):
            return
        self.handle_persona_delete(pid)
        self._render_persona_dialog()
        self._render_settings()

    # persona persistence + handlers (ported)
    def _persist_personas(self):
        sanitized = []
        for persona in self.personas:
            if persona.get("isDefault") or persona.get("isBuiltin") or _is_builtin_persona_id(persona["id"]):
                continue
            sanitized.append({
                "id": persona["id"],
                "title": _sanitize_persona_text(persona.get("title"), 60),
                "description": _sanitize_persona_text(persona.get("description"), 180),
                "prompt": _sanitize_persona_text(persona.get("prompt"), 5000),
            })
        _ls_set(PERSONAS_STORAGE_KEY, json.dumps(sanitized))
        if not any(p["id"] == self.selected_persona_id for p in self.personas):
            self.set_selected_persona_id(DEFAULT_PERSONA_ID)

    def set_selected_persona_id(self, pid):
        exists = any(p["id"] == pid for p in self.personas)
        resolved = pid if exists else DEFAULT_PERSONA_ID
        self.selected_persona_id = resolved
        _ls_set(SELECTED_PERSONA_STORAGE_KEY, resolved)

    def handle_persona_select(self, pid):
        if not isinstance(pid, str) or not pid.strip():
            return
        if not any(p["id"] == pid for p in self.personas):
            return
        self.set_selected_persona_id(pid)
        if self.is_connected:
            self.show_toast(self.t("toasts.personaQueuedTitle"), self.t("toasts.personaQueuedMessage"), "info")

    def handle_persona_create(self, payload):
        title = _sanitize_persona_text(payload.get("title"), 60)
        description = _sanitize_persona_text(payload.get("description"), 180)
        prompt = _sanitize_persona_text(payload.get("prompt"), 5000)
        if not title or not description or not prompt:
            self.show_toast(self.t("toasts.personaErrorTitle"), self.t("toasts.personaRequiredFields"), "error")
            return
        created = {"id": _create_debug_id("persona"), "title": title, "description": description,
                   "prompt": prompt, "isDefault": False, "isBuiltin": False, "promptEnglish": ""}
        self.personas = [*self.personas, created]
        self._persist_personas()
        self.set_selected_persona_id(created["id"])
        self.show_toast(self.t("toasts.personaAddedTitle"),
                        self.t("toasts.personaAddedMessage", {"title": title}), "success")

    def handle_persona_update(self, payload):
        pid = payload.get("id", "")
        pid = pid.strip() if isinstance(pid, str) else ""
        if not pid or pid == DEFAULT_PERSONA_ID:
            return
        idx = next((i for i, p in enumerate(self.personas) if p["id"] == pid), -1)
        if idx < 0 or self.personas[idx].get("isBuiltin"):
            return
        title = _sanitize_persona_text(payload.get("title"), 60)
        description = _sanitize_persona_text(payload.get("description"), 180)
        prompt = _sanitize_persona_text(payload.get("prompt"), 5000)
        if not title or not description or not prompt:
            self.show_toast(self.t("toasts.personaErrorTitle"), self.t("toasts.personaRequiredFields"), "error")
            return
        self.personas[idx] = {**self.personas[idx], "title": title, "description": description,
                              "prompt": prompt, "isDefault": False, "isBuiltin": False, "promptEnglish": ""}
        self._persist_personas()
        self.show_toast(self.t("toasts.personaUpdatedTitle"),
                        self.t("toasts.personaUpdatedMessage", {"title": title}), "success")

    def handle_persona_delete(self, pid):
        if not isinstance(pid, str) or not pid.strip() or pid == DEFAULT_PERSONA_ID:
            return
        target = next((p for p in self.personas if p["id"] == pid), None)
        if not target or target.get("isBuiltin"):
            return
        if not window.confirm(self.t("toasts.personaDeleteConfirm", {"title": target.get("title", "")})):
            return
        self.personas = [p for p in self.personas if p["id"] != pid]
        self._persist_personas()
        if self.selected_persona_id == pid:
            self.set_selected_persona_id(DEFAULT_PERSONA_ID)
        self.show_toast(self.t("toasts.personaDeletedTitle"),
                        self.t("toasts.personaDeletedMessage", {"title": target.get("title", "")}), "success")

    # ----------------------------------------------------------------- #
    # Timer widget
    # ----------------------------------------------------------------- #
    def _build_timer(self, shell):
        overlay = document.createElement("div")
        overlay.className = "qv-timer-expired-overlay qv-hidden"
        shell.appendChild(overlay)
        self.el["timer_overlay"] = overlay

        timer = document.createElement("div")
        timer.className = "qv-timer qv-timer-min qv-hidden"
        timer.innerHTML = (
            '<div class="qv-timer-shell">'
            '  <div class="qv-timer-time" id="qv-timer-time">00:00</div>'
            '  <div style="flex:1; min-width:0;"><p class="qv-timer-label" id="qv-timer-label"></p></div>'
            '  <button class="qv-timer-x" id="qv-timer-dismiss">×</button>'
            '</div>'
        )
        shell.appendChild(timer)
        self.el["timer"] = timer
        self.el["timer_time"] = timer.querySelector("#qv-timer-time")
        self.el["timer_label"] = timer.querySelector("#qv-timer-label")
        timer.addEventListener("click", proxy(lambda e: self.toggle_timer_minimize()))

        def on_dismiss(event):
            event.stopPropagation()
            self.dismiss_timer()

        timer.querySelector("#qv-timer-dismiss").addEventListener("click", proxy(on_dismiss))

    def _timer_remaining_ms(self):
        if not self.timer_visible:
            return 0
        return max(0, self.timer_end_at_ms - _now())

    def _render_timer(self):
        if "timer" not in self.el:
            return
        timer = self.el["timer"]
        overlay = self.el["timer_overlay"]
        if not self.timer_visible:
            timer.classList.add("qv-hidden")
            overlay.classList.add("qv-hidden")
            return
        timer.classList.remove("qv-hidden")
        remaining_ms = self._timer_remaining_ms()
        import math
        remaining_s = math.ceil(remaining_ms / 1000)
        is_expired = remaining_s <= 0
        is_urgent = (not is_expired) and remaining_s <= 5
        cls = "qv-timer"
        cls += " qv-timer-min" if self.timer_minimized else " qv-timer-exp-pos"
        if is_urgent:
            cls += " qv-urgent"
        if is_expired:
            cls += " qv-expired"
        timer.className = cls
        minutes = max(0, remaining_s) // 60
        seconds = max(0, remaining_s) % 60
        self.el["timer_time"].textContent = f"{minutes:02d}:{seconds:02d}"
        self.el["timer_label"].textContent = self.timer_label
        if self.timer_expired_overlay:
            overlay.classList.remove("qv-hidden")
        else:
            overlay.classList.add("qv-hidden")

    def stop_timer_ticker(self):
        _clear_interval(self.timer_tick_interval)
        self.timer_tick_interval = None
        _clear_timeout(self.timer_auto_minimize_timeout)
        self.timer_auto_minimize_timeout = None
        _clear_timeout(self.timer_expiry_dismiss_timeout)
        self.timer_expiry_dismiss_timeout = None
        _clear_timeout(self.timer_pending_fallback_timeout)
        self.timer_pending_fallback_timeout = None

    def dismiss_timer(self):
        self.stop_timer_ticker()
        self.pending_timer_start = None
        self.timer_visible = False
        self.timer_minimized = True
        self.timer_label = "Timer"
        self.timer_total_ms = 0
        self.timer_end_at_ms = 0
        self.timer_notified = False
        self.timer_expired_overlay = False
        self._render_timer()

    def toggle_timer_minimize(self):
        if not self.timer_visible:
            return
        self.timer_minimized = not self.timer_minimized
        self._render_timer()

    def start_floating_timer(self, duration_seconds, label="Timer"):
        try:
            seconds = max(0, int(float(duration_seconds or 0)))
        except (TypeError, ValueError):
            seconds = 0
        if seconds <= 0:
            self.dismiss_timer()
            return
        self.stop_timer_ticker()
        safe_label = label.strip() if isinstance(label, str) and label.strip() else "Timer"
        now = _now()
        self.timer_visible = True
        self.timer_minimized = False
        self.timer_label = safe_label
        self.timer_total_ms = seconds * 1000
        self.timer_end_at_ms = now + self.timer_total_ms
        self.timer_notified = False
        self.timer_expired_overlay = False
        self._render_timer()

        def tick(*_):
            self._timer_check_expiry()
            self._render_timer()

        self.timer_tick_interval = _set_interval(tick, 200)

        def auto_min(*_):
            self.timer_minimized = True
            self._render_timer()

        self.timer_auto_minimize_timeout = _set_timeout(auto_min, 1200)

    def _timer_check_expiry(self):
        if not self.timer_visible:
            return
        import math
        seconds_left = math.ceil(self._timer_remaining_ms() / 1000)
        if seconds_left <= 0:
            self.stop_timer_ticker()
            self.timer_minimized = False
            self.timer_expired_overlay = True

            def auto_dismiss(*_):
                self.dismiss_timer()

            self.timer_expiry_dismiss_timeout = _set_timeout(auto_dismiss, 3000)
            return
        if self.timer_expired_overlay:
            self.timer_expired_overlay = False
        if self.timer_notified or seconds_left > 2:
            return
        self.timer_notified = True
        if self.is_connected and self.system and getattr(self.system.ai_client, "is_session_open", False):
            async def notify():
                try:
                    await self.system.ai_client.send_text("Time is up.", True)
                except Exception:  # noqa: BLE001
                    pass
            asyncio.ensure_future(notify())

    def handle_ai_timer_start(self, payload=None):
        payload = payload or {}

        def g(key):
            try:
                return payload.get(key)
            except AttributeError:
                return getattr(payload, key, None)

        duration = g("duration_seconds") or g("durationSeconds") or g("seconds") or g("duration")
        label = g("label") or g("title") or "Timer"
        self.pending_timer_start = {"durationSeconds": duration, "label": label}
        _clear_timeout(self.timer_pending_fallback_timeout)
        self.timer_pending_fallback_timeout = None
        if not self.assistant_speaking:
            def fallback(*_):
                self.timer_pending_fallback_timeout = None
                if self.assistant_speaking or not self.pending_timer_start:
                    return
                self.handle_assistant_speech_end()
            self.timer_pending_fallback_timeout = _set_timeout(fallback, 2500)

    def handle_ai_timer_cancel(self):
        self.dismiss_timer()

    def handle_assistant_speech_end(self):
        _clear_timeout(self.timer_pending_fallback_timeout)
        self.timer_pending_fallback_timeout = None
        pending = self.pending_timer_start
        if not pending:
            return
        self.pending_timer_start = None
        self.start_floating_timer(pending["durationSeconds"], pending["label"])

    # ----------------------------------------------------------------- #
    # Overlay dialogs (consent, recording, daily-limit)
    # ----------------------------------------------------------------- #
    def _build_dialogs(self, shell):
        # Consent terms dialog (ConfirmTermsDialog.vue)
        consent = document.createElement("div")
        consent.className = "qv-overlay qv-hidden"
        consent.id = "qv-consent"
        consent.innerHTML = (
            '<div class="qv-dialog qv-dialog-cyan">'
            '  <p class="qv-mono" style="font-size:12px; color:#a5f3fc; letter-spacing:.2em; padding-bottom:14px; border-bottom:1px solid rgba(255,255,255,0.06);">Security &amp; Consent Matrix</p>'
            '  <div class="qv-consent-box" style="margin-top:18px;">'
            '    "Since this whole setup or thing is free, I have to acknowledge this AI (API) conversation is used to improve other models. Sorry I could not find a free and secure one so."'
            '  </div>'
            '  <div class="qv-terms qv-scroll">'
            '    <p><strong>1. AI Model Training (Required):</strong> Your conversation transcripts and speech audio are processed by the free-tier API provider to train and refine future AI models. This data improves Google AI models, NOT a private model.</p>'
            '    <p style="margin-top:10px;"><strong>2. Developer Data Sharing (Optional):</strong> Opting in shares system logs, telemetry, and camera/screen vision data with the developer team for model improvement, debugging, and community protections.</p>'
            '    <p style="margin-top:10px;"><strong>3. System Limits:</strong> If you decline developer sharing, a strict 10-minute daily session limit is enforced and automated media streams are blocked.</p>'
            '    <p style="margin-top:10px;"><strong>4. Independent Safety Reporting:</strong> The REPORT function stays active at all times. Critical safety reports are sent to developers regardless of optional sharing.</p>'
            '  </div>'
            '  <label class="qv-consent-opt" id="qv-consent-ai">'
            '    <input type="checkbox" id="qv-consent-ai-cb" style="margin-top:4px; accent-color:#06b6d4;" />'
            '    <div><p style="font-size:12px; font-weight:600;">AI Data Training Agreement <span style="color:#fb7185; font-size:9px;">(REQUIRED)</span></p>'
            '    <p style="margin-top:2px; font-size:10px; color:rgba(255,255,255,0.4);">Acknowledge that conversations train future AI models.</p></div>'
            '  </label>'
            '  <label class="qv-consent-opt" id="qv-consent-dev">'
            '    <input type="checkbox" id="qv-consent-dev-cb" style="margin-top:4px; accent-color:#06b6d4;" />'
            '    <div><p style="font-size:12px; font-weight:600;">Share Data with Developer <span style="color:#67e8f9; font-size:9px;">(OPTIONAL)</span></p>'
            '    <p style="margin-top:2px; font-size:10px; color:rgba(255,255,255,0.4);">Share logs, camera, and screen captures. Unlocks unlimited connection time and media relays.</p></div>'
            '  </label>'
            '  <div class="qv-dialog-actions">'
            '    <button class="qv-action-secondary" id="qv-consent-cancel">Cancel</button>'
            '    <button class="qv-action-secondary" id="qv-consent-acceptall">Accept All</button>'
            '    <button class="qv-action-primary" id="qv-consent-connect">CONNECT</button>'
            '  </div>'
            '</div>'
        )
        shell.appendChild(consent)
        self.el["consent"] = consent
        self.el["consent_ai_cb"] = consent.querySelector("#qv-consent-ai-cb")
        self.el["consent_dev_cb"] = consent.querySelector("#qv-consent-dev-cb")
        consent.querySelector("#qv-consent-cancel").addEventListener("click", proxy(lambda e: self._handle_consent_cancel()))
        consent.querySelector("#qv-consent-acceptall").addEventListener("click", proxy(lambda e: self._consent_accept_all()))
        consent.querySelector("#qv-consent-connect").addEventListener("click", proxy(lambda e: asyncio.ensure_future(self._consent_submit())))
        for cb_id, opt_id in (("#qv-consent-ai-cb", "#qv-consent-ai"), ("#qv-consent-dev-cb", "#qv-consent-dev")):
            consent.querySelector(cb_id).addEventListener("change", proxy(lambda e: self._render_consent()))

        # Recording consent dialog
        rec = document.createElement("div")
        rec.className = "qv-overlay qv-hidden"
        rec.id = "qv-recording"
        rec.innerHTML = (
            '<div class="qv-dialog qv-dialog-cyan">'
            '  <p class="qv-mono" style="font-size:12px; color:#a5f3fc; letter-spacing:.2em;">Media Stream Access Consent</p>'
            '  <h3 style="margin:14px 0 12px; font-size:18px; color:#22d3ee; font-family:ui-monospace,monospace;">Enable Recording &amp; Streaming?</h3>'
            '  <p style="font-size:13px; line-height:1.6; color:#cbd5e1; font-family:ui-monospace,monospace;">Riko requires access to your microphone (and camera/screen if enabled) to capture and stream real-time audio and video to the AI service. No media is stored permanently unless developer telemetry sharing is explicitly authorized.</p>'
            '  <div class="qv-dialog-actions" style="margin-top:24px;">'
            '    <button class="qv-action-secondary" id="qv-rec-cancel">Cancel</button>'
            '    <button class="qv-action-primary" id="qv-rec-confirm">Consent &amp; Connect</button>'
            '  </div>'
            '</div>'
        )
        shell.appendChild(rec)
        self.el["recording"] = rec
        rec.querySelector("#qv-rec-cancel").addEventListener("click", proxy(lambda e: self._set_recording_dialog(False)))
        rec.querySelector("#qv-rec-confirm").addEventListener("click", proxy(lambda e: asyncio.ensure_future(self._confirm_recording_consent())))

        # Daily limit expired dialog
        limit = document.createElement("div")
        limit.className = "qv-overlay qv-hidden"
        limit.id = "qv-limit"
        limit.style.background = "rgba(0,0,0,0.6)"
        limit.innerHTML = (
            '<div class="qv-dialog qv-dialog-rose">'
            '  <p class="qv-mono" style="font-size:12px; color:#fecdd3; letter-spacing:.2em;">Access Matrix Expired</p>'
            '  <h3 style="margin:14px 0 12px; font-size:18px; color:#fb7185; font-family:ui-monospace,monospace;">Daily Free Limit Reached</h3>'
            '  <p style="font-size:13px; line-height:1.6; color:#cbd5e1; font-family:ui-monospace,monospace;">Your daily 10-minute free conversation time has ended. Since the platform uses a free API provider, we require developer telemetry to offer unlimited access. By sharing telemetry, you get unlimited usage!</p>'
            '  <div style="display:flex; flex-direction:column; gap:12px; margin-top:24px;">'
            '    <button class="qv-action-primary" id="qv-limit-enable">Enable Sharing &amp; Connect (Unlimited)</button>'
            '    <button class="qv-action-secondary" id="qv-limit-dismiss">Dismiss</button>'
            '  </div>'
            '</div>'
        )
        shell.appendChild(limit)
        self.el["limit"] = limit
        limit.querySelector("#qv-limit-enable").addEventListener("click", proxy(lambda e: asyncio.ensure_future(self.enable_dev_sharing_and_connect())))
        limit.querySelector("#qv-limit-dismiss").addEventListener("click", proxy(lambda e: self._set_daily_limit_dialog(False)))

    def _set_consent_dialog(self, visible):
        if visible:
            self.el["consent_ai_cb"].checked = self.consent_ai_training
            self.el["consent_dev_cb"].checked = self.consent_dev_sharing
            self._render_consent()
            self.el["consent"].classList.remove("qv-hidden")
        else:
            self.el["consent"].classList.add("qv-hidden")

    def _render_consent(self):
        ai = self.el["consent_ai_cb"].checked
        dev = self.el["consent_dev_cb"].checked
        self.el["consent"].querySelector("#qv-consent-ai").className = "qv-consent-opt" + (" qv-checked" if ai else "")
        self.el["consent"].querySelector("#qv-consent-dev").className = "qv-consent-opt" + (" qv-checked" if dev else "")
        self.el["consent"].querySelector("#qv-consent-connect").disabled = not ai

    def _consent_accept_all(self):
        self.el["consent_ai_cb"].checked = True
        self.el["consent_dev_cb"].checked = True
        self._render_consent()
        asyncio.ensure_future(self._consent_submit())

    async def _consent_submit(self):
        ai = bool(self.el["consent_ai_cb"].checked)
        dev = bool(self.el["consent_dev_cb"].checked)
        if not ai:
            return
        self._set_consent_dialog(False)
        self.consent_ai_training = ai
        self.consent_dev_sharing = dev
        _ls_set("vrm_consent_ai_training", "true" if ai else "false")
        _ls_set("vrm_consent_developer_sharing", "true" if dev else "false")
        self._render_settings()
        self._set_recording_dialog(True)

    def _handle_consent_cancel(self):
        self._set_consent_dialog(False)

    def _set_recording_dialog(self, visible):
        if visible:
            self.el["recording"].classList.remove("qv-hidden")
        else:
            self.el["recording"].classList.add("qv-hidden")

    async def _confirm_recording_consent(self):
        self._set_recording_dialog(False)
        await self.proceed_to_connect()

    def _set_daily_limit_dialog(self, visible):
        if visible:
            self.el["limit"].classList.remove("qv-hidden")
        else:
            self.el["limit"].classList.add("qv-hidden")

    # ----------------------------------------------------------------- #
    # Drag & drop
    # ----------------------------------------------------------------- #
    def _wire_drag_and_drop(self):
        shell = self.el["shell"]

        def handle_drag(event):
            event.preventDefault()
            etype = event.type
            if etype == "dragenter":
                self.drag_depth += 1
                self.el["drag"].classList.remove("qv-hidden")
            elif etype == "dragleave":
                self.drag_depth = max(0, self.drag_depth - 1)
                if self.drag_depth == 0:
                    self.el["drag"].classList.add("qv-hidden")
            elif etype == "dragover":
                self.el["drag"].classList.remove("qv-hidden")

        async def handle_drop(event):
            event.preventDefault()
            self.drag_depth = 0
            self.el["drag"].classList.add("qv-hidden")
            dt = event.dataTransfer
            if dt and dt.files and dt.files.length > 0:
                await self.load_vrm_file(dt.files.item(0))

        for evt in ("dragenter", "dragover", "dragleave"):
            shell.addEventListener(evt, proxy(handle_drag))
        shell.addEventListener("drop", proxy(lambda e: asyncio.ensure_future(handle_drop(e))))

    # ----------------------------------------------------------------- #
    # Panel toggles
    # ----------------------------------------------------------------- #
    def open_persona_manager(self):
        self.show_settings = False
        self.el["settings"].classList.add("qv-hidden")
        self.show_persona_manager = True
        self._persona_reset_draft()
        self._render_persona_dialog()
        self.el["persona_overlay"].classList.remove("qv-hidden")
        self._render_dock()

    def close_persona_manager(self):
        self.show_persona_manager = False
        self.el["persona_overlay"].classList.add("qv-hidden")

    def toggle_chat_panel(self):
        self.show_chat = not self.show_chat
        if self.show_chat:
            self.show_settings = False
            self.show_persona_manager = False
            self.el["settings"].classList.add("qv-hidden")
            self.el["persona_overlay"].classList.add("qv-hidden")
            self.el["chat"].classList.remove("qv-hidden")
            self._render_chat()
        else:
            self.el["chat"].classList.add("qv-hidden")
        self._render_dock()

    def toggle_settings_panel(self):
        self.show_settings = not self.show_settings
        if self.show_settings:
            self.show_chat = False
            self.show_persona_manager = False
            self.el["chat"].classList.add("qv-hidden")
            self.el["persona_overlay"].classList.add("qv-hidden")
            self._render_settings()
            self.el["settings"].classList.remove("qv-hidden")
        else:
            self.el["settings"].classList.add("qv-hidden")
        self._render_dock()

    # ----------------------------------------------------------------- #
    # Settings actions (watchers ported)
    # ----------------------------------------------------------------- #
    def set_avatar_scale(self, value):
        self.avatar_scale = value
        _ls_set("vrm_avatar_scale", str(value))
        if self.system:
            self.system.set_avatar_scale(value)
        if "scale_chip" not in self.el and "settings" in self.el:
            pass
        if "settings" in self.el and not self.el["settings"].classList.contains("qv-hidden"):
            self.el["settings"].querySelector("#qv-scale-chip").textContent = f"{value:.1f}x"

    def set_background_color(self, value):
        normalized = _normalize_hex_color(value, self.background_color)
        if normalized == self.background_color:
            # still sync inputs
            if "bg_color" in self.el:
                self.el["bg_color"].value = self.background_color
                self.el["bg_text"].value = self.background_color
            return
        self.background_color = normalized
        _ls_set(BACKGROUND_COLOR_STORAGE_KEY, normalized)
        if self.system:
            self.system.set_background_color(normalized)
        if "bg_color" in self.el:
            self.el["bg_color"].value = normalized
            self.el["bg_text"].value = normalized
            if not self.el["settings"].classList.contains("qv-hidden"):
                self.el["settings"].querySelector("#qv-bg-chip").textContent = normalized

    def set_look_at_user(self, value):
        self.look_at_user_enabled = value
        _ls_set("vrm_look_at_user", "true" if value else "false")
        if self.system:
            self.system.set_look_at_options({"user": value, "screen": self.look_at_screen_enabled})
        self.show_toast(self.t("toasts.lookAtUserTitle"),
                        self.t("toasts.lookAtUserEnabled") if value else self.t("toasts.lookAtUserDisabled"), "info")
        self._render_settings()

    def set_look_at_screen(self, value):
        self.look_at_screen_enabled = value
        _ls_set("vrm_look_at_screen", "true" if value else "false")
        if self.system:
            self.system.set_look_at_options({"user": self.look_at_user_enabled, "screen": value})
        self.show_toast(self.t("toasts.lookAtScreenTitle"),
                        self.t("toasts.lookAtScreenEnabled") if value else self.t("toasts.lookAtScreenDisabled"), "info")
        self._render_settings()

    def set_language(self, value):
        resolved = resolve_language(value)
        previous = self.selected_language
        self.selected_language = resolved
        _ls_set(UI_LANGUAGE_STORAGE_KEY, resolved)
        # rebuild personas labels for new language
        custom = [p for p in self.personas if not p.get("isBuiltin") and not _is_builtin_persona_id(p["id"])]
        self.personas = merge_builtins_with_custom(custom, resolved)
        # re-render everything that has text
        self._render_hud()
        self._render_dock()
        self._render_settings()
        self._render_chat()
        if self.show_persona_manager:
            self._render_persona_dialog()
        if self.el["drag"]:
            self.el["shell"].querySelector("#qv-drag-hint").textContent = self.t("app.dragAndDrop")
            self.el["shell"].querySelector("#qv-drag-title").textContent = self.t("app.uploadAvatar")
        if previous == resolved:
            return
        if self.is_connected and self.system and getattr(self.system.ai_client, "is_session_open", False):
            async def send_hint():
                try:
                    await self.system.ai_client.send_text(build_ai_runtime_language_hint(resolved), True)
                    self.show_toast(self.t("toasts.languageChangedTitle"), self.t("toasts.languageChangedMessage"), "info")
                except Exception:  # noqa: BLE001
                    self.show_toast(self.t("toasts.languageChangeFailedTitle"),
                                    self.t("toasts.languageChangeFailedMessage"), "warning")
            asyncio.ensure_future(send_hint())

    def toggle_consent_dev_sharing(self):
        self.consent_dev_sharing = not self.consent_dev_sharing
        _ls_set("vrm_consent_developer_sharing", "true" if self.consent_dev_sharing else "false")
        if self.consent_dev_sharing:
            self.clear_session_limit_timer()
            self.show_toast("Unlimited Access", "Developer data sharing enabled. 10-minute daily limit removed.", "success")
        else:
            if self.is_connected:
                self.start_session_limit_timer()
                self.show_toast("Daily Limit Enforced", "Developer data sharing disabled. 10-minute daily limit active.", "warning")
        self._render_settings()
        self._render_hud()

    async def enable_dev_sharing_and_connect(self):
        self._set_daily_limit_dialog(False)
        self.consent_dev_sharing = True
        _ls_set("vrm_consent_developer_sharing", "true")
        self.show_toast("Unlimited Access", "Developer data sharing enabled. Enjoy unlimited connection time!", "success")
        self._render_settings()
        if not self.is_connected and not self.is_connecting:
            await self.proceed_to_connect()

    # ----------------------------------------------------------------- #
    # Connect / disconnect flow
    # ----------------------------------------------------------------- #
    async def toggle_connection(self):
        if not self.system or not self.system_ready or self.is_connecting:
            return
        if not getattr(self.system, "vrm", None):
            self.show_toast(self.t("toasts.noAvatarTitle"), self.t("toasts.noAvatarMessage"), "error")
            return
        if self.is_connected:
            try:
                self.system.ai_client.disconnect("User ended call")
            except Exception:  # noqa: BLE001
                pass
            self.is_connected = False
            self.clear_session_limit_timer()
            self._render_dock()
            self._render_hud()
            return
        if not self.consent_ai_training:
            self._set_consent_dialog(True)
            return
        self._set_recording_dialog(True)

    def _build_token_provider(self):
        async def provider():
            from pyodide.http import pyfetch
            res = await pyfetch("/api/get-token")
            if not res.ok:
                raise RuntimeError(f"Token generation failed: {res.status}")
            data = json.loads(await res.string())
            token = data.get("token")
            if not token:
                raise RuntimeError("No token returned from server")
            return token
        return provider

    async def proceed_to_connect(self):
        if not self.consent_dev_sharing:
            remaining = self.get_daily_limit_remaining_ms()
            if remaining <= 0:
                self.show_toast("Daily Limit Reached",
                                "Your daily 10-minute limit has expired. Please consent to sharing developer data for unlimited access.",
                                "warning")
                self.is_connecting = False
                self._set_daily_limit_dialog(True)
                return

        self.show_toast(self.t("toasts.connectingTitle"), self.t("toasts.connectingMessage"), "info")
        self.is_connecting = True
        self._render_dock()

        user_name = _ls_get("vrm_user_name", "") or ""
        callbacks = self._build_callbacks()
        try:
            await self.system.connect(
                self.chat_history,
                callbacks,
                "",
                True,
                _ls_get("vrm_user_name"),
                {"userId": self.user_debug_id, "sessionId": self.session_debug_id, "userName": user_name.strip()},
                self.selected_persona_prompt(),
                self.selected_language,
                self._build_token_provider(),
            )
            self.is_connected = True
            self.start_session_limit_timer()
        except Exception as error:  # noqa: BLE001
            console.error(str(error))
            self.clear_session_limit_timer()
            self.track_reconnect_issue()
            self.show_toast(self.t("toasts.connectionFailedTitle"), str(error), "error")
            self.is_connected = False
        finally:
            self.is_connecting = False
            self._render_dock()
            self._render_hud()

    def _build_callbacks(self):
        def on_user_name_set(name):
            _ls_set("vrm_user_name", name)
            if self.system and getattr(self.system, "telegram_manager", None):
                self.system.telegram_manager.set_debug_identity(
                    {"userName": name, "userId": self.user_debug_id, "sessionId": self.session_debug_id})

        def on_memory_saved(key, value):
            try:
                memories = json.loads(_ls_get("vrm_user_memories", "{}") or "{}")
            except Exception:  # noqa: BLE001
                memories = {}
            memories[key] = value
            _ls_set("vrm_user_memories", json.dumps(memories))

        def on_memory_deleted(key):
            try:
                memories = json.loads(_ls_get("vrm_user_memories", "{}") or "{}")
            except Exception:  # noqa: BLE001
                memories = {}
            memories.pop(key, None)
            _ls_set("vrm_user_memories", json.dumps(memories))

        def on_system_message(title, msg, type_="info"):
            self.show_toast(title, msg, type_)

        def on_set_background_image(url):
            if self.system:
                self.system.set_background_image(url)

        def on_disconnect(reason):
            self.active_user_entry_id = None
            self.active_model_entry_id = None
            self.is_connected = False
            self.clear_session_limit_timer()
            self.track_reconnect_issue()
            self._render_dock()
            self._render_hud()
            if reason == "AI ended the conversation":
                announcement = self.t("toasts.aiEndedCall")
                self.show_toast(self.t("toasts.callEndedTitle"), announcement, "info")
                try:
                    synth = getattr(window, "speechSynthesis", None)
                    if synth:
                        synth.cancel()
                        utt = window.SpeechSynthesisUtterance.new(announcement)
                        lang = self.selected_language or "en"
                        utt.lang = {"uz": "uz-UZ", "ru": "ru-RU"}.get(lang, "en-US")
                        utt.volume = 0.8
                        utt.rate = 1.0
                        synth.speak(utt)
                except Exception:  # noqa: BLE001
                    pass
            else:
                self.show_toast(self.t("toasts.callEndedTitle"), reason, "info")

        def on_transcription(role, text, is_final, meta=None):
            normalized_role = "user" if role == "user" else "model"
            normalized_text = _sanitize_transcript_text(text)
            if not normalized_text:
                return
            meta = meta or {}
            try:
                source = meta.get("source", "")
            except AttributeError:
                source = getattr(meta, "source", "") or ""
            if source in ("gemini_input", "gemini_output"):
                self._set_history(self._upsert_gemini_transcript(list(self.chat_history), normalized_role, normalized_text, is_final))
                return
            new_history = list(self.chat_history)
            last = new_history[-1] if new_history else None
            if not is_final and last and last.get("role") == normalized_role:
                last["text"] = normalized_text
                last["timestamp"] = _now()
                self._set_history(new_history)
                return
            if is_final:
                if normalized_role == "user" and last and last.get("role") == "user":
                    last["text"] = normalized_text
                    last["timestamp"] = _now()
                    self._set_history(new_history)
                    return
                if (normalized_role == "model" and last and last.get("role") == normalized_role
                        and normalized_text.startswith(last.get("text", "")[:10])):
                    last["text"] = normalized_text
                    last["timestamp"] = _now()
                    self._set_history(new_history)
                    return
                new_history.append(self._create_history_entry(normalized_role, normalized_text))
                self._set_history(new_history)
                return
            new_history.append(self._create_history_entry(normalized_role, normalized_text))
            self._set_history(new_history)

        def get_history():
            return self.chat_history

        return {
            "onUserNameSet": on_user_name_set,
            "onMemorySaved": on_memory_saved,
            "onMemoryDeleted": on_memory_deleted,
            "onSystemMessage": on_system_message,
            "onTimerStart": self.handle_ai_timer_start,
            "onTimerCancel": self.handle_ai_timer_cancel,
            "onSetBackgroundImage": on_set_background_image,
            "onDisconnect": on_disconnect,
            "onTranscription": on_transcription,
            "onHistoryChange": None,
            "getHistory": get_history,
        }

    async def toggle_screen_share(self):
        if not self.system or not self.system_ready:
            return
        if self.is_sharing_screen:
            await self.system.stop_screen_share()
            return
        try:
            started = await self.system.start_screen_share()
            if not started:
                self.show_toast(self.t("toasts.screenShareTitle"), self.t("toasts.screenShareCouldNotStart"), "error")
        except Exception:  # noqa: BLE001
            self.show_toast(self.t("toasts.screenShareTitle"), self.t("toasts.screenSharePermissionBlocked"), "error")

    def clear_history(self):
        self.active_user_entry_id = None
        self.active_model_entry_id = None
        if self.system and getattr(self.system, "ai_client", None):
            clear_fn = getattr(self.system.ai_client, "clear_session_resumption", None)
            if callable(clear_fn):
                try:
                    clear_fn()
                except Exception:  # noqa: BLE001
                    pass
        self.chat_history = []
        localStorage.removeItem("vrm_chat_history")
        self._render_chat()
        if self.is_connected:
            try:
                self.system.ai_client.disconnect("Chat history cleared by user")
            except Exception:  # noqa: BLE001
                pass
            self.is_connected = False
            self._render_dock()
            self._render_hud()

    # ----------------------------------------------------------------- #
    # VRM upload + model management
    # ----------------------------------------------------------------- #
    async def _list_user_models(self):
        """Best-effort list of cached *user* VRM models.

        The Python cache_manager singleton exposes get_all / list_keys (it does
        NOT have the Vue ``getMetadataAll`` helper). We adapt here and tolerate
        records that don't carry the expected ``{key, meta:{type,name,date}}``
        shape, so the settings model list degrades gracefully.
        """
        try:
            records = await cache_manager.get_all("models")
        except Exception as error:  # noqa: BLE001
            console.warn("Failed to list cached models", str(error))
            return []
        out = []
        for rec in (list(records) if records is not None else []):
            try:
                key = rec.get("key") if isinstance(rec, dict) else getattr(rec, "key", None)
                meta = rec.get("meta") if isinstance(rec, dict) else getattr(rec, "meta", None)
                mtype = (meta.get("type") if isinstance(meta, dict) else getattr(meta, "type", None)) if meta else None
                if mtype != "user":
                    continue
                name = (meta.get("name") if isinstance(meta, dict) else getattr(meta, "name", None)) if meta else None
                date = (meta.get("date") if isinstance(meta, dict) else getattr(meta, "date", 0)) if meta else 0
                out.append({"key": key, "meta": {"name": name, "date": date or 0}})
            except Exception:  # noqa: BLE001
                continue
        out.sort(key=lambda x: x["meta"].get("date") or 0, reverse=True)
        return out

    async def refresh_models(self):
        self.available_models = await self._list_user_models()
        self._render_model_list()

    async def handle_model_switch(self, model_key):
        if not self.system:
            return
        if not model_key:
            await self.load_vrm_file({"name": "Default", "url": "/models/riko.vrm"}, True)
            self.selected_model_key = None
            localStorage.removeItem("vrm_selected_model_key")
            return
        self.show_toast(self.t("toasts.switchingAvatarTitle"), self.t("toasts.switchingAvatarMessage"), "info")
        try:
            await self.system.load_new_vrm(model_key)
            self.selected_model_key = model_key
            _ls_set("vrm_selected_model_key", model_key)
            self.show_toast(self.t("toasts.avatarUpdatedTitle"), self.t("toasts.avatarLoadedFromCache"), "success")
        except Exception as error:  # noqa: BLE001
            console.error(str(error))
            self.show_toast(self.t("toasts.loadFailedTitle"), self.t("toasts.cachedModelLoadFailed"), "error")

    async def handle_model_delete(self, model_key):
        if not self.system or not model_key:
            return
        if not window.confirm(self.t("toasts.modelDeleteConfirm")):
            return
        try:
            await self.system.delete_model(model_key)
            self.show_toast(self.t("toasts.modelDeletedTitle"), self.t("toasts.modelDeletedMessage"), "success")
            if self.selected_model_key == model_key:
                self.selected_model_key = None
                localStorage.removeItem("vrm_selected_model_key")
            await self.refresh_models()
        except Exception:  # noqa: BLE001
            self.show_toast(self.t("toasts.errorTitle"), self.t("toasts.modelDeleteFailed"), "error")

    async def load_vrm_file(self, file, is_url=False):
        if is_url:
            file_name = file.get("name", "") if isinstance(file, dict) else "Default"
        else:
            file_name = getattr(file, "name", "") or ""
            if not file_name.lower().endswith(".vrm"):
                self.show_toast(self.t("toasts.invalidFileTitle"), self.t("toasts.invalidFileMessage"), "error")
                return
        self.show_toast(self.t("toasts.loadingAvatarTitle"),
                        self.t("toasts.loadingAvatarMessage", {"fileName": file_name or self.t("settings.defaultRiko")}), "info")
        try:
            # delete old user models on a fresh upload
            if not is_url:
                try:
                    for m in await self._list_user_models():
                        if m.get("key"):
                            await self.system.delete_model(m["key"])
                    self.available_models = []
                    self._render_model_list()
                except Exception as e:  # noqa: BLE001
                    console.warn("Failed to cleanup old models", str(e))

            if is_url:
                url = file.get("url") if isinstance(file, dict) else None
                await self.system.load_new_vrm(url)
            else:
                await self.system.load_new_vrm(file)
            if not self.system_ready and getattr(self.system, "vrm", None):
                self.system_ready = True
                self.system.set_avatar_scale(self.avatar_scale)
                self._render_dock()
                self._render_hud()
            self.show_toast(self.t("toasts.avatarUpdatedTitle"), self.t("toasts.newAvatarLoaded"), "success")
            await self.refresh_models()
            if not is_url and self.available_models:
                newest = self.available_models[0]
                if _now() - (newest["meta"].get("date") or 0) < 5000:
                    self.selected_model_key = newest["key"]
                    _ls_set("vrm_selected_model_key", newest["key"])
        except Exception:  # noqa: BLE001
            self.show_toast(self.t("toasts.loadFailedTitle"), self.t("toasts.vrmLoadFailed"), "error")

    # ----------------------------------------------------------------- #
    # Boot the 3D system (port of onMounted)
    # ----------------------------------------------------------------- #
    async def boot_system(self):
        self.update_loading_state({"progress": 8, "stage": "Booting Engine", "detail": "Initializing client"})

        # init persistent device id
        async def init_fingerprint():
            try:
                fp = await generate_device_fingerprint()
                self.user_debug_id = fp
                _ls_set(DEBUG_USER_ID_STORAGE_KEY, fp)
                if self.system and getattr(self.system, "telegram_manager", None):
                    self.system.telegram_manager.set_debug_identity({"userId": fp})
            except Exception:  # noqa: BLE001
                pass
        asyncio.ensure_future(init_fingerprint())

        initial_user_name = (_ls_get("vrm_user_name", "") or "").strip()

        def on_speech_start():
            self.assistant_speaking = True
            _clear_timeout(self.timer_pending_fallback_timeout)
            self.timer_pending_fallback_timeout = None

        def on_speech_end(meta=None):
            self.assistant_speaking = False
            _clear_timeout(self.timer_pending_fallback_timeout)
            self.timer_pending_fallback_timeout = None
            interrupted = False
            if meta is not None:
                try:
                    interrupted = bool(meta.get("interrupted"))
                except AttributeError:
                    interrupted = bool(getattr(meta, "interrupted", False))
            if interrupted:
                self.pending_timer_start = None
                return
            self.handle_assistant_speech_end()

        options = {
            "onLoadProgress": self.update_loading_state,
            "onAssistantSpeechStart": on_speech_start,
            "onAssistantSpeechEnd": on_speech_end,
            "debugIdentity": {"userId": self.user_debug_id, "sessionId": self.session_debug_id, "userName": initial_user_name},
        }

        try:
            sys = await create_vrm_chat_system(self.el["canvas"], options)
            self.system = sys
            self.cleanup_system = sys.cleanup
            sys.set_background_color(self.background_color)
            sys.set_look_at_options({"user": self.look_at_user_enabled, "screen": self.look_at_screen_enabled})

            def on_vision_state(is_active):
                self.is_sharing_screen = is_active
                self.show_toast(self.t("toasts.screenShareTitle"),
                                self.t("toasts.screenShareActive") if is_active else self.t("toasts.screenShareStopped"),
                                "success" if is_active else "info")
                self._render_dock()
                self._render_hud()

            if getattr(sys, "vision_manager", None) is not None:
                sys.vision_manager.on_state_change = on_vision_state

            await self.refresh_models()

            if getattr(sys, "vrm", None):
                if self.selected_model_key:
                    exists = any(m.get("key") == self.selected_model_key for m in self.available_models)
                    if exists:
                        await sys.load_new_vrm(self.selected_model_key)
                    else:
                        self.selected_model_key = None
                        localStorage.removeItem("vrm_selected_model_key")
                self.system_ready = True
                sys.set_avatar_scale(self.avatar_scale)
                self.update_loading_state({"progress": 100, "stage": "System Ready", "detail": "Avatar online"})
            else:
                if self.selected_model_key:
                    try:
                        await sys.load_new_vrm(self.selected_model_key)
                        self.system_ready = True
                        sys.set_avatar_scale(self.avatar_scale)
                        self.update_loading_state({"progress": 100, "stage": "System Ready", "detail": "Restored User Avatar"})
                    except Exception:  # noqa: BLE001
                        self.system_ready = True
                        self.update_loading_state({"progress": 100, "stage": "System Ready", "detail": "Upload a VRM model to continue"})
                        self.show_toast(self.t("toasts.avatarMissingTitle"), self.t("toasts.avatarMissingSaved"), "info")
                else:
                    self.system_ready = True
                    self.update_loading_state({"progress": 100, "stage": "System Ready", "detail": "Upload a VRM model to continue"})
                    self.show_toast(self.t("toasts.avatarMissingTitle"), self.t("toasts.avatarMissingDefault"), "info")
        except Exception as error:  # noqa: BLE001
            console.error(str(error))
            self.update_loading_state({"progress": 100, "stage": "Initialization Failed", "detail": str(error)})
            self.show_toast(self.t("toasts.initializationFailedTitle"), str(error), "error")

        self._render_dock()
        self._render_hud()

        # FPS HUD ticker
        def fps_tick(*_):
            fps = 0
            try:
                sm = getattr(self.system, "scene_manager", None) if self.system else None
                if sm and hasattr(sm, "get_current_fps"):
                    fps = sm.get_current_fps() or 0
            except Exception:  # noqa: BLE001
                fps = 0
            if "fps" in self.el:
                self.el["fps"].textContent = str(int(fps))
        self.fps_interval = _set_interval(fps_tick, 1000)


def _time_fmt():
    from managers.jsutil import obj
    return obj(hour="2-digit", minute="2-digit")


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
_app_instance = None


async def start(mount=None):
    """Construct the whole UI, boot the 3D system and wire every control.

    This is the single entry point the integrator calls from main.py:

        import asyncio
        from ui.app_ui import start
        asyncio.ensure_future(start())

    ``mount`` is an optional DOM element to attach the shell to (defaults to
    ``document.body``). Returns the :class:`AppUI` instance.
    """
    global _app_instance
    app = AppUI()
    _app_instance = app
    window.vrmAppUI = app  # debugging handle
    app.build(mount)
    await app.boot_system()
    return app
