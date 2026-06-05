"""i18n — Python port of src/i18n/ui.js (en / uz / ru translations + helpers)."""

import re

SUPPORTED_LANGUAGES = (
    {"code": "en", "label": "English"},
    {"code": "uz", "label": "O'zbek"},
    {"code": "ru", "label": "Русский"},
)

UI_LANGUAGE_STORAGE_KEY = "vrm_ui_language"

_UI_LANGUAGE_SET = {item["code"] for item in SUPPORTED_LANGUAGES}

UI_MESSAGES = {
    "en": {
        "app": {
            "dragAndDrop": "Drag and Drop", "uploadAvatar": "Upload VRM Avatar",
            "liveSessionActive": "Live Session Active", "systemStandby": "System Standby",
            "voiceLinkStable": "Voice link stable", "connectVoiceVision": "Connect to start voice + vision tools",
            "screenShareEnabled": "Screen share enabled", "renderFps": "Render FPS",
            "sceneReady": "Scene ready", "initializingScene": "Initializing scene",
        },
        "settings": {
            "systemControl": "System Control", "identityMatrix": "Identity Matrix",
            "defaultRiko": "Default Riko", "systemModel": "System Model", "aiPersona": "AI Persona",
            "defaultPersonaDescription": "Original Riko personality used by the app.",
            "unknownModel": "Unknown Model", "editPersonas": "Edit Personas",
            "projectionScale": "Projection Scale", "backgroundColor": "Background Color",
            "visionSensors": "Vision Sensors", "faceTrack": "Face Track", "screenSense": "Screen Sense",
            "languageMode": "Language Mode", "languageHint": "UI + AI reply preference",
            "unknownDate": "Unknown date", "justNow": "Just now", "cachedAgo": "Cached {relative}",
        },
        "dock": {
            "uploadAvatarTitle": "Upload avatar", "upload": "Upload",
            "toggleScreenShareTitle": "Toggle screen share", "screen": "Screen",
            "connecting": "Connecting...", "disconnect": "Disconnect", "connect": "Connect",
            "toggleChatTitle": "Toggle chat", "chat": "Chat", "settingsTitle": "Settings", "settings": "Settings",
        },
        "chat": {
            "conversationLog": "Conversation Log ({count})", "clear": "Clear",
            "noMessagesYet": "No messages yet", "you": "You", "assistant": "Riko",
        },
        "personaDialog": {
            "editPersonas": "Edit Personas", "availablePersonas": "Available Personas", "new": "New",
            "default": "Default", "editPersonaTitle": "Edit persona", "deletePersonaTitle": "Delete persona",
            "editPersona": "Edit Persona", "createPersona": "Create Persona", "cancel": "Cancel",
            "title": "Title", "titlePlaceholder": "Persona title", "shortDescription": "Short Description",
            "summaryPlaceholder": "1-line summary", "personaPrompt": "Persona Prompt",
            "promptPlaceholder": "Describe personality, style, and behavior",
            "saveChanges": "Save Changes", "addPersona": "Add Persona",
            "pickPersonaHint": "Pick a persona and press Edit, or create a new one.",
            "editLockHint": "Editing is locked to this persona. Save or Cancel to edit others.",
        },
        "toasts": {
            "lookAtUserTitle": "Look At User", "lookAtUserEnabled": "AI can now look at you through camera.",
            "lookAtUserDisabled": "AI look-at-user is disabled.", "lookAtScreenTitle": "Look At Screen",
            "lookAtScreenEnabled": "AI can now analyze your shared screen.",
            "lookAtScreenDisabled": "AI look-at-screen is disabled.", "screenShareTitle": "Screen Share",
            "screenShareActive": "Screen sharing active", "screenShareStopped": "Screen sharing stopped",
            "avatarMissingTitle": "Avatar Missing", "avatarMissingSaved": "Saved model not found. Upload a .vrm file.",
            "avatarMissingDefault": "Default model not found. Upload a .vrm file.",
            "initializationFailedTitle": "Initialization Failed", "performanceTipTitle": "Performance Tip",
            "performanceTipMessage": "Frequent reconnects detected. Open chat and clear history to lighten the session.",
            "noAvatarTitle": "No Avatar", "noAvatarMessage": "Load a VRM model before connecting.",
            "connectingTitle": "Connecting", "connectingMessage": "Establishing live voice session...",
            "callEndedTitle": "Call Ended", "aiEndedCall": "AI ended the conversation. Goodbye!",
            "connectionFailedTitle": "Connection Failed", "screenShareCouldNotStart": "Could not start screen sharing.",
            "screenSharePermissionBlocked": "Screen share permission was blocked.",
            "personaQueuedTitle": "Persona Queued", "personaQueuedMessage": "Disconnect and reconnect to apply the new persona.",
            "personaErrorTitle": "Persona Error", "personaRequiredFields": "Title, description, and prompt are required.",
            "personaAddedTitle": "Persona Added", "personaAddedMessage": '"{title}" is ready to use.',
            "personaUpdatedTitle": "Persona Updated", "personaUpdatedMessage": '"{title}" saved.',
            "personaDeleteConfirm": 'Delete persona "{title}"?', "personaDeletedTitle": "Persona Deleted",
            "personaDeletedMessage": '"{title}" removed.', "switchingAvatarTitle": "Switching Avatar",
            "switchingAvatarMessage": "Loading cached model...", "avatarUpdatedTitle": "Avatar Updated",
            "avatarLoadedFromCache": "Model loaded from cache.", "loadFailedTitle": "Load Failed",
            "cachedModelLoadFailed": "Could not load cached model.", "modelDeletedTitle": "Deleted",
            "modelDeletedMessage": "Model removed from cache.", "errorTitle": "Error",
            "modelDeleteFailed": "Failed to delete model.", "modelDeleteConfirm": "Are you sure you want to delete this model?",
            "invalidFileTitle": "Invalid File", "invalidFileMessage": "Please upload a .vrm file.",
            "loadingAvatarTitle": "Loading Avatar", "loadingAvatarMessage": "Processing {fileName}...",
            "newAvatarLoaded": "New model loaded successfully.", "vrmLoadFailed": "Could not load this VRM file.",
            "languageChangedTitle": "Language Updated",
            "languageChangedMessage": "AI language preference will apply in the current session.",
            "languageChangeFailedTitle": "Language Hint Failed",
            "languageChangeFailedMessage": "Language preference was saved. Reconnect to apply it to AI responses.",
        },
        "aiLanguage": {
            "english": "English", "uzbek": "Uzbek", "russian": "Russian",
            "preferenceInstruction": "Preferred response language is {languageName}. This is only a preference, not mandatory. Use it by default when natural, but follow the user language if they switch or explicitly request another language.",
            "runtimeHint": "[SYSTEM LANGUAGE PREFERENCE] Prefer replying in {languageName}. This is a soft preference, not strict. Follow the user language if they switch. Do not ask for confirmation.",
        },
    },
    "uz": {
        "app": {
            "dragAndDrop": "Sudrab olib tashlang", "uploadAvatar": "VRM avatar yuklash",
            "liveSessionActive": "Jonli sessiya faol", "systemStandby": "Tizim kutish holatida",
            "voiceLinkStable": "Ovoz ulanishi barqaror", "connectVoiceVision": "Ovoz va ko'rish vositalarini boshlash uchun ulang",
            "screenShareEnabled": "Ekran ulashish yoqilgan", "renderFps": "Render FPS",
            "sceneReady": "Sahna tayyor", "initializingScene": "Sahna ishga tushmoqda",
        },
        "settings": {
            "systemControl": "Tizim boshqaruvi", "identityMatrix": "Identifikatsiya matriksasi",
            "defaultRiko": "Standart Riko", "systemModel": "Tizim modeli", "aiPersona": "AI personasi",
            "defaultPersonaDescription": "Ilovadagi asl Riko personasi.", "unknownModel": "Noma'lum model",
            "editPersonas": "Personalarni tahrirlash", "projectionScale": "Proeksiya o'lchami",
            "backgroundColor": "Fon rangi", "visionSensors": "Ko'rish sensorlari", "faceTrack": "Yuz kuzatuvi",
            "screenSense": "Ekran sensori", "languageMode": "Til rejimi", "languageHint": "UI + AI javob afzalligi",
            "unknownDate": "Noma'lum sana", "justNow": "Hozirgina", "cachedAgo": "Keshlangan: {relative}",
        },
        "dock": {
            "uploadAvatarTitle": "Avatar yuklash", "upload": "Yuklash",
            "toggleScreenShareTitle": "Ekran ulashishni almashtirish", "screen": "Ekran",
            "connecting": "Ulanmoqda...", "disconnect": "Uzish", "connect": "Ulanish",
            "toggleChatTitle": "Chatni almashtirish", "chat": "Chat", "settingsTitle": "Sozlamalar", "settings": "Sozlamalar",
        },
        "chat": {
            "conversationLog": "Suhbat jurnali ({count})", "clear": "Tozalash",
            "noMessagesYet": "Hali xabarlar yo'q", "you": "Siz", "assistant": "Riko",
        },
        "personaDialog": {
            "editPersonas": "Personalarni tahrirlash", "availablePersonas": "Mavjud personlar", "new": "Yangi",
            "default": "Standart", "editPersonaTitle": "Personani tahrirlash", "deletePersonaTitle": "Personani o'chirish",
            "editPersona": "Personani tahrirlash", "createPersona": "Persona yaratish", "cancel": "Bekor qilish",
            "title": "Sarlavha", "titlePlaceholder": "Persona nomi", "shortDescription": "Qisqa tavsif",
            "summaryPlaceholder": "1 qatorli tavsif", "personaPrompt": "Persona prompti",
            "promptPlaceholder": "Xarakter, uslub va xatti-harakatni yozing", "saveChanges": "O'zgarishlarni saqlash",
            "addPersona": "Persona qo'shish", "pickPersonaHint": "Personani tanlang va Tahrirlashni bosing yoki yangisini yarating.",
            "editLockHint": "Tahrirlash shu personaga qulflangan. Boshqasini tahrirlash uchun Saqlash yoki Bekor qilishni bosing.",
        },
        "toasts": {
            "lookAtUserTitle": "Foydalanuvchiga qarash", "lookAtUserEnabled": "AI endi kamera orqali sizga qaray oladi.",
            "lookAtUserDisabled": "AI foydalanuvchiga qarash o'chirildi.", "lookAtScreenTitle": "Ekranga qarash",
            "lookAtScreenEnabled": "AI endi ulashilgan ekranni tahlil qila oladi.",
            "lookAtScreenDisabled": "AI ekranga qarash o'chirildi.", "screenShareTitle": "Ekran ulashish",
            "screenShareActive": "Ekran ulashish faol", "screenShareStopped": "Ekran ulashish to‘xtatildi",
            "avatarMissingTitle": "Avatar topilmadi", "avatarMissingSaved": "Saqlangan model topilmadi. .vrm fayl yuklang.",
            "avatarMissingDefault": "Standart model topilmadi. .vrm fayl yuklang.",
            "initializationFailedTitle": "Ishga tushirish muvaffaqiyatsiz", "performanceTipTitle": "Performance maslahat",
            "performanceTipMessage": "Ko'p qayta ulanish kuzatildi. Sessiyani yengillashtirish uchun chat tarixini tozalang.",
            "noAvatarTitle": "Avatar yo'q", "noAvatarMessage": "Ulanishdan oldin VRM model yuklang.",
            "connectingTitle": "Ulanmoqda", "connectingMessage": "Jonli ovozli sessiya ochilmoqda...",
            "callEndedTitle": "Qo‘ng‘iroq tugadi", "aiEndedCall": "AI suhbatni yakunladi. Xayr!",
            "connectionFailedTitle": "Ulanish muvaffaqiyatsiz", "screenShareCouldNotStart": "Ekran ulashishni boshlab bo‘lmadi.",
            "screenSharePermissionBlocked": "Ekran ulashish ruxsati rad etildi.",
            "personaQueuedTitle": "Persona navbatga qo‘yildi", "personaQueuedMessage": "Yangi personani qo'llash uchun uzib, qayta uling.",
            "personaErrorTitle": "Persona xatosi", "personaRequiredFields": "Sarlavha, tavsif va prompt majburiy.",
            "personaAddedTitle": "Persona qo'shildi", "personaAddedMessage": '"{title}" foydalanishga tayyor.',
            "personaUpdatedTitle": "Persona yangilandi", "personaUpdatedMessage": '"{title}" saqlandi.',
            "personaDeleteConfirm": '"{title}" personasi o‘chirilsinmi?', "personaDeletedTitle": "Persona o'chirildi",
            "personaDeletedMessage": '"{title}" olib tashlandi.', "switchingAvatarTitle": "Avatar almashtirilmoqda",
            "switchingAvatarMessage": "Keshlangan model yuklanmoqda...", "avatarUpdatedTitle": "Avatar yangilandi",
            "avatarLoadedFromCache": "Model keshdan yuklandi.", "loadFailedTitle": "Yuklash xatosi",
            "cachedModelLoadFailed": "Keshlangan modelni yuklab bo‘lmadi.", "modelDeletedTitle": "O'chirildi",
            "modelDeletedMessage": "Model keshdan olib tashlandi.", "errorTitle": "Xato",
            "modelDeleteFailed": "Modelni o'chirib bo'lmadi.", "modelDeleteConfirm": "Ushbu modelni o'chirishni tasdiqlaysizmi?",
            "invalidFileTitle": "Noto‘g‘ri fayl", "invalidFileMessage": "Iltimos, .vrm fayl yuklang.",
            "loadingAvatarTitle": "Avatar yuklanmoqda", "loadingAvatarMessage": "{fileName} qayta ishlanmoqda...",
            "newAvatarLoaded": "Yangi model muvaffaqiyatli yuklandi.", "vrmLoadFailed": "Ushbu VRM faylni yuklab bo‘lmadi.",
            "languageChangedTitle": "Til yangilandi", "languageChangedMessage": "AI til afzalligi joriy sessiyada qo‘llanadi.",
            "languageChangeFailedTitle": "Til ko‘rsatmasi yuborilmadi",
            "languageChangeFailedMessage": "Til saqlandi. AI javoblariga qo‘llash uchun qayta ulanishingiz mumkin.",
        },
        "aiLanguage": {
            "english": "Ingliz tili", "uzbek": "O'zbek tili", "russian": "Rus tili",
            "preferenceInstruction": "Afzal javob tili: {languageName}. Bu majburiy emas, faqat tavsiya. Odatda shu tilda javob bering, lekin foydalanuvchi tilni almashtirsa yoki boshqa tilni so'rasa, moslashing.",
            "runtimeHint": "[SYSTEM LANGUAGE PREFERENCE] Javoblarda asosan {languageName} tilidan foydalaning. Bu yumshoq afzallik, qatʼiy emas. Foydalanuvchi tilni almashtirsa moslashing. Tasdiq so‘ramang.",
        },
    },
    "ru": {
        "app": {
            "dragAndDrop": "Перетащите файл", "uploadAvatar": "Загрузить VRM аватар",
            "liveSessionActive": "Сессия активна", "systemStandby": "Система в режиме ожидания",
            "voiceLinkStable": "Голосовое соединение стабильно",
            "connectVoiceVision": "Подключитесь, чтобы запустить голос и визуальные инструменты",
            "screenShareEnabled": "Демонстрация экрана включена", "renderFps": "Render FPS",
            "sceneReady": "Сцена готова", "initializingScene": "Инициализация сцены",
        },
        "settings": {
            "systemControl": "Управление системой", "identityMatrix": "Матрица идентичности",
            "defaultRiko": "Riko по умолчанию", "systemModel": "Системная модель", "aiPersona": "Персона AI",
            "defaultPersonaDescription": "Оригинальная персона Riko, используемая в приложении.",
            "unknownModel": "Неизвестная модель", "editPersonas": "Редактировать персоны",
            "projectionScale": "Масштаб проекции", "backgroundColor": "Цвет фона",
            "visionSensors": "Визуальные сенсоры", "faceTrack": "Отслеживание лица", "screenSense": "Анализ экрана",
            "languageMode": "Режим языка", "languageHint": "UI + предпочтение ответа AI",
            "unknownDate": "Дата неизвестна", "justNow": "Только что", "cachedAgo": "Кэшировано: {relative}",
        },
        "dock": {
            "uploadAvatarTitle": "Загрузить аватар", "upload": "Загрузка",
            "toggleScreenShareTitle": "Переключить демонстрацию экрана", "screen": "Экран",
            "connecting": "Подключение...", "disconnect": "Отключить", "connect": "Подключить",
            "toggleChatTitle": "Переключить чат", "chat": "Чат", "settingsTitle": "Настройки", "settings": "Настройки",
        },
        "chat": {
            "conversationLog": "Журнал диалога ({count})", "clear": "Очистить",
            "noMessagesYet": "Сообщений пока нет", "you": "Вы", "assistant": "Riko",
        },
        "personaDialog": {
            "editPersonas": "Редактировать персоны", "availablePersonas": "Доступные персоны", "new": "Новая",
            "default": "По умолчанию", "editPersonaTitle": "Редактировать персону", "deletePersonaTitle": "Удалить персону",
            "editPersona": "Редактирование персоны", "createPersona": "Создание персоны", "cancel": "Отмена",
            "title": "Название", "titlePlaceholder": "Название персоны", "shortDescription": "Краткое описание",
            "summaryPlaceholder": "Краткая строка", "personaPrompt": "Промпт персоны",
            "promptPlaceholder": "Опишите характер, стиль и поведение", "saveChanges": "Сохранить изменения",
            "addPersona": "Добавить персону", "pickPersonaHint": "Выберите персону и нажмите Edit, либо создайте новую.",
            "editLockHint": "Редактирование заблокировано для этой персоны. Сохраните или отмените, чтобы редактировать другие.",
        },
        "toasts": {
            "lookAtUserTitle": "Взгляд на пользователя", "lookAtUserEnabled": "AI теперь может видеть вас через камеру.",
            "lookAtUserDisabled": "Взгляд на пользователя отключен.", "lookAtScreenTitle": "Взгляд на экран",
            "lookAtScreenEnabled": "AI теперь может анализировать ваш экран.",
            "lookAtScreenDisabled": "Взгляд на экран отключен.", "screenShareTitle": "Демонстрация экрана",
            "screenShareActive": "Демонстрация экрана активна", "screenShareStopped": "Демонстрация экрана остановлена",
            "avatarMissingTitle": "Аватар не найден", "avatarMissingSaved": "Сохраненная модель не найдена. Загрузите .vrm файл.",
            "avatarMissingDefault": "Модель по умолчанию не найдена. Загрузите .vrm файл.",
            "initializationFailedTitle": "Ошибка инициализации", "performanceTipTitle": "Совет по производительности",
            "performanceTipMessage": "Обнаружены частые переподключения. Откройте чат и очистите историю.",
            "noAvatarTitle": "Нет аватара", "noAvatarMessage": "Загрузите VRM модель перед подключением.",
            "connectingTitle": "Подключение", "connectingMessage": "Запускаем живую голосовую сессию...",
            "callEndedTitle": "Звонок завершен", "aiEndedCall": "AI завершил беседу. До свидания!",
            "connectionFailedTitle": "Ошибка подключения", "screenShareCouldNotStart": "Не удалось запустить демонстрацию экрана.",
            "screenSharePermissionBlocked": "Доступ к демонстрации экрана заблокирован.",
            "personaQueuedTitle": "Персона в очереди", "personaQueuedMessage": "Переподключитесь, чтобы применить новую персону.",
            "personaErrorTitle": "Ошибка персоны", "personaRequiredFields": "Название, описание и промпт обязательны.",
            "personaAddedTitle": "Персона добавлена", "personaAddedMessage": '"{title}" готова к использованию.',
            "personaUpdatedTitle": "Персона обновлена", "personaUpdatedMessage": '"{title}" сохранена.',
            "personaDeleteConfirm": 'Удалить персону "{title}"?', "personaDeletedTitle": "Персона удалена",
            "personaDeletedMessage": '"{title}" удалена.', "switchingAvatarTitle": "Смена аватара",
            "switchingAvatarMessage": "Загрузка модели из кэша...", "avatarUpdatedTitle": "Аватар обновлен",
            "avatarLoadedFromCache": "Модель загружена из кэша.", "loadFailedTitle": "Ошибка загрузки",
            "cachedModelLoadFailed": "Не удалось загрузить модель из кэша.", "modelDeletedTitle": "Удалено",
            "modelDeletedMessage": "Модель удалена из кэша.", "errorTitle": "Ошибка",
            "modelDeleteFailed": "Не удалось удалить модель.", "modelDeleteConfirm": "Удалить эту модель?",
            "invalidFileTitle": "Неверный файл", "invalidFileMessage": "Пожалуйста, загрузите .vrm файл.",
            "loadingAvatarTitle": "Загрузка аватара", "loadingAvatarMessage": "Обрабатывается {fileName}...",
            "newAvatarLoaded": "Новая модель успешно загружена.", "vrmLoadFailed": "Не удалось загрузить этот VRM файл.",
            "languageChangedTitle": "Язык обновлен", "languageChangedMessage": "Языковое предпочтение AI применится в текущей сессии.",
            "languageChangeFailedTitle": "Подсказка языка не отправлена",
            "languageChangeFailedMessage": "Язык сохранен. Переподключитесь, чтобы точно применить его к ответам AI.",
        },
        "aiLanguage": {
            "english": "Английский", "uzbek": "Узбекский", "russian": "Русский",
            "preferenceInstruction": "Предпочтительный язык ответа: {languageName}. Это не строгое требование, а рекомендация. Обычно отвечай на этом языке, но если пользователь переключится или попросит другой язык, адаптируйся.",
            "runtimeHint": "[SYSTEM LANGUAGE PREFERENCE] Предпочитай ответы на {languageName}. Это мягкое предпочтение, не строгое правило. Если пользователь сменит язык, адаптируйся. Подтверждение не требуется.",
        },
    },
}


def _resolve_path(source, path):
    if not source or not isinstance(path, str) or not path:
        return None
    acc = source
    for part in path.split("."):
        if isinstance(acc, dict) and part in acc:
            acc = acc[part]
        else:
            return None
    return acc


def resolve_language(language):
    normalized = language.strip().lower() if isinstance(language, str) else ""
    return normalized if normalized in _UI_LANGUAGE_SET else "en"


def get_locale_for_language(language):
    normalized = resolve_language(language)
    if normalized == "uz":
        return "uz-UZ"
    if normalized == "ru":
        return "ru-RU"
    return "en-US"


def translate_ui(language, key, params=None):
    params = params or {}
    normalized = resolve_language(language)
    from_language = _resolve_path(UI_MESSAGES.get(normalized), key)
    from_english = _resolve_path(UI_MESSAGES["en"], key)
    template = from_language if isinstance(from_language, str) else from_english
    if not isinstance(template, str):
        return key

    def repl(m):
        token = m.group(1)
        if token in params:
            value = params[token]
            return "" if value is None else str(value)
        return ""

    return re.sub(r"\{(\w+)\}", repl, template)


def get_ai_language_name(language):
    normalized = resolve_language(language)
    if normalized == "uz":
        return "Uzbek"
    if normalized == "ru":
        return "Russian"
    return "English"


def build_ai_language_preference_instruction(language):
    normalized = resolve_language(language)
    language_name = get_ai_language_name(normalized)
    return translate_ui("en", "aiLanguage.preferenceInstruction", {"languageName": language_name})


def build_ai_runtime_language_hint(language):
    normalized = resolve_language(language)
    language_name = get_ai_language_name(normalized)
    return translate_ui("en", "aiLanguage.runtimeHint", {"languageName": language_name})
