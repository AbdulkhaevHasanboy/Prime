"""AIClient — Python port of managers/aiClient.js.

The Gemini Live WebRTC/WebSocket client. The wire protocol is handled entirely by
the JS @google/genai SDK (exposed on ``window.GoogleGenAI``). Python orchestrates:
it constructs the SDK objects, drives ``session.sendRealtimeInput`` /
``sendToolResponse`` / ``sendClientContent``, captures the microphone via the Web
Audio API, decodes inbound audio, and dispatches tool calls — all via Pyodide
interop.

Conventions (see jsutil.py):
- ``obj(**kw)`` / ``js_dict(dict)`` build plain JS objects (NOT Maps).
- ``proxy(fn)`` wraps a Python callable as a persistent JS callback (required for
  anything handed into JS: SDK callbacks, setTimeout, AudioWorklet port handlers).
- Browser globals come from the ``js`` module (``window``, ``console``, ...).

Callbacks supplied by the orchestrator (``on_audio_data`` etc.) are plain Python
callables. They are invoked directly. Inbound SDK messages are JS proxy objects;
attributes are read with the ``_jget`` helper which mirrors JS optional chaining.

Method names are snake_case, with camelCase aliases kept where the orchestrator
(index.js) calls them, so wiring is trivial.
"""

import base64 as _b64
import math
import random
import time

from js import window, console
from pyodide.ffi import to_js, JsException

from .jsutil import obj, js_dict, proxy


# Monkeypatch global WebSocket to correct the double-slash URL bug in the
# @google/genai SDK. This is a one-time browser-global patch; we drive it from
# Python via interop. (Mirrors the IIFE at the top of aiClient.js.)
def _patch_websocket():
    # The double-slash WebSocket URL fix is applied in index.html as a proper
    # native WebSocket subclass (window.__websocket_patched). Replacing
    # window.WebSocket from Python with a function proxy breaks `new WebSocket()`
    # ("Illegal invocation"), so this is intentionally a no-op now.
    return


WORKLET_CODE = """
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const input = inputs[0];
    if (input && input[0] && input[0].length > 0) {
      const channelData = input[0];
      const pcmData = new Int16Array(channelData.length);
      for (let i = 0; i < channelData.length; i++) {
        const sample = Math.max(-1, Math.min(1, channelData[i]));
        pcmData[i] = sample < 0 ? sample * 0x8000 : sample * 0x7fff;
      }
      this.port.postMessage(pcmData);
    }
    return true;
  }
}
registerProcessor('pcm-processor', PCMProcessor);
"""


def _jget(jsobj, *path, default=None):
    """Safe nested attribute access on a JS proxy, mirroring JS optional chaining.

    Returns ``default`` when any link in ``path`` is missing/undefined/None.
    """
    cur = jsobj
    for key in path:
        if cur is None:
            return default
        try:
            cur = getattr(cur, key)
        except (AttributeError, JsException):
            return default
        if cur is None:
            return default
    return cur if cur is not None else default


def _is_function(fn):
    return callable(fn)


def _now_ms():
    return int(time.time() * 1000)


def _set_timeout(callback, delay_ms):
    """window.setTimeout that accepts a Python callable. Returns the timer id."""
    return window.setTimeout(proxy(callback), delay_ms)


def _clear_timeout(timer_id):
    if timer_id is not None:
        window.clearTimeout(timer_id)


class AIClient:
    def __init__(self, api_key, model):
        _patch_websocket()

        # --- state mirrored from the JS field declarations ---
        self.api_key = api_key
        self.client = None
        self.live_model = model
        self.active_session = None
        self.audio_context = None
        self.worklet_node = None
        self.media_source_node = None
        self.media_stream = None
        self.is_recording = False
        # Int16Array(4096) input ring buffer (lives in JS so it can be sliced cheaply).
        self.input_buffer = window.Int16Array.new(4096)
        self.input_buffer_index = 0
        self.is_disconnecting = False
        self.is_session_open = False  # NOTE: attribute, the orchestrator reads it directly
        self.is_reconnecting = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 12
        self.reconnect_first_delay_ms = 120
        self.reconnect_base_delay_ms = 300
        self.reconnect_max_delay_ms = 2200
        self.reconnect_timer = None
        self.reconnect_history_suggestion_sent = False
        self.connection_args = None
        self.recognition = None
        self.on_disconnect_callback = None
        self.on_user_speech_state_change = None
        self.is_user_speaking = False
        self.user_speech_release_timer = None
        self.user_speech_release_ms = 700
        self.last_auto_angry_animation_at = 0
        self.auto_angry_animation_cooldown_ms = 5500

        # Transcription state
        self.current_input_transcription = ""
        self.current_output_transcription = ""

        # Internal history to preserve context on reconnects
        self.internal_history = []
        self.max_internal_history_items = 180
        self.max_connection_history_items = 16
        self.max_resume_overlay_history_items = 12
        self.conversation_profile = {"userName": "", "memories": {}}
        self.recent_input_audio_chunks = []
        self.reconnect_audio_window_ms = 5000
        self.reconnect_audio_replay_silence_ms = 400
        self.reconnect_audio_sample_rate = 16000
        self.pending_reconnect_audio = False
        self.is_restoring_reconnect_context = False
        self.session_resumption_storage_key = "vrm_live_session_resumption"
        self.session_resumption_handle = ""
        self.session_resumption_updated_at = 0
        self.session_resumption_scope = ""
        self.session_resumption_max_age_ms = 2 * 60 * 60 * 1000
        self.go_away_time_left = ""
        self.go_away_notified = False
        self.skip_session_resumption_once = False
        self.go_away_abortion_count = 0
        self.current_connection_id = None

        self.token_provider = None

        # Construct the SDK client (GoogleGenAI is exposed on window).
        self.client = window.GoogleGenAI.new(
            obj(apiKey=api_key or "dummy-key-to-prevent-throw", apiVersion="v1alpha")
        )

        self._load_session_resumption_state()
        self._load_conversation_profile()

    # ------------------------------------------------------------------
    # Token / profile
    # ------------------------------------------------------------------
    def update_token(self, token):
        self.client = window.GoogleGenAI.new(obj(apiKey=token, apiVersion="v1alpha"))

    def set_token_provider(self, provider):
        self.token_provider = provider if _is_function(provider) else None

    def set_conversation_profile(self, profile=None):
        if profile is None or not isinstance(profile, dict):
            return {
                "userName": self.conversation_profile["userName"],
                "memories": dict(self.conversation_profile["memories"]),
            }

        if "userName" in profile:
            self.conversation_profile["userName"] = self._normalize_profile_text(
                profile.get("userName"), 80
            )

        if "memories" in profile:
            self.conversation_profile["memories"] = self._normalize_conversation_memories(
                profile.get("memories")
            )

        try:
            storage = self._get_storage()
            if storage is not None:
                storage.setItem(
                    "vrm_conversation_profile",
                    window.JSON.stringify(js_dict(self.conversation_profile)),
                )
        except Exception as e:  # noqa: BLE001
            console.warn("Failed to save conversation profile:", str(e))

        return {
            "userName": self.conversation_profile["userName"],
            "memories": dict(self.conversation_profile["memories"]),
        }

    def clear_session_resumption(self):
        self._clear_session_resumption_state()

    # ------------------------------------------------------------------
    # connectLive — the big entry point. Positional args match index.js exactly.
    # ------------------------------------------------------------------
    async def connect_live(
        self,
        system_prompt="",
        on_audio_data=None,
        on_animation_trigger=None,
        on_expression_trigger=None,
        on_vision_trigger=None,
        on_screen_trigger=None,
        on_camera_off_trigger=None,
        on_screen_off_trigger=None,
        on_disconnect=None,
        available_animations=None,
        on_user_name_set=None,
        on_memory_saved=None,
        on_memory_deleted=None,
        on_history_change=None,
        on_system_message=None,
        on_transcription=None,
        past_history=None,
        initial_message="",
        enable_mic=True,
        on_behavior_report=None,
        on_user_speech_state_change=None,
        get_history=None,
        on_timer_start=None,
        on_timer_cancel=None,
        on_set_background_image=None,
        on_usage_metadata=None,
    ):
        if available_animations is None:
            available_animations = []
        if past_history is None:
            past_history = []

        if self.active_session:
            return

        console.log(f"🔌 Connecting to Gemini Live... (Mic: {enable_mic})")
        self.is_disconnecting = False
        self.is_reconnecting = False
        self.reconnect_attempts = 0
        self.reconnect_history_suggestion_sent = False
        self._clear_reconnect_timer()
        self.internal_history = []
        self.current_input_transcription = ""
        self.current_output_transcription = ""
        self.recent_input_audio_chunks = []
        self.pending_reconnect_audio = False
        self.is_restoring_reconnect_context = False
        self.on_disconnect_callback = on_disconnect or None
        self.on_user_speech_state_change = (
            on_user_speech_state_change if _is_function(on_user_speech_state_change) else None
        )
        self._reset_voice_activity_state()
        self._set_user_speaking_state(False, True)

        try:
            self.connection_args = {
                "baseSystemPrompt": system_prompt,
                "onAudioData": on_audio_data,
                "onAnimationTrigger": on_animation_trigger,
                "onExpressionTrigger": on_expression_trigger,
                "onVisionTrigger": on_vision_trigger,
                "onScreenTrigger": on_screen_trigger,
                "onCameraOffTrigger": on_camera_off_trigger,
                "onScreenOffTrigger": on_screen_off_trigger,
                "onDisconnect": on_disconnect,
                "availableAnimations": available_animations,
                "onUserNameSet": on_user_name_set,
                "onMemorySaved": on_memory_saved,
                "onMemoryDeleted": on_memory_deleted,
                "onHistoryChange": on_history_change,
                "onSystemMessage": on_system_message,
                "onTranscription": on_transcription,
                "pastHistory": past_history,
                "initialMessage": initial_message,
                "enableMic": enable_mic,
                "onBehaviorReport": on_behavior_report,
                "onUserSpeechStateChange": on_user_speech_state_change,
                "getHistory": get_history,
                "onTimerStart": on_timer_start if _is_function(on_timer_start) else None,
                "onTimerCancel": on_timer_cancel if _is_function(on_timer_cancel) else None,
                "onSetBackgroundImage": on_set_background_image
                if _is_function(on_set_background_image)
                else None,
                "onUsageMetadata": on_usage_metadata if _is_function(on_usage_metadata) else None,
            }

            await self._establish_connection()
        except Exception as e:  # noqa: BLE001
            console.error("🔥 Connection Failed:", str(e))
            self.disconnect("Initial connection failed")
            self._call(on_system_message, "Connection Failed", str(e), "error")

    async def _establish_connection(self):
        if self.is_disconnecting:
            return
        is_reconnect_session = self.is_reconnecting

        ca = self.connection_args
        base_system_prompt = ca["baseSystemPrompt"]
        on_audio_data = ca["onAudioData"]
        on_animation_trigger = ca["onAnimationTrigger"]
        on_expression_trigger = ca["onExpressionTrigger"]
        on_vision_trigger = ca["onVisionTrigger"]
        on_screen_trigger = ca["onScreenTrigger"]
        on_camera_off_trigger = ca["onCameraOffTrigger"]
        on_screen_off_trigger = ca["onScreenOffTrigger"]
        on_user_name_set = ca["onUserNameSet"]
        on_memory_saved = ca["onMemorySaved"]
        on_memory_deleted = ca["onMemoryDeleted"]
        on_system_message = ca["onSystemMessage"]
        on_transcription = ca["onTranscription"]
        past_history = ca["pastHistory"]
        initial_message = ca["initialMessage"]
        enable_mic = ca["enableMic"]
        on_user_speech_state_change = ca["onUserSpeechStateChange"]
        get_history = ca["getHistory"]
        on_usage_metadata = ca["onUsageMetadata"]

        force_fresh_session = False
        try:
            storage = self._get_storage()
            if storage is not None and storage.getItem("vrm_session_ended") == "true":
                force_fresh_session = True
                storage.setItem("vrm_session_ended", "false")
        except Exception as e:  # noqa: BLE001
            console.warn("Failed to consume vrm_session_ended flag:", str(e))

        if force_fresh_session:
            self._clear_session_resumption_state()

        resumption_scope = self._create_session_resumption_scope(base_system_prompt)
        resume_handle = (
            ""
            if (self.skip_session_resumption_once or force_fresh_session)
            else self._get_valid_session_resumption_handle(resumption_scope)
        )
        is_using_session_resumption = bool(resume_handle)
        self.skip_session_resumption_once = False

        if self.token_provider:
            try:
                console.log("🔄 Fetching a fresh ephemeral token from token provider...")
                fresh_token = await self.token_provider()
                self.update_token(fresh_token)
            except Exception as token_err:  # noqa: BLE001
                console.error("🔥 Failed to fetch fresh ephemeral token:", str(token_err))
                if is_reconnect_session:
                    self._schedule_reconnect(
                        on_system_message, "Token refresh failed: " + str(token_err)
                    )
                    return
                else:
                    raise RuntimeError("Failed to obtain ephemeral token: " + str(token_err))

        self.on_user_speech_state_change = (
            on_user_speech_state_change if _is_function(on_user_speech_state_change) else None
        )

        # History is injected as User Context after connection (not appended to prompt).
        live_history_snapshot = self._get_history_snapshot(get_history)
        if isinstance(live_history_snapshot, list):
            safe_past_history = live_history_snapshot
        elif isinstance(past_history, list):
            safe_past_history = past_history
        else:
            safe_past_history = []

        if isinstance(live_history_snapshot, list):
            combined_history = safe_past_history
        else:
            combined_history = [*safe_past_history, *self.internal_history]

        history_for_connection = self._resolve_history_for_connection(
            combined_history,
            {
                "isReconnectSession": is_reconnect_session,
                "isUsingSessionResumption": is_using_session_resumption,
                "forceFreshSession": force_fresh_session,
            },
        )

        profile_prompt = self._build_conversation_profile_instruction(
            is_reconnect_session, force_fresh_session
        )
        full_system_prompt = (
            f"{base_system_prompt}\n\n{profile_prompt}" if profile_prompt else base_system_prompt
        )
        system_instruction = (
            obj(parts=to_js([js_dict({"text": full_system_prompt})]))
            if full_system_prompt
            else None
        )

        explicit_pending_question = (
            str(initial_message).strip() if isinstance(initial_message, str) else ""
        )
        last_msg = self._get_last_meaningful_history_message(combined_history)
        should_replay_pending_audio = (
            is_reconnect_session
            and not explicit_pending_question
            and self.pending_reconnect_audio
            and self._has_recoverable_reconnect_audio()
        )
        pending_user_question = explicit_pending_question
        should_answer_pending_question = len(explicit_pending_question) > 0

        if should_replay_pending_audio:
            pending_user_question = (
                last_msg["text"] if last_msg and last_msg.get("role") == "user" else ""
            )
            should_answer_pending_question = False
            console.log("Reconnect recovery: replaying recent user audio")
        elif is_reconnect_session and not pending_user_question:
            if last_msg and last_msg.get("role") == "user":
                pending_user_question = last_msg["text"]
                should_answer_pending_question = len(pending_user_question) > 0
                if should_answer_pending_question:
                    console.log(
                        "Reconnect recovery: answering last pending user message:",
                        pending_user_question,
                    )

        avail = self.connection_args["availableAnimations"]
        if len(avail) > 0:
            anim_string = ", ".join(avail[:12]) + (", ..." if len(avail) > 12 else "")
        else:
            anim_string = "wave, clap, dance, backflip"

        tools = self._get_tools(anim_string)

        config = obj(
            responseModalities=to_js(["AUDIO"]),
            thinkingConfig=obj(thinkingLevel="minimal"),
            speechConfig=obj(
                voiceConfig=obj(prebuiltVoiceConfig=obj(voiceName="Zephyr"))
            ),
            contextWindowCompression=obj(slidingWindow=obj()),
            sessionResumption=(obj(handle=resume_handle) if resume_handle else obj()),
            # Restored transcription settings (empty object uses default model)
            inputAudioTranscription=obj(),
            outputAudioTranscription=obj(),
            historyConfig=obj(initialHistoryInClientContent=True),
            tools=tools,
            systemInstruction=system_instruction,
        )

        console.log("🔌 Starting New Session. History items:", len(combined_history))

        connection_id = str(_now_ms()) + format(random.random(), ".17f")[2:]
        self.current_connection_id = connection_id

        # --- Callback closures handed to the JS SDK ---------------------------
        def on_open():
            if self.current_connection_id != connection_id:
                return
            console.log("✅ Live Session Started")
            self.is_session_open = True
            self.reconnect_attempts = 0
            self.reconnect_history_suggestion_sent = False
            self._clear_reconnect_timer()
            self.go_away_notified = False
            self.go_away_time_left = ""

            if self.is_reconnecting:
                self._call(
                    on_system_message,
                    "Reconnected",
                    "Resumed live session from server state"
                    if is_using_session_resumption
                    else "Restored connection & context",
                    "success",
                )
                self.is_reconnecting = False
            else:
                if not initial_message:
                    self._call(
                        on_system_message,
                        "Connected",
                        "Live session resumed"
                        if is_using_session_resumption
                        else "Live session started",
                        "success",
                    )

            # Restore context immediately (fire-and-forget like `void` in JS).
            window.Promise.resolve(
                self._finalize_session_open(
                    {
                        "combinedHistory": history_for_connection,
                        "pendingUserQuestion": pending_user_question,
                        "shouldAnswerPendingQuestion": should_answer_pending_question,
                        "shouldReplayPendingAudio": should_replay_pending_audio,
                        "enableMic": enable_mic,
                        "isUsingSessionResumption": is_using_session_resumption,
                    }
                )
            )

        def on_message(msg):
            if self.current_connection_id != connection_id:
                return

            usage = _jget(msg, "usageMetadata") or _jget(msg, "usage_metadata")
            if usage is not None:
                self._call(on_usage_metadata, usage)

            sru = _jget(msg, "sessionResumptionUpdate")
            if _jget(sru, "resumable") and _jget(sru, "newHandle"):
                self._set_session_resumption_handle(sru.newHandle, resumption_scope)

            go_away = _jget(msg, "goAway")
            if go_away is not None and not self.go_away_notified:
                self.go_away_notified = True
                self.go_away_time_left = _jget(go_away, "timeLeft", default="") or ""
                self._stash_pending_input_buffer_for_reconnect()

                self._call(
                    on_system_message,
                    "Session Renewal",
                    (
                        f"Server will rotate this live connection in {self.go_away_time_left}. "
                        "Reconnecting immediately."
                    )
                    if self.go_away_time_left
                    else "Server will rotate this live connection soon. Reconnecting immediately.",
                    "warning",
                )

                console.log("🔄 GoAway received: Reconnecting immediately per best practices...")

                self._set_user_speaking_state(False, True)
                self._reset_voice_activity_state()
                self._flush_transcriptions(
                    True, on_transcription, "both", {"clearUserBuffer": True}
                )

                old_session = self.active_session
                self.active_session = None
                self.is_session_open = False
                self.current_connection_id = None

                if old_session:
                    try:
                        old_session.close()
                    except Exception as e:  # noqa: BLE001
                        console.warn("Failed to close session on GoAway", str(e))

                self.is_reconnecting = True
                self.reconnect_attempts = 0
                window.Promise.resolve(self._establish_connection())
                return

            content = _jget(msg, "serverContent")

            if _jget(content, "groundingMetadata") is not None:
                console.debug("Grounding:", content.groundingMetadata)

            out_trans = _jget(content, "outputTranscription")
            if out_trans is not None:
                self.pending_reconnect_audio = False
                self._set_user_speaking_state(False)
                self._clear_user_speech_release_timer()

                if len(self.current_input_transcription.strip()) > 0:
                    self._flush_transcriptions(
                        True, on_transcription, "user", {"clearUserBuffer": True}
                    )

                text = _jget(out_trans, "text", default="") or ""
                self.current_output_transcription += text
                self._call(
                    on_transcription,
                    "model",
                    self.current_output_transcription,
                    False,
                    {"source": "gemini_output"},
                )

            in_trans = _jget(content, "inputTranscription")
            if in_trans is not None:
                text = _jget(in_trans, "text", default="") or ""
                if self._is_meaningful_speech_text(text):
                    self._set_user_speaking_state(True)
                    self._arm_user_speech_release_timer()
                self.current_input_transcription += text
                self._call(
                    on_transcription,
                    "user",
                    self.current_input_transcription,
                    False,
                    {"source": "gemini_input"},
                )

            if _jget(content, "turnComplete"):
                self._set_user_speaking_state(False)
                self._clear_user_speech_release_timer()

                if len(self.current_input_transcription.strip()) > 0:
                    self._call(
                        on_transcription,
                        "user",
                        self.current_input_transcription,
                        True,
                        {"source": "gemini_input"},
                    )
                self._flush_transcriptions(True, on_transcription, "model")

            # Handle Audio + inline text + functionCall parts
            model_turn = _jget(content, "modelTurn")
            parts = _jget(model_turn, "parts")
            if parts is not None:
                for part in parts:
                    inline_data = _jget(part, "inlineData")
                    data = _jget(inline_data, "data")
                    if data:
                        # Decode base64 PCM16 in Python (window.atob returns a Python
                        # str here, which has no .length/.charCodeAt).
                        raw = _b64.b64decode(data if isinstance(data, str) else str(data))
                        bytes_arr = window.Uint8Array.new(to_js(raw))
                        self._call(on_audio_data, window.Int16Array.new(bytes_arr.buffer))

                    part_text = _jget(part, "text")
                    if (
                        out_trans is None
                        and isinstance(part_text, str)
                        and part_text.strip()
                    ):
                        self.current_output_transcription += part_text
                        self._call(
                            on_transcription,
                            "model",
                            self.current_output_transcription,
                            False,
                            {"source": "gemini_output"},
                        )

                    fc = _jget(part, "functionCall")
                    if fc is not None:
                        self._execute_function(
                            fc,
                            on_animation_trigger,
                            on_expression_trigger,
                            on_vision_trigger,
                            on_screen_trigger,
                            on_camera_off_trigger,
                            on_screen_off_trigger,
                            on_user_name_set,
                            on_memory_saved,
                            on_memory_deleted,
                        )

            tool_call = _jget(msg, "toolCall")
            if tool_call is not None:
                self._handle_tool_call(
                    tool_call,
                    on_animation_trigger,
                    on_expression_trigger,
                    on_vision_trigger,
                    on_screen_trigger,
                    on_camera_off_trigger,
                    on_screen_off_trigger,
                    on_user_name_set,
                    on_memory_saved,
                    on_memory_deleted,
                )

        def on_close(e):
            if self.current_connection_id != connection_id:
                console.log("🔄 Ignoring close event from an old connection")
                return
            console.log("❌ Connection Closed", e)
            self.is_session_open = False
            self.active_session = None
            self._set_user_speaking_state(False, True)
            self._reset_voice_activity_state()
            self._stash_pending_input_buffer_for_reconnect()

            # Flush partial transcriptions BEFORE reconnect so user words survive.
            self._flush_transcriptions(
                True, on_transcription, "both", {"clearUserBuffer": True}
            )

            if self.is_disconnecting:
                return

            reason = _jget(e, "reason", default="Connection lost") or "Connection lost"
            console.log(f"Connection dropped unexpectedly ({reason}).")
            self._schedule_reconnect(on_system_message, reason)

        def on_error(e):
            if self.current_connection_id != connection_id:
                return
            console.error("🔥 Live Error:", e)
            # Often transient internal API issues; reconnection triggers via onclose.

        try:
            self.active_session = await self.client.live.connect(
                obj(
                    model=self.live_model,
                    config=config,
                    callbacks=obj(
                        onopen=proxy(on_open),
                        onmessage=proxy(on_message),
                        onclose=proxy(on_close),
                        onerror=proxy(on_error),
                    ),
                )
            )
        except Exception as err:  # noqa: BLE001
            console.error("Failed to connect live session:", str(err))

            if is_using_session_resumption and not self.is_disconnecting:
                console.warn(
                    "Session resumption failed, clearing handle and retrying with manual restore."
                )
                self._clear_session_resumption_state()
                self.skip_session_resumption_once = True
                self._call(
                    on_system_message,
                    "Session Resume Failed",
                    "Falling back to chat history restore for this reconnect.",
                    "warning",
                )
                await self._establish_connection()
                return

            if not self.is_disconnecting:
                self._schedule_reconnect(on_system_message, str(err) or "connection failed")
            else:
                self._call(
                    on_system_message,
                    "Connection Error",
                    "Failed to connect. Check API Key.",
                    "error",
                )
            return

    # ------------------------------------------------------------------
    # Context restoration
    # ------------------------------------------------------------------
    async def _restore_context(self, history, pending_question, options=None):
        if not self.active_session:
            return
        options = options or {}
        should_answer_pending_question = options.get("shouldAnswerPendingQuestion", False)
        replay_pending_audio = options.get("replayPendingAudio", False)
        history_only = options.get("historyOnly", False)

        safe_history = history if isinstance(history, list) else []
        valid_history = [
            m for m in safe_history if m and m.get("text") and m.get("text").strip()
        ]
        normalized_pending_question = (
            pending_question.strip() if isinstance(pending_question, str) else ""
        )
        should_recover_question = (
            not replay_pending_audio
            and should_answer_pending_question
            and len(normalized_pending_question) > 0
        )

        context_history = valid_history
        if (should_recover_question or replay_pending_audio) and len(valid_history) > 0:
            last_msg = valid_history[-1]
            if last_msg and last_msg.get("role") == "user" and (
                replay_pending_audio
                or str(last_msg.get("text") or "").strip().lower()
                == normalized_pending_question.lower()
            ):
                context_history = valid_history[:-1]

        history_turns = [
            js_dict(
                {
                    "role": "user" if (msg and msg.get("role") == "user") else "model",
                    "parts": to_js([js_dict({"text": str((msg or {}).get("text") or "")})]),
                }
            )
            for msg in context_history
        ]
        instruction_lines = [
            "[SYSTEM] Recent chat context restored.",
            "Use the restored turns as recent conversation state.",
        ]

        if should_recover_question:
            instruction_lines += [
                "[SYSTEM] RECONNECT RULE: The user already asked this before disconnect.",
                f'UNANSWERED USER QUERY: "{normalized_pending_question}"',
                "Respond immediately. Do not greet. Do not ask them to repeat.",
            ]
            console.log("Restoring context with PENDING QUESTION:", normalized_pending_question)
        elif replay_pending_audio:
            instruction_lines += [
                "[SYSTEM] RECONNECT RULE: The user's latest message will be replayed as audio next.",
                "Treat this payload as background only. Do not answer yet.",
                "Wait for the replayed audio and respond naturally without asking them to repeat.",
            ]
            console.log("Restoring context and waiting for replayed user audio")
        else:
            instruction_lines.append(
                "Do not greet or answer until the next real user input arrives."
            )
            console.log("Restoring recent context silently")

        if len(history_turns) > 0:
            await self._send_client_content(history_turns, False)

        if history_only:
            return

        await self._send_client_content(
            [
                js_dict(
                    {
                        "role": "user",
                        "parts": to_js([js_dict({"text": "\n".join(instruction_lines)})]),
                    }
                )
            ],
            False,
        )

        if should_recover_question:
            self.active_session.sendRealtimeInput(obj(text=normalized_pending_question))

    # ------------------------------------------------------------------
    # sendText
    # ------------------------------------------------------------------
    async def send_text(self, text, force_send=False, options=None):
        """Send realtime text to the active session.

        NOTE: the original aiClient.js has a large block of code after the first
        `return` that is dead (unreachable) — a session-restart fallback. It is
        intentionally NOT reproduced here.
        """
        options = options or {}
        normalized_text = text.strip() if isinstance(text, str) else ""
        if not normalized_text:
            return

        preserve_reconnect_audio = options.get("preserveReconnectAudio", False)
        if not preserve_reconnect_audio:
            self.pending_reconnect_audio = False

        if not self.active_session or not self.is_session_open:
            raise RuntimeError("Live session is not active")

        try:
            console.log(
                "Sending realtime text to active session:",
                normalized_text[:50] + "...",
            )
            self.active_session.sendRealtimeInput(obj(text=normalized_text))
            return
        except Exception as error:  # noqa: BLE001
            console.error("Failed to send realtime text:", str(error))
            if not force_send:
                raise
            return

    # ------------------------------------------------------------------
    # Reconnect / history helpers
    # ------------------------------------------------------------------
    def _clear_reconnect_timer(self):
        if not self.reconnect_timer:
            return
        _clear_timeout(self.reconnect_timer)
        self.reconnect_timer = None

    def _get_last_meaningful_history_message(self, history=None):
        if not isinstance(history, list):
            return None
        for i in range(len(history) - 1, -1, -1):
            item = history[i]
            text = item.get("text").strip() if item and isinstance(item.get("text"), str) else ""
            if not text:
                continue
            role = "user" if (item and item.get("role") == "user") else "model"
            return {"role": role, "text": text}
        return None

    def _push_internal_history(self, role, text):
        normalized_role = "user" if role == "user" else "model"
        normalized_text = text.strip() if isinstance(text, str) else ""
        if not normalized_text:
            return

        has_recent_duplicate = any(
            item and item.get("role") == normalized_role and item.get("text") == normalized_text
            for item in self.internal_history[-6:]
        )
        if has_recent_duplicate:
            return

        self.internal_history.append(
            {"role": normalized_role, "text": normalized_text, "timestamp": _now_ms()}
        )

        if len(self.internal_history) > self.max_internal_history_items:
            self.internal_history = self.internal_history[-self.max_internal_history_items :]

    def _normalize_profile_text(self, value, max_length=240):
        if isinstance(value, str):
            normalized = " ".join(value.split()).strip()
        else:
            normalized = ""
        if not normalized:
            return ""
        return normalized[:max_length].strip()

    def _normalize_conversation_memories(self, memories=None):
        if not isinstance(memories, dict):
            return {}

        normalized = {}
        count = 0
        for key, value in memories.items():
            safe_key = self._normalize_profile_text(key, 80)
            safe_value = self._normalize_profile_text(value, 220)
            if not safe_key or not safe_value:
                continue
            normalized[safe_key] = safe_value
            count += 1
            if count >= 24:
                break
        return normalized

    def _get_storage(self):
        try:
            ls = getattr(window, "localStorage", None)
            return ls
        except Exception:  # noqa: BLE001
            return None

    def _load_session_resumption_state(self):
        storage = self._get_storage()
        if not storage:
            return
        try:
            raw = storage.getItem(self.session_resumption_storage_key) or "null"
            parsed = window.JSON.parse(raw)
            handle = _jget(parsed, "handle")
            self.session_resumption_handle = handle.strip() if isinstance(handle, str) else ""
            updated = _jget(parsed, "updatedAt")
            try:
                self.session_resumption_updated_at = int(updated) if updated else 0
            except (TypeError, ValueError):
                self.session_resumption_updated_at = 0
            scope = _jget(parsed, "scope")
            self.session_resumption_scope = scope.strip() if isinstance(scope, str) else ""
        except Exception as error:  # noqa: BLE001
            console.warn("Failed to load session resumption state:", str(error))
            self._clear_session_resumption_state()

    def _load_conversation_profile(self):
        storage = self._get_storage()
        if not storage:
            return
        try:
            raw = storage.getItem("vrm_conversation_profile") or "null"
            parsed = window.JSON.parse(raw)
            if parsed is not None:
                user_name = _jget(parsed, "userName")
                if isinstance(user_name, str):
                    self.conversation_profile["userName"] = self._normalize_profile_text(
                        user_name, 80
                    )
                memories = _jget(parsed, "memories")
                if memories is not None:
                    try:
                        mem_py = memories.to_py()
                    except Exception:  # noqa: BLE001
                        mem_py = None
                    if isinstance(mem_py, dict):
                        self.conversation_profile["memories"] = (
                            self._normalize_conversation_memories(mem_py)
                        )
        except Exception as error:  # noqa: BLE001
            console.warn("Failed to load conversation profile:", str(error))

    def _persist_session_resumption_state(self):
        storage = self._get_storage()
        if not storage:
            return

        if (
            not self.session_resumption_handle
            or not self.session_resumption_updated_at
            or not self.session_resumption_scope
        ):
            storage.removeItem(self.session_resumption_storage_key)
            return

        storage.setItem(
            self.session_resumption_storage_key,
            window.JSON.stringify(
                js_dict(
                    {
                        "handle": self.session_resumption_handle,
                        "updatedAt": self.session_resumption_updated_at,
                        "scope": self.session_resumption_scope,
                    }
                )
            ),
        )

    def _set_session_resumption_handle(self, handle, scope):
        normalized_handle = handle.strip() if isinstance(handle, str) else ""
        normalized_scope = scope.strip() if isinstance(scope, str) else ""
        if not normalized_handle or not normalized_scope:
            return
        if (
            self.session_resumption_handle == normalized_handle
            and self.session_resumption_scope == normalized_scope
        ):
            return

        self.session_resumption_handle = normalized_handle
        self.session_resumption_updated_at = _now_ms()
        self.session_resumption_scope = normalized_scope
        self._persist_session_resumption_state()

    def _clear_session_resumption_state(self):
        self.session_resumption_handle = ""
        self.session_resumption_updated_at = 0
        self.session_resumption_scope = ""
        storage = self._get_storage()
        if storage is not None:
            storage.removeItem(self.session_resumption_storage_key)

    def _hash_string(self, value=""):
        input_str = value if isinstance(value, str) else ""
        hash_val = 2166136261
        for ch in input_str:
            hash_val ^= ord(ch)
            # Math.imul: 32-bit signed multiply.
            hash_val = (hash_val * 16777619) & 0xFFFFFFFF
        # >>> 0 then toString(16)
        return format(hash_val & 0xFFFFFFFF, "x")

    def _create_session_resumption_scope(self, base_system_prompt=""):
        return f"{self.live_model}:{self._hash_string(base_system_prompt)}"

    def _get_valid_session_resumption_handle(self, scope):
        normalized_scope = scope.strip() if isinstance(scope, str) else ""
        if not normalized_scope:
            return ""
        if not self.session_resumption_handle or not self.session_resumption_updated_at:
            return ""
        if self.session_resumption_scope != normalized_scope:
            return ""

        age_ms = _now_ms() - self.session_resumption_updated_at
        if age_ms > self.session_resumption_max_age_ms:
            self._clear_session_resumption_state()
            return ""

        return self.session_resumption_handle

    def _select_reconnect_history_window(self, history=None):
        safe_history = [item for item in history if item] if isinstance(history, list) else []
        if len(safe_history) == 0:
            return []

        def _finite_ts(item):
            ts = item.get("timestamp")
            return isinstance(ts, (int, float)) and ts == ts and ts not in (float("inf"), float("-inf"))

        with_timestamp = [item for item in safe_history if _finite_ts(item)]
        if len(with_timestamp) == 0:
            return safe_history[-60:]

        newest_timestamp = max(item["timestamp"] for item in with_timestamp)
        one_hour_ago = newest_timestamp - 60 * 60 * 1000
        last_hour_history = [
            item
            for item in safe_history
            if isinstance(item.get("timestamp"), (int, float))
            and item["timestamp"] >= one_hour_ago
        ]
        if len(last_hour_history) > 0:
            return last_hour_history

        # Start-of-day boundary for the newest timestamp (local time).
        day_start_date = window.Date.new(newest_timestamp)
        day_start_date.setHours(0, 0, 0, 0)
        day_start = day_start_date.getTime()
        same_day_history = [
            item
            for item in safe_history
            if isinstance(item.get("timestamp"), (int, float)) and item["timestamp"] >= day_start
        ]
        if len(same_day_history) > 0:
            return same_day_history

        return safe_history[-60:]

    def _get_resume_overlay_history(self, history=None):
        safe_history = [item for item in history if item] if isinstance(history, list) else []
        if len(safe_history) == 0:
            return []
        return safe_history[-self.max_resume_overlay_history_items :]

    def _resolve_history_for_connection(self, history=None, options=None):
        options = options or {}
        is_reconnect_session = options.get("isReconnectSession", False)
        is_using_session_resumption = options.get("isUsingSessionResumption", False)
        force_fresh_session = options.get("forceFreshSession", False)
        if is_using_session_resumption or force_fresh_session:
            return []

        safe_history = history if isinstance(history, list) else []

        # Strip turns containing an end_conversation tool call so the model does
        # not re-execute the disconnect on the next fresh session.
        filtered_history = [
            item
            for item in safe_history
            if "end_conversation"
            not in (item.get("text") if item and isinstance(item.get("text"), str) else "")
        ]

        bounded_history = filtered_history[-self.max_connection_history_items :]
        reconnect_window = (
            self._select_reconnect_history_window(filtered_history)
            if is_reconnect_session
            else []
        )
        chosen = reconnect_window if len(reconnect_window) > 0 else bounded_history
        return chosen[-self.max_connection_history_items :]

    def _is_fatal_close_reason(self, reason=""):
        normalized = str(reason or "").lower()
        if not normalized:
            return False
        return (
            "quota" in normalized
            or "billing" in normalized
            or "resource exhausted" in normalized
            or "429" in normalized
            or "authentication" in normalized
            or "invalid api key" in normalized
            or "unauthenticated" in normalized
            or "credentials" in normalized
        )

    def _set_conversation_memory(self, key, value):
        safe_key = self._normalize_profile_text(key, 80)
        safe_value = self._normalize_profile_text(value, 220)
        if not safe_key or not safe_value:
            return
        self.conversation_profile["memories"] = {
            **self.conversation_profile["memories"],
            safe_key: safe_value,
        }

    def _delete_conversation_memory(self, key):
        safe_key = self._normalize_profile_text(key, 80)
        if not safe_key or safe_key not in self.conversation_profile["memories"]:
            return
        next_memories = dict(self.conversation_profile["memories"])
        del next_memories[safe_key]
        self.conversation_profile["memories"] = next_memories

    def _build_conversation_profile_instruction(
        self, is_reconnect_session=False, force_fresh_session=False
    ):
        sections = []
        user_name = self.conversation_profile["userName"]
        memory_entries = list(self.conversation_profile["memories"].items())

        if user_name:
            sections.append(
                f"[PROFILE OVERRIDE] The user's verified name is {user_name}. "
                "Do not ask for their name again. Ignore any earlier instruction that says "
                "you do not know their name."
            )

        if len(memory_entries) > 0:
            memory_lines = "\n".join(f"- {key}: {value}" for key, value in memory_entries)
            sections.append(
                f"[SAVED MEMORIES]\n{memory_lines}\n"
                "Treat these as remembered facts unless the user corrects or deletes them."
            )

        try:
            storage = self._get_storage()
            saved_history_str = storage.getItem("vrm_chat_history") if storage else None
            if saved_history_str:
                full_history = window.JSON.parse(saved_history_str)
                if full_history is not None and full_history.length > 0:
                    use_reconnect = is_reconnect_session and not force_fresh_session
                    full_len = full_history.length
                    cutoff_index = max(0, full_len - 16) if use_reconnect else 0
                    slice_end = cutoff_index if use_reconnect else full_len

                    older_history = []
                    for idx in range(0, slice_end):
                        item = full_history[idx]
                        text = _jget(item, "text", default="")
                        text = text if isinstance(text, str) else ""
                        if "end_conversation" in text:
                            continue
                        older_history.append(item)

                    if len(older_history) > 0:
                        formatted_lines = []
                        for item in older_history:
                            role = _jget(item, "role")
                            role_label = "User" if role == "user" else "Riko (AI)"
                            item_text = _jget(item, "text", default="")
                            formatted_lines.append(f"{role_label}: {item_text}")
                        formatted_history = "\n".join(formatted_lines)

                        sections.append(
                            "[OLDER CONVERSATION HISTORY LOG]\n"
                            "This is the record of your previous conversation turns with this "
                            "user before the current session. Use it to keep track of what you "
                            "discussed:\n"
                            f"{formatted_history}"
                        )
        except Exception as e:  # noqa: BLE001
            console.warn("Failed to load older chat history log for profile instruction:", str(e))

        # Always inject a session boundary marker.
        sections.append(
            "[NEW SESSION] The previous conversation session has fully ended. "
            "You are starting a completely new conversation session now. "
            "Do NOT automatically close the call or call end_conversation. Only end the call "
            "if the user explicitly requests you to do so in the new conversation."
        )

        if len(sections) == 0:
            return ""
        return "[RECONNECT PROFILE]\n" + "\n\n".join(sections)

    def _get_history_snapshot(self, get_history):
        if not _is_function(get_history):
            return None
        try:
            snapshot = get_history()
            # The orchestrator may return a JS array; normalize to a Python list.
            if isinstance(snapshot, list):
                return snapshot
            if snapshot is not None and hasattr(snapshot, "to_py"):
                py = snapshot.to_py()
                return py if isinstance(py, list) else None
            return None
        except Exception as error:  # noqa: BLE001
            console.warn("Failed to read history snapshot for reconnect:", str(error))
            return None

    async def _finalize_session_open(self, options=None):
        options = options or {}
        combined_history = options.get("combinedHistory", [])
        pending_user_question = options.get("pendingUserQuestion", "")
        should_answer_pending_question = options.get("shouldAnswerPendingQuestion", False)
        should_replay_pending_audio = options.get("shouldReplayPendingAudio", False)
        enable_mic = options.get("enableMic", True)
        is_using_session_resumption = options.get("isUsingSessionResumption", False)

        try:
            self.is_restoring_reconnect_context = should_replay_pending_audio

            if is_using_session_resumption:
                overlay_history = self._get_resume_overlay_history(combined_history)
                if len(overlay_history) > 0:
                    await self._restore_context(overlay_history, "", {"historyOnly": True})

                if (
                    should_answer_pending_question
                    and isinstance(pending_user_question, str)
                    and pending_user_question.strip()
                ):
                    self.active_session.sendRealtimeInput(
                        obj(text=pending_user_question.strip())
                    )
            else:
                await self._restore_context(
                    combined_history,
                    pending_user_question,
                    {
                        "shouldAnswerPendingQuestion": should_answer_pending_question,
                        "replayPendingAudio": should_replay_pending_audio,
                    },
                )

            if should_replay_pending_audio:
                await self._sleep_ms(140)
                await self._replay_recent_user_audio()
        except Exception as error:  # noqa: BLE001
            console.error("Failed to restore live session context:", str(error))
        finally:
            self.is_restoring_reconnect_context = False
            if enable_mic:
                await self.start_microphone()
            else:
                self.stop_microphone()

    # ------------------------------------------------------------------
    # Reconnect audio buffering
    # ------------------------------------------------------------------
    def _has_speech_energy_in_chunk(self, int16_data):
        if int16_data is None or int16_data.length == 0:
            return False

        sum_squares = 0.0
        length = int16_data.length
        for i in range(length):
            sample = int16_data[i] / 32768
            sum_squares += sample * sample

        rms = math.sqrt(sum_squares / length)
        return rms >= 0.015

    def _trim_recent_input_audio(self, reference_time=None):
        if reference_time is None:
            reference_time = _now_ms()
        min_timestamp = reference_time - self.reconnect_audio_window_ms
        self.recent_input_audio_chunks = [
            chunk
            for chunk in self.recent_input_audio_chunks
            if chunk["samples"] is not None
            and chunk["samples"].length > 0
            and chunk["timestamp"] >= min_timestamp
        ]
        self.pending_reconnect_audio = any(
            chunk["hasSpeech"] for chunk in self.recent_input_audio_chunks
        )

    def _remember_recent_audio_chunk(self, int16_data):
        if int16_data is None or int16_data.length == 0:
            return
        chunk_copy = int16_data.slice()
        self.recent_input_audio_chunks.append(
            {
                "timestamp": _now_ms(),
                "samples": chunk_copy,
                "hasSpeech": self._has_speech_energy_in_chunk(chunk_copy),
            }
        )
        self._trim_recent_input_audio()

    def _stash_pending_input_buffer_for_reconnect(self):
        if not isinstance(self.input_buffer_index, int) or self.input_buffer_index <= 0:
            return
        partial_chunk = self.input_buffer.slice(0, self.input_buffer_index)
        self.input_buffer_index = 0
        self._remember_recent_audio_chunk(partial_chunk)

    def _has_recoverable_reconnect_audio(self):
        self._trim_recent_input_audio()
        return self.pending_reconnect_audio and len(self.recent_input_audio_chunks) > 0

    def _encode_int16_to_base64(self, int16_data):
        if int16_data is None or int16_data.length == 0:
            return ""
        bytes_arr = window.Uint8Array.new(
            int16_data.buffer, int16_data.byteOffset, int16_data.byteLength
        )
        binary = ""
        chunk_size = 0x8000
        total = bytes_arr.length
        i = 0
        while i < total:
            sub = bytes_arr.subarray(i, i + chunk_size)
            binary += window.String.fromCharCode.apply(None, sub)
            i += chunk_size
        return window.btoa(binary)

    def _encode_utf8_text_to_base64(self, text):
        normalized_text = text if isinstance(text, str) else ""
        if not normalized_text:
            return ""
        bytes_arr = window.TextEncoder.new().encode(normalized_text)
        binary = ""
        chunk_size = 0x8000
        total = bytes_arr.length
        i = 0
        while i < total:
            sub = bytes_arr.subarray(i, i + chunk_size)
            binary += window.String.fromCharCode.apply(None, sub)
            i += chunk_size
        return window.btoa(binary)

    async def _create_history_attachment_part(self, history_document):
        normalized_document = history_document if isinstance(history_document, str) else "[]"
        try:
            history_blob = window.Blob.new(
                to_js([normalized_document]), obj(type="application/json")
            )
            uploaded_file = await self.client.files.upload(
                obj(
                    file=history_blob,
                    config=obj(
                        mimeType="application/json",
                        displayName="vrm_chat_history.json",
                    ),
                )
            )
            uri = _jget(uploaded_file, "uri")
            if uri:
                return obj(
                    fileData=obj(
                        fileUri=uri,
                        mimeType=_jget(uploaded_file, "mimeType", default="application/json"),
                        displayName=_jget(
                            uploaded_file, "displayName", default="vrm_chat_history.json"
                        ),
                    )
                )
        except Exception as error:  # noqa: BLE001
            console.warn(
                "Failed to upload vrm_chat_history.json, falling back to inline JSON:", str(error)
            )

        return obj(
            inlineData=obj(
                mimeType="application/json",
                data=self._encode_utf8_text_to_base64(normalized_document),
            )
        )

    async def _send_client_content(self, turns, turn_complete=True):
        if not self.active_session:
            raise RuntimeError("No active live session")

        safe_turns = [t for t in turns if t] if isinstance(turns, list) else []
        self.active_session.sendClientContent(
            obj(turns=to_js(safe_turns), turnComplete=turn_complete)
        )

    async def _replay_recent_user_audio(self):
        if not self.active_session or not self.is_session_open:
            return False
        if not self._has_recoverable_reconnect_audio():
            return False

        try:
            for chunk in self.recent_input_audio_chunks:
                base64_audio = self._encode_int16_to_base64(chunk["samples"])
                if not base64_audio:
                    continue
                self.active_session.sendRealtimeInput(
                    obj(audio=obj(mimeType="audio/pcm;rate=16000", data=base64_audio))
                )

            silence_samples = max(
                1,
                int(
                    (self.reconnect_audio_sample_rate * self.reconnect_audio_replay_silence_ms)
                    / 1000
                ),
            )
            silence_base64 = self._encode_int16_to_base64(
                window.Int16Array.new(silence_samples)
            )
            if silence_base64:
                self.active_session.sendRealtimeInput(
                    obj(audio=obj(mimeType="audio/pcm;rate=16000", data=silence_base64))
                )

            self.pending_reconnect_audio = False
            console.log("Reconnect recovery: replayed recent user audio")
            return True
        except Exception as error:  # noqa: BLE001
            console.error("Failed to replay recent user audio:", str(error))
            return False

    def _schedule_reconnect(self, on_system_message, reason="Connection lost"):
        if self.is_disconnecting:
            return
        if self._is_fatal_close_reason(reason):
            self._call(
                on_system_message,
                "Connection Closed",
                "Live session rejected the current setup (API Key or Quota issue). "
                "Reconnect stopped to avoid looping.",
                "error",
            )
            self.disconnect(reason)
            return

        if "goaway" in reason.lower():
            self.go_away_abortion_count = (self.go_away_abortion_count or 0) + 1
            if self.go_away_abortion_count >= 2:
                self.go_away_abortion_count = 0
                self._call(
                    on_system_message,
                    "GoAway Loop Detected",
                    "Connection unstable. Clearing chat history and session context to recover...",
                    "error",
                )

                self._clear_session_resumption_state()
                self.internal_history = []
                if _is_function(_jget_dict(self.connection_args, "onHistoryChange")):
                    self.connection_args["onHistoryChange"]([])
                try:
                    storage = self._get_storage()
                    if storage is not None:
                        storage.removeItem("vrm_chat_history")
                except Exception:  # noqa: BLE001
                    pass

                self.reconnect_attempts = 0
                self.is_reconnecting = True
                self.skip_session_resumption_once = True

                def _retry():
                    window.Promise.resolve(self._establish_connection())

                _set_timeout(_retry, 1000)
                return
        else:
            self.go_away_abortion_count = 0

        if self.reconnect_timer:
            return

        self.is_reconnecting = True
        self.reconnect_attempts += 1

        if self.reconnect_attempts > self.max_reconnect_attempts:
            self._call(
                on_system_message,
                "Connection Failed",
                "Reconnect limit reached. Clear chat history and reconnect manually.",
                "error",
            )
            self.disconnect("Reconnect limit reached")
            return

        attempt = self.reconnect_attempts
        exponential_delay = self.reconnect_base_delay_ms * 2 ** max(0, attempt - 2)
        base_delay = self.reconnect_first_delay_ms if attempt == 1 else exponential_delay
        jitter_ms = int(random.random() * 120)
        delay_ms = min(self.reconnect_max_delay_ms, base_delay + jitter_ms)
        delay_seconds = math.ceil(delay_ms / 1000)

        self._call(
            on_system_message,
            "Reconnecting",
            f"Connection unstable ({reason}). Retry {attempt}/{self.max_reconnect_attempts} "
            f"in {delay_seconds}s.",
            "warning",
        )

        if attempt >= 4 and not self.reconnect_history_suggestion_sent:
            self.reconnect_history_suggestion_sent = True
            self._call(
                on_system_message,
                "History Cleanup Recommended",
                "Too many reconnects. Open Chat > Clear to remove old history, then reconnect.",
                "warning",
            )

        def _do_reconnect():
            self.reconnect_timer = None
            window.Promise.resolve(self._establish_connection())

        self.reconnect_timer = _set_timeout(_do_reconnect, delay_ms)

    def _flush_transcriptions(self, is_final, on_transcription, target="both", options=None):
        options = options or {}
        clear_user_buffer = options.get("clearUserBuffer", False)

        if (target == "user" or target == "both") and self.current_input_transcription.strip():
            text = self.current_input_transcription
            self._call(on_transcription, "user", text, is_final, {"source": "gemini_input"})
            if is_final:
                self._push_internal_history("user", text)
                if clear_user_buffer:
                    self.current_input_transcription = ""

        if (target == "model" or target == "both") and self.current_output_transcription.strip():
            text = self.current_output_transcription
            self._call(on_transcription, "model", text, is_final, {"source": "gemini_output"})
            if is_final:
                self._push_internal_history("model", text)
                self.current_output_transcription = ""

    # ------------------------------------------------------------------
    # Tool / function execution
    # ------------------------------------------------------------------
    def _handle_tool_call(
        self,
        tool_call,
        on_animation_trigger,
        on_expression_trigger,
        on_vision_trigger,
        on_screen_trigger,
        on_camera_off_trigger,
        on_screen_off_trigger,
        on_user_name_set,
        on_memory_saved,
        on_memory_deleted,
    ):
        function_calls = _jget(tool_call, "functionCalls")
        if function_calls is None:
            return
        for fc in function_calls:
            self._execute_function(
                fc,
                on_animation_trigger,
                on_expression_trigger,
                on_vision_trigger,
                on_screen_trigger,
                on_camera_off_trigger,
                on_screen_off_trigger,
                on_user_name_set,
                on_memory_saved,
                on_memory_deleted,
            )

    def _is_anger_expression(self, expression_name):
        if not isinstance(expression_name, str):
            return False
        normalized = expression_name.strip().lower()
        if not normalized:
            return False
        import re

        return bool(
            re.search(
                r"\b(angry|furious|enraged|livid|seething|fuming|irate|wrathful|hostile|"
                r"aggressive|annoyed|agitated|resentful|defiant|serious|determined)\b",
                normalized,
            )
        )

    def _maybe_trigger_angry_animation(self, expression_name, on_animation_trigger):
        if not self._is_anger_expression(expression_name):
            return
        now = _now_ms()
        if now - self.last_auto_angry_animation_at < self.auto_angry_animation_cooldown_ms:
            return
        self.last_auto_angry_animation_at = now
        self._call(on_animation_trigger, "angry")

    def _execute_function(
        self,
        fc,
        on_animation_trigger,
        on_expression_trigger,
        on_vision_trigger,
        on_screen_trigger,
        on_camera_off_trigger,
        on_screen_off_trigger,
        on_user_name_set,
        on_memory_saved,
        on_memory_deleted,
    ):
        fid = _jget(fc, "id")
        name = _jget(fc, "name")
        args = _jget(fc, "args")
        console.log(f"🎯 Function: {name}", args)

        if name == "set_user_name":
            self.set_conversation_profile({"userName": _jget(args, "name")})
            self._call(on_user_name_set, _jget(args, "name"))
            self._send_tool_response(fid, name, obj(result="ok"))
            return
        if name == "save_memory":
            self._set_conversation_memory(_jget(args, "key"), _jget(args, "value"))
            self._call(on_memory_saved, _jget(args, "key"), _jget(args, "value"))
            self._send_tool_response(fid, name, obj(result="ok"))
            return
        if name == "delete_memory":
            self._delete_conversation_memory(_jget(args, "key"))
            self._call(on_memory_deleted, _jget(args, "key"))
            self._send_tool_response(fid, name, obj(result="ok"))
            return

        if name == "start_timer":
            duration_raw = _jget(args, "duration_seconds")
            try:
                duration_seconds = float(duration_raw)
            except (TypeError, ValueError):
                duration_seconds = float("nan")
            if not math.isfinite(duration_seconds) or duration_seconds <= 0:
                self._send_tool_response(
                    fid,
                    name,
                    obj(error="duration_seconds must be a positive number of seconds."),
                )
                return

            label_raw = _jget(args, "label")
            label = label_raw if isinstance(label_raw, str) else "Timer"
            on_timer_start = _jget_dict(self.connection_args, "onTimerStart")
            if _is_function(on_timer_start):
                on_timer_start({"duration_seconds": duration_seconds, "label": label})
            self._send_tool_response(fid, name, obj(result="ok"))
            return

        if name == "cancel_timer":
            on_timer_cancel = _jget_dict(self.connection_args, "onTimerCancel")
            if _is_function(on_timer_cancel):
                on_timer_cancel()
            self._send_tool_response(fid, name, obj(result="ok"))
            return

        if name == "end_conversation":
            self._send_tool_response(fid, name, obj(result="ok"))

            def check_and_disconnect():
                audio_manager = _jget(window, "vrmSystem", "audioManager") or _jget(
                    window, "vrmAudioManager"
                )
                if audio_manager:
                    active_sources = _jget(audio_manager, "activeSources")
                    is_speaking = bool(_jget(audio_manager, "isPlaying")) or bool(
                        active_sources is not None and active_sources.length > 0
                    )
                else:
                    is_speaking = False
                if is_speaking:
                    console.log("AI is still speaking, deferring end_conversation disconnect...")
                    _set_timeout(check_and_disconnect, 500)
                else:
                    console.log("AI finished speaking, disconnecting end_conversation now.")
                    self.disconnect("AI ended the conversation")

            _set_timeout(check_and_disconnect, 1500)
            return

        if name == "set_background_image":
            self._handle_set_background_image(fid, name, args)
            return

        if name == "report_behavior":
            self._call(on_expression_trigger, "furious", 8.0)
            self._call(on_animation_trigger, "cutthroat")
            on_behavior_report = _jget_dict(self.connection_args, "onBehaviorReport")
            if _is_function(on_behavior_report):
                on_behavior_report(_jget(args, "reason"), _jget(args, "severity"))
            self._send_tool_response(fid, name, obj(result="Report sent to developer."))
            return

        if name == "look_at_user":
            window.Promise.resolve(
                self._execute_vision_capture(
                    fid, name, on_vision_trigger, "Camera not available."
                )
            )
            return
        if name == "look_at_screen":
            window.Promise.resolve(
                self._execute_vision_capture(
                    fid,
                    name,
                    on_screen_trigger,
                    "Screen not shared or active. Ask user to enable screen share.",
                )
            )
            return
        if name == "turn_off_camera":
            window.Promise.resolve(
                self._execute_control_action(
                    fid, name, on_camera_off_trigger, "Camera is already off or unavailable."
                )
            )
            return
        if name == "turn_off_screen":
            window.Promise.resolve(
                self._execute_control_action(
                    fid,
                    name,
                    on_screen_off_trigger,
                    "Screen share is already off or unavailable.",
                )
            )
            return

        def deferred_trigger():
            if name == "trigger_animation":
                self._call(on_animation_trigger, _jget(args, "animation_name"))
            if name == "set_expression":
                expression_name = _jget(args, "expression")
                self._call(
                    on_expression_trigger,
                    expression_name,
                    _jget(args, "duration", default=5.0) or 5.0,
                )
                self._maybe_trigger_angry_animation(expression_name, on_animation_trigger)

        _set_timeout(deferred_trigger, 500)

        self._send_tool_response(fid, name, obj(status="queued"))

    def _handle_set_background_image(self, fid, name, args):
        """Port of the set_background_image branch (image search + fetch + send)."""
        prompt = _jget(args, "prompt")
        if not (isinstance(prompt, str) and len(prompt.strip()) > 0):
            self._send_tool_response(fid, name, obj(error="Prompt is required."))
            return

        seed = int(random.random() * 1000000)

        stopwords = {
            "and", "the", "with", "for", "from", "under", "above", "near", "beside",
            "foreground", "background", "view", "scenic", "sunset", "sunny", "landscape",
        }
        import re

        cleaned = re.sub(r"[^a-z0-9\s,]", "", prompt.strip().lower())
        words = [w for w in re.split(r"[\s,]+", cleaned) if len(w) > 2 and w not in stopwords]
        tags = ",".join(words[:4])
        query_tags = tags or "landscape"

        search_url = f"/api/search-image?q={window.encodeURIComponent(prompt.strip())}"

        def send_image_to_ai(url):
            if not url:
                return
            final_fetch_url = (
                f"/api/proxy-image?url={window.encodeURIComponent(url)}"
                if isinstance(url, str) and url.startswith("http")
                else url
            )

            def on_blob(blob):
                reader = window.FileReader.new()

                def on_loadend(ev=None):
                    base64_data = reader.result.split(",")[1]

                    def on_sent(sent):
                        console.log(
                            "🖼️ Sent chosen background image to Gemini session:", sent
                        )

                    self._then(self._send_realtime_image(base64_data), on_sent)

                reader.onloadend = proxy(on_loadend)
                reader.readAsDataURL(blob)

            def fetch_blob(res):
                return res.blob()

            promise = window.fetch(final_fetch_url)
            promise = promise.then(proxy(fetch_blob))
            promise = promise.then(proxy(on_blob))
            promise.catch(
                proxy(
                    lambda e: console.warn("Could not send chosen background image to AI:", e)
                )
            )

        def on_search_data(data):
            image_url = None
            results = _jget(data, "results")
            if results is not None and results.length > 0:
                limit = min(results.length, 5)
                random_index = int(random.random() * limit)
                image_url = _jget(results[random_index], "image")

            if not image_url:
                image_url = f"https://loremflickr.com/1024/576/{query_tags}?random={seed}"

            on_set_bg = _jget_dict(self.connection_args, "onSetBackgroundImage")
            if _is_function(on_set_bg):
                on_set_bg(image_url)
                self._send_tool_response(
                    fid, name, obj(result="Background image changed.", imageUrl=image_url)
                )
                send_image_to_ai(image_url)
            else:
                self._send_tool_response(
                    fid, name, obj(error="Background change not supported by current frontend")
                )

        def on_search_error(error):
            console.error("Failed to search background image:", error)
            fallback_url = f"https://loremflickr.com/1024/576/{query_tags}?random={seed}"
            on_set_bg = _jget_dict(self.connection_args, "onSetBackgroundImage")
            if _is_function(on_set_bg):
                on_set_bg(fallback_url)
                self._send_tool_response(
                    fid,
                    name,
                    obj(result="Background image changed (fallback).", imageUrl=fallback_url),
                )
                send_image_to_ai(fallback_url)
            else:
                self._send_tool_response(
                    fid, name, obj(error="Background change not supported by current frontend")
                )

        promise = window.fetch(search_url)
        promise = promise.then(proxy(lambda r: r.json()))
        promise = promise.then(proxy(on_search_data))
        promise.catch(proxy(on_search_error))

    async def _execute_control_action(self, fid, tool_name, action_fn, default_message):
        try:
            if not action_fn:
                self._send_tool_response(fid, tool_name, obj(result=default_message))
                return

            result = action_fn()
            result = await self._maybe_await(result)

            err = _jget(result, "error") if not isinstance(result, str) else None
            if result is not None and not isinstance(result, str) and isinstance(err, str):
                self._send_tool_response(fid, tool_name, obj(result=err))
                return
            if isinstance(result, str) and len(result.strip()) > 0:
                self._send_tool_response(fid, tool_name, obj(result=result.strip()))
                return
            if result is False:
                self._send_tool_response(fid, tool_name, obj(result=default_message))
                return

            self._send_tool_response(fid, tool_name, obj(result="Done."))
        except Exception as error:  # noqa: BLE001
            console.error(f"{tool_name} failed", str(error))
            self._send_tool_response(
                fid, tool_name, obj(result=f"Action failed: {str(error) or 'unknown error'}")
            )

    async def _execute_vision_capture(self, fid, tool_name, capture_fn, unavailable_message):
        try:
            if not capture_fn:
                self._send_tool_response(fid, tool_name, obj(result=unavailable_message))
                return

            frame = capture_fn()
            frame = await self._maybe_await(frame)

            err = _jget(frame, "error") if not isinstance(frame, str) else None
            if frame is not None and not isinstance(frame, str) and isinstance(err, str):
                self._send_tool_response(fid, tool_name, obj(result=err))
                return
            if not isinstance(frame, str) or len(frame) == 0:
                self._send_tool_response(fid, tool_name, obj(result=unavailable_message))
                return

            delivered = await self._send_realtime_image(frame)
            if not delivered:
                self._send_tool_response(
                    fid,
                    tool_name,
                    obj(result="Session is reconnecting. Ask again in a moment."),
                )
                return

            self._send_tool_response(
                fid, tool_name, obj(result="Image delivered. Analyze and respond now.")
            )
        except Exception as error:  # noqa: BLE001
            console.error(f"{tool_name} failed", str(error))
            self._send_tool_response(
                fid, tool_name, obj(result=f"Capture failed: {str(error) or 'unknown error'}")
            )

    def _send_tool_response(self, fid, name, response):
        # Synchronous: sendToolResponse is a void SDK call. Must NOT be a coroutine,
        # otherwise callers that invoke it without await silently drop the tool
        # response and the model stalls (never produces its audio reply).
        if not self.active_session:
            return
        try:
            self.active_session.sendToolResponse(
                obj(functionResponses=to_js([obj(id=fid, name=name, response=response)]))
            )
        except Exception as e:  # noqa: BLE001
            console.error("Tool response failed", str(e))

    async def _send_realtime_image(self, base64_image):
        if not self.active_session or not self.is_session_open:
            return False
        try:
            self.active_session.sendRealtimeInput(
                obj(video=obj(mimeType="image/jpeg", data=base64_image))
            )
            return True
        except Exception as e:  # noqa: BLE001
            console.error("Image send failed", str(e))
            return False

    # ------------------------------------------------------------------
    # Microphone capture (Web Audio API driven from Python)
    # ------------------------------------------------------------------
    async def start_microphone(self):
        if self.is_recording:
            return
        try:
            self._reset_voice_activity_state()
            self._set_user_speaking_state(False, True)

            audio_ctx_ctor = getattr(window, "AudioContext", None) or getattr(
                window, "webkitAudioContext", None
            )
            self.audio_context = audio_ctx_ctor.new(obj(sampleRate=16000))

            self.media_stream = await window.navigator.mediaDevices.getUserMedia(
                obj(
                    audio=obj(
                        channelCount=1,
                        sampleRate=16000,
                        echoCancellation=True,
                        noiseSuppression=True,
                        autoGainControl=True,
                    )
                )
            )

            should_abort_mic_start = (
                not self.audio_context
                or self.is_disconnecting
                or not self.active_session
                or not self.is_session_open
            )
            if should_abort_mic_start:
                self._stop_media_stream_tracks()
                self.media_stream = None
                try:
                    if self.audio_context:
                        await self.audio_context.close()
                except Exception:  # noqa: BLE001
                    pass
                self.audio_context = None
                return

            if not self.worklet_node:
                blob_url = ""
                blob = window.Blob.new(to_js([WORKLET_CODE]), obj(type="application/javascript"))
                try:
                    blob_url = window.URL.createObjectURL(blob)
                    await self.audio_context.audioWorklet.addModule(blob_url)
                finally:
                    if blob_url:
                        window.URL.revokeObjectURL(blob_url)

                should_abort_after_worklet = (
                    not self.audio_context
                    or self.is_disconnecting
                    or not self.active_session
                    or not self.is_session_open
                )
                if should_abort_after_worklet:
                    self._stop_media_stream_tracks()
                    self.media_stream = None
                    try:
                        if self.audio_context:
                            await self.audio_context.close()
                    except Exception:  # noqa: BLE001
                        pass
                    self.audio_context = None
                    return

                self.media_source_node = self.audio_context.createMediaStreamSource(
                    self.media_stream
                )
                self.worklet_node = window.AudioWorkletNode.new(
                    self.audio_context, "pcm-processor"
                )

                def on_port_message(e):
                    if self.is_recording:
                        self._process_audio_chunk(e.data)

                self.worklet_node.port.onmessage = proxy(on_port_message)
                self.media_source_node.connect(self.worklet_node)
            self.is_recording = True
        except Exception as e:  # noqa: BLE001
            self._stop_media_stream_tracks()
            self.media_stream = None
            if self.media_source_node:
                self.media_source_node.disconnect()
            self.media_source_node = None
            if self.worklet_node:
                self.worklet_node.port.onmessage = None
                self.worklet_node.disconnect()
            self.worklet_node = None
            try:
                if self.audio_context:
                    await self.audio_context.close()
            except Exception:  # noqa: BLE001
                pass
            self.audio_context = None
            console.error("Mic Error:", str(e))

    def stop_microphone(self):
        self.is_recording = False
        self._set_user_speaking_state(False, True)
        self._reset_voice_activity_state()
        self._stop_media_stream_tracks()
        self.media_stream = None
        if self.media_source_node:
            self.media_source_node.disconnect()
        self.media_source_node = None
        if self.worklet_node:
            self.worklet_node.port.onmessage = None
            self.worklet_node.disconnect()
        self.worklet_node = None
        if self.audio_context:
            self.audio_context.close()
        self.audio_context = None
        self.input_buffer_index = 0

    def _stop_media_stream_tracks(self):
        if self.media_stream:
            try:
                for track in self.media_stream.getTracks():
                    track.stop()
            except Exception:  # noqa: BLE001
                pass

    def _process_audio_chunk(self, pcm16_data):
        if self.is_disconnecting:
            return
        if pcm16_data is None:
            return
        length = pcm16_data.length
        for i in range(length):
            self.input_buffer[self.input_buffer_index] = pcm16_data[i]
            self.input_buffer_index += 1
            if self.input_buffer_index == self.input_buffer.length:
                self._flush_input_buffer()

    def _flush_input_buffer(self):
        if self.input_buffer_index <= 0:
            return

        audio_chunk = self.input_buffer.slice(0, self.input_buffer_index)
        self._remember_recent_audio_chunk(audio_chunk)
        self.input_buffer_index = 0

        if (
            not self.active_session
            or self.is_disconnecting
            or not self.is_session_open
            or self.is_restoring_reconnect_context
        ):
            return

        base64 = self._encode_int16_to_base64(audio_chunk)
        if not base64:
            return
        window.Promise.resolve(self._send_to_gemini(base64))

    async def _send_to_gemini(self, base64_audio):
        if not self.active_session or not self.is_session_open:
            return
        try:
            self.active_session.sendRealtimeInput(
                obj(audio=obj(mimeType="audio/pcm;rate=16000", data=base64_audio))
            )
        except Exception as e:  # noqa: BLE001
            err_msg = str(_jget(e, "message", default="") or str(e)).lower()
            if "closed" not in err_msg and "closing" not in err_msg:
                console.error("Audio Send Error:", str(e))

    # ------------------------------------------------------------------
    # Voice activity state
    # ------------------------------------------------------------------
    def _is_meaningful_speech_text(self, text):
        if not isinstance(text, str):
            return False
        import re

        cleaned = re.sub(r"<[^>]*>", " ", text)
        cleaned = re.sub(r"\[[^\]]*]", " ", cleaned)
        cleaned = re.sub(
            r"\b(noise|silence|music|laughter|laugh|breath|breathing|applause)\b",
            " ",
            cleaned,
            flags=re.IGNORECASE,
        )
        cleaned = cleaned.strip()
        if not cleaned:
            return False
        return bool(re.search(r"[A-Za-z]{2,}|[0-9]{2,}", cleaned))

    def _arm_user_speech_release_timer(self):
        self._clear_user_speech_release_timer()

        def _release():
            self.user_speech_release_timer = None
            self._set_user_speaking_state(False)

        self.user_speech_release_timer = _set_timeout(_release, self.user_speech_release_ms)

    def _clear_user_speech_release_timer(self):
        if not self.user_speech_release_timer:
            return
        _clear_timeout(self.user_speech_release_timer)
        self.user_speech_release_timer = None

    def _set_user_speaking_state(self, is_speaking, force=False):
        nxt = bool(is_speaking)
        if not force and self.is_user_speaking == nxt:
            return
        self.is_user_speaking = nxt
        if not nxt:
            self._clear_user_speech_release_timer()

        if _is_function(self.on_user_speech_state_change):
            try:
                self.on_user_speech_state_change(nxt)
            except Exception as error:  # noqa: BLE001
                console.error("User speech state callback failed:", str(error))

    def _reset_voice_activity_state(self):
        self._clear_user_speech_release_timer()

    # ------------------------------------------------------------------
    # Disconnect
    # ------------------------------------------------------------------
    def disconnect(self, reason="User disconnected"):
        if self.is_disconnecting:
            return
        try:
            storage = self._get_storage()
            if storage is not None:
                storage.setItem("vrm_session_ended", "true")
        except Exception as e:  # noqa: BLE001
            console.warn("Failed to set vrm_session_ended flag:", str(e))
        if (
            not self.active_session
            and not self.is_recording
            and not self.reconnect_timer
            and not self.on_disconnect_callback
        ):
            return
        self.is_disconnecting = True
        self._clear_reconnect_timer()
        self.is_reconnecting = False
        self.reconnect_attempts = 0
        console.log(f"🔌 Disconnecting: {reason}")

        self.is_session_open = False
        self._stash_pending_input_buffer_for_reconnect()
        self.stop_microphone()

        on_transcription = _jget_dict(self.connection_args, "onTranscription")
        self._flush_transcriptions(
            True, on_transcription, "both", {"clearUserBuffer": True}
        )

        if self.active_session:
            try:
                self.active_session.close()
            except Exception as error:  # noqa: BLE001
                console.warn("Failed to close live session cleanly", str(error))
            self.active_session = None
        cb = self.on_disconnect_callback
        if _is_function(cb):
            cb(reason)
        self.on_disconnect_callback = None

    # ------------------------------------------------------------------
    # Tool declarations
    # ------------------------------------------------------------------
    def _get_tools(self, anim_string):
        function_declarations = [
            js_dict(
                {
                    "name": "trigger_animation",
                    "description": "Trigger an avatar animation when it fits the reply.",
                    "parameters": js_dict(
                        {
                            "type": "OBJECT",
                            "properties": js_dict(
                                {
                                    "animation_name": js_dict(
                                        {
                                            "type": "STRING",
                                            "description": f"Use one available animation name. "
                                            f"Examples: {anim_string}",
                                        }
                                    )
                                }
                            ),
                            "required": to_js(["animation_name"]),
                        }
                    ),
                }
            ),
            js_dict(
                {
                    "name": "set_background_image",
                    "description": "Change the background image of the 3D scene. The AI can "
                    "generate a background based on a prompt or describe a scene to load.",
                    "parameters": js_dict(
                        {
                            "type": "OBJECT",
                            "properties": js_dict(
                                {
                                    "prompt": js_dict(
                                        {
                                            "type": "STRING",
                                            "description": "A prompt describing the background "
                                            'image to generate (e.g. Enclose your exact phrase in '
                                            'quotation marks (e.g., "Martin Luther King Jr.") to '
                                            "force the search to look for the exact string rather "
                                            "than individual words.). And the images chosen by may "
                                            "not be accurate since they are from the WIKIPEDIA.",
                                        }
                                    )
                                }
                            ),
                            "required": to_js(["prompt"]),
                        }
                    ),
                }
            ),
            js_dict(
                {
                    "name": "set_expression",
                    "description": 'Set the avatar facial expression. Use a specific emotion or '
                    '"neutral".',
                    "parameters": js_dict(
                        {
                            "type": "OBJECT",
                            "properties": js_dict(
                                {
                                    "expression": js_dict(
                                        {
                                            "type": "STRING",
                                            "description": "Examples: happy, smug, angry, sad, "
                                            "surprised, bored, nervous, disgusted, flirty, tired, "
                                            "thinking, neutral.",
                                        }
                                    ),
                                    "duration": js_dict(
                                        {
                                            "type": "NUMBER",
                                            "description": "Duration in seconds.",
                                        }
                                    ),
                                }
                            ),
                            "required": to_js(["expression"]),
                        }
                    ),
                }
            ),
            js_dict(
                {
                    "name": "look_at_user",
                    "description": "Capture a live image from the user camera when vision is "
                    "needed.",
                }
            ),
            js_dict(
                {
                    "name": "look_at_screen",
                    "description": "Capture the user's shared screen when screen context is "
                    "needed.",
                }
            ),
            js_dict({"name": "turn_off_camera", "description": "Stop camera-based vision."}),
            js_dict({"name": "turn_off_screen", "description": "Stop screen-based vision."}),
            js_dict(
                {
                    "name": "set_user_name",
                    "description": "Save user name.",
                    "parameters": js_dict(
                        {
                            "type": "OBJECT",
                            "properties": js_dict(
                                {"name": js_dict({"type": "STRING"})}
                            ),
                            "required": to_js(["name"]),
                        }
                    ),
                }
            ),
            js_dict(
                {
                    "name": "save_memory",
                    "description": "Persist a fact about the user.",
                    "parameters": js_dict(
                        {
                            "type": "OBJECT",
                            "properties": js_dict(
                                {
                                    "key": js_dict({"type": "STRING"}),
                                    "value": js_dict({"type": "STRING"}),
                                }
                            ),
                            "required": to_js(["key", "value"]),
                        }
                    ),
                }
            ),
            js_dict(
                {
                    "name": "delete_memory",
                    "description": "Forget a fact about the user.",
                    "parameters": js_dict(
                        {
                            "type": "OBJECT",
                            "properties": js_dict({"key": js_dict({"type": "STRING"})}),
                            "required": to_js(["key"]),
                        }
                    ),
                }
            ),
            js_dict(
                {
                    "name": "start_timer",
                    "description": "Start an on-screen countdown timer.",
                    "parameters": js_dict(
                        {
                            "type": "OBJECT",
                            "properties": js_dict(
                                {
                                    "duration_seconds": js_dict(
                                        {
                                            "type": "NUMBER",
                                            "description": "Countdown duration in seconds.",
                                        }
                                    ),
                                    "label": js_dict(
                                        {
                                            "type": "STRING",
                                            "description": "Short label for the timer.",
                                        }
                                    ),
                                }
                            ),
                            "required": to_js(["duration_seconds"]),
                        }
                    ),
                }
            ),
            js_dict(
                {
                    "name": "cancel_timer",
                    "description": "Cancel and hide the active on-screen timer.",
                }
            ),
            js_dict(
                {
                    "name": "end_conversation",
                    "description": "End the current active conversation session and disconnect "
                    "the call.",
                }
            ),
            js_dict(
                {
                    "name": "report_behavior",
                    "description": "Report dangerous or explicit behavior to the developer.",
                    "parameters": js_dict(
                        {
                            "type": "OBJECT",
                            "properties": js_dict(
                                {
                                    "reason": js_dict(
                                        {
                                            "type": "STRING",
                                            "description": "Description of the unusual behavior",
                                        }
                                    ),
                                    "severity": js_dict(
                                        {
                                            "type": "STRING",
                                            "enum": to_js(["low", "critical"]),
                                            "description": 'Use "critical" for '
                                            'NSFW/Nudity/Explicit content. Use "low" for '
                                            "creepy/weird text.",
                                        }
                                    ),
                                }
                            ),
                            "required": to_js(["reason", "severity"]),
                        }
                    ),
                }
            ),
        ]

        return to_js(
            [
                obj(functionDeclarations=to_js(function_declarations)),
                obj(google_search=obj()),
            ]
        )

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _call(self, fn, *args):
        """Invoke an optional callback (JS optional-chaining `fn?.(...)` equivalent)."""
        if _is_function(fn):
            try:
                return fn(*args)
            except Exception as error:  # noqa: BLE001
                console.error("Callback failed:", str(error))
        return None

    async def _maybe_await(self, value):
        """Await a value if it is awaitable (Python coroutine or JS thenable)."""
        if value is None:
            return None
        if hasattr(value, "__await__"):
            return await value
        # JS Promise / thenable exposes `.then`.
        if hasattr(value, "then") and callable(getattr(value, "then", None)):
            return await value
        return value

    def _then(self, awaitable, on_result):
        """Attach a result callback to a Python coroutine via a JS Promise."""
        promise = window.Promise.resolve(awaitable)
        promise.then(proxy(on_result))

    async def _sleep_ms(self, ms):
        """await-able sleep implemented with a JS Promise + setTimeout."""
        def executor(resolve, reject=None):
            window.setTimeout(proxy(lambda *a: resolve(None)), ms)

        await window.Promise.new(proxy(executor))

    # ------------------------------------------------------------------
    # camelCase aliases for the orchestrator (index.js parity)
    # ------------------------------------------------------------------
    # `isSessionOpen` is read as a bare attribute in index.js; expose a property
    # that proxies the snake_case instance attribute so either name works.
    @property
    def isSessionOpen(self):  # noqa: N802
        return self.is_session_open

    @isSessionOpen.setter
    def isSessionOpen(self, value):  # noqa: N802
        self.is_session_open = value

    updateToken = update_token
    setTokenProvider = set_token_provider
    setConversationProfile = set_conversation_profile
    clearSessionResumption = clear_session_resumption
    connectLive = connect_live
    sendText = send_text
    startMicrophone = start_microphone
    stopMicrophone = stop_microphone


def _jget_dict(d, key, default=None):
    """getattr-style access for the connection_args Python dict (may be None)."""
    if not isinstance(d, dict):
        return default
    return d.get(key, default)
