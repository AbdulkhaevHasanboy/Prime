"""AudioManager — Python port of managers/audioManager.js.

Drives the Web Audio API (AudioContext / AnalyserNode / BufferSource) from Python
to play streamed PCM16 @ 24kHz from Gemini, with RMS-based mouth lip-sync applied
to the VRM's `aa` expression. Faithful behavioral port.
"""

import numpy as np
from js import window, requestAnimationFrame, cancelAnimationFrame
from pyodide.ffi import to_js

from .jsutil import proxy


class AudioManager:
    def __init__(self):
        self.audio_ctx = None
        self.analyser = None
        self.next_start_time = 0.0
        self.mouth_raf = None
        self.mouth_release_raf = None
        self.active_sources = []
        self.on_speech_start = None
        self.on_speech_end = None
        self.on_mouth_open_change = None
        self.is_playing = False
        self.is_user_speaking = False
        self.current_vrm = None
        self.mouth_open_value = 0.0
        self.time_domain_data = None

    async def initialize(self):
        if self.audio_ctx:
            return
        AC = window.AudioContext if hasattr(window, "AudioContext") and window.AudioContext else window.webkitAudioContext
        self.audio_ctx = AC.new()
        self.analyser = self.audio_ctx.createAnalyser()
        self.analyser.fftSize = 256
        self.analyser.connect(self.audio_ctx.destination)
        self.time_domain_data = window.Uint8Array.new(self.analyser.frequencyBinCount)
        print("Audio System Ready")

    async def queue_audio(self, int16_data):
        vrm = window.currentVrm
        if vrm:
            self.current_vrm = vrm
        if self.is_user_speaking:
            return
        await self.play_chunk(int16_data, vrm or self.current_vrm)

    async def play_chunk(self, int16_data, vrm=None):
        if self.is_user_speaking:
            return
        if not self.audio_ctx:
            await self.initialize()
        if not self.audio_ctx:
            return
        if self.audio_ctx.state == "suspended":
            await self.audio_ctx.resume()

        if vrm:
            self.current_vrm = vrm
        if self.mouth_release_raf is not None:
            cancelAnimationFrame(self.mouth_release_raf)
            self.mouth_release_raf = None

        self.set_playback_state(True)

        # Convert Int16 -> Float32 [-1, 1] using numpy for speed.
        f32 = self._to_float32(int16_data)
        length = int(f32.shape[0])

        audio_buffer = self.audio_ctx.createBuffer(1, length, 24000)
        audio_buffer.copyToChannel(window.Float32Array.new(to_js(f32)), 0)

        source = self.audio_ctx.createBufferSource()
        source.buffer = audio_buffer
        source.connect(self.analyser)

        now = self.audio_ctx.currentTime
        if self.next_start_time < now:
            self.next_start_time = now + 0.05

        source.start(self.next_start_time)
        self.next_start_time += audio_buffer.duration

        self.active_sources.append(source)

        def on_ended(event=None, _s=source):
            if _s in self.active_sources:
                self.active_sources.remove(_s)

        source.onended = proxy(on_ended)

        if self.current_vrm and self.mouth_raf is None:
            self.start_mouth_sync(self.current_vrm)

    @staticmethod
    def _to_float32(int16_data):
        """Accept a JS Int16Array (or Python buffer) and return a float32 numpy array."""
        try:
            mv = int16_data.to_py()  # JS typed array -> memoryview
            arr = np.frombuffer(mv, dtype=np.int16)
        except (AttributeError, TypeError):
            arr = np.asarray(int16_data, dtype=np.int16)
        return (arr.astype(np.float32) / 32768.0)

    def start_mouth_sync(self, vrm):
        def tick(timestamp=None):
            if not self.audio_ctx or not self.analyser:
                return
            if self.is_user_speaking:
                self.stop_mouth_sync(vrm)
                self.set_playback_state(False)
                return
            if self.audio_ctx.currentTime > self.next_start_time + 0.1:
                self.stop_mouth_sync(vrm)
                self.set_playback_state(False)
                return

            if (self.time_domain_data is None
                    or self.time_domain_data.length != self.analyser.frequencyBinCount):
                self.time_domain_data = window.Uint8Array.new(self.analyser.frequencyBinCount)

            self.analyser.getByteTimeDomainData(self.time_domain_data)
            data = np.frombuffer(self.time_domain_data.to_py(), dtype=np.uint8).astype(np.float32)
            vals = (data - 128.0) / 128.0
            volume = float(np.sqrt(np.mean(vals * vals)))

            target_open = min(volume * 5.0, 0.5)
            smoothing = 0.42 if target_open > self.mouth_open_value else 0.12
            self.mouth_open_value += (target_open - self.mouth_open_value) * smoothing

            em = getattr(vrm, "expressionManager", None)
            if em:
                em.setValue("aa", self.mouth_open_value)
                em.update()

            self.mouth_raf = requestAnimationFrame(self._mouth_tick_proxy)

        self._mouth_tick_proxy = proxy(tick)
        self.mouth_raf = requestAnimationFrame(self._mouth_tick_proxy)

    def set_user_speaking_state(self, is_speaking):
        nxt = bool(is_speaking)
        if self.is_user_speaking == nxt:
            return
        self.is_user_speaking = nxt
        if self.is_user_speaking:
            self.interrupt_playback()

    def interrupt_playback(self):
        for source in self.active_sources:
            try:
                source.onended = None
                source.stop(0)
            except Exception:  # noqa: BLE001
                pass
        self.active_sources = []
        if self.audio_ctx:
            self.next_start_time = self.audio_ctx.currentTime
        else:
            self.next_start_time = 0
        self.stop_mouth_sync(self.current_vrm or window.currentVrm or None)
        self.set_playback_state(False)

    def stop_mouth_sync(self, vrm=None):
        if self.mouth_raf is not None:
            cancelAnimationFrame(self.mouth_raf)
            self.mouth_raf = None
        target = vrm or self.current_vrm or window.currentVrm or None
        self.release_mouth(target)

    def release_mouth(self, vrm=None):
        target = vrm or self.current_vrm or window.currentVrm or None
        if not target or not getattr(target, "expressionManager", None):
            self.mouth_open_value = 0.0
            return
        if self.mouth_release_raf is not None:
            cancelAnimationFrame(self.mouth_release_raf)
            self.mouth_release_raf = None

        def tick(timestamp=None):
            self.mouth_open_value += (0 - self.mouth_open_value) * 0.14
            if self.mouth_open_value <= 0.01:
                self.mouth_open_value = 0.0
                target.expressionManager.setValue("aa", 0)
                target.expressionManager.update()
                self.mouth_release_raf = None
                return
            target.expressionManager.setValue("aa", self.mouth_open_value)
            target.expressionManager.update()
            self.mouth_release_raf = requestAnimationFrame(self._mouth_release_proxy)

        self._mouth_release_proxy = proxy(tick)
        self.mouth_release_raf = requestAnimationFrame(self._mouth_release_proxy)

    def set_playback_state(self, next_is_playing):
        if self.is_playing == next_is_playing:
            return
        self.is_playing = next_is_playing
        if next_is_playing:
            if self.on_speech_start:
                self.on_speech_start()
        else:
            if self.on_speech_end:
                self.on_speech_end()

    def cleanup(self):
        self.interrupt_playback()
        if self.mouth_release_raf is not None:
            cancelAnimationFrame(self.mouth_release_raf)
            self.mouth_release_raf = None
        if self.audio_ctx:
            self.audio_ctx.close()
        self.audio_ctx = None

    # camelCase aliases for orchestrator parity
    queueAudio = queue_audio
    setUserSpeakingState = set_user_speaking_state
