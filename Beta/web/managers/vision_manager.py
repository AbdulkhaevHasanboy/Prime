"""VisionManager — Python port of managers/visionManager.js.

Drives getUserMedia / getDisplayMedia / canvas capture / MediaRecorder from Python
for camera + screen frames and short video clips. JS Promises (video-ready,
clip-recording) are bridged to asyncio Futures.
"""

import asyncio

from js import window, document, navigator, setTimeout, clearTimeout, setInterval, clearInterval
from pyodide.ffi import to_js

from .jsutil import obj, proxy


class VisionManager:
    def __init__(self):
        self.video_element = None
        self.canvas_element = None
        self.stream = None
        self.is_initialized = False
        self.screen_stream = None
        self.screen_video_element = None
        self.is_sharing_screen = False
        self.screen_share_interval = None
        self.camera_interval = None
        self.on_camera_frame = None
        self.on_screen_frame = None
        self.on_state_change = None
        self.is_recording_clip = False
        self.camera_denied = False

    async def initialize(self):
        if self.is_initialized:
            return True
        self.video_element = document.createElement("video")
        self.video_element.style.display = "none"
        self.video_element.autoplay = True
        self.video_element.muted = True
        self.video_element.setAttribute("playsinline", "true")
        document.body.appendChild(self.video_element)

        self.canvas_element = document.createElement("canvas")
        self.canvas_element.style.display = "none"

        self.is_initialized = True
        return True

    def is_video_track_live(self, stream):
        if not stream:
            return False
        tracks = stream.getVideoTracks()
        if tracks.length == 0:
            return False
        track = tracks[0]
        return bool(track) and track.readyState == "live" and not track.muted

    async def ensure_video_ready(self, video, timeout_ms=1200):
        if not video:
            return False
        if video.videoWidth > 0 and video.videoHeight > 0:
            if video.paused:
                try:
                    await video.play()
                except Exception:  # noqa: BLE001
                    pass
            return True

        fut = asyncio.get_event_loop().create_future()
        state = {"resolved": False, "timeout_id": None}

        def finish(event=None):
            if state["resolved"]:
                return
            state["resolved"] = True
            try:
                video.removeEventListener("loadedmetadata", finish_proxy)
                video.removeEventListener("playing", finish_proxy)
            except Exception:  # noqa: BLE001
                pass
            if state["timeout_id"] is not None:
                clearTimeout(state["timeout_id"])
            if not fut.done():
                fut.set_result(True)

        finish_proxy = proxy(finish)
        video.addEventListener("loadedmetadata", finish_proxy)
        video.addEventListener("playing", finish_proxy)
        state["timeout_id"] = setTimeout(finish_proxy, timeout_ms)

        await fut

        if video.paused:
            try:
                await video.play()
            except Exception:  # noqa: BLE001
                pass
        return video.videoWidth > 0 and video.videoHeight > 0

    def stop_camera(self):
        if self.stream:
            for track in self.stream.getTracks():
                track.stop()
        self.stream = None
        if self.video_element:
            self.video_element.srcObject = None

    async def start_camera(self):
        if not self.is_initialized:
            await self.initialize()
        if self.camera_denied:
            print("VisionManager: camera access is blocked due to previous user denial.")
            return False

        if self.stream and self.is_video_track_live(self.stream):
            if self.video_element and self.video_element.srcObject != self.stream:
                self.video_element.srcObject = self.stream
            await self.ensure_video_ready(self.video_element)
            return True

        self.stop_camera()
        try:
            print("VisionManager: requesting camera access...")
            self.stream = await navigator.mediaDevices.getUserMedia(
                obj(video=obj(width=obj(ideal=640), height=obj(ideal=480), facingMode="user"))
            )
            tracks = self.stream.getVideoTracks()
            if tracks.length > 0:
                tracks[0].onended = proxy(lambda event=None: self.stop_camera())
            if self.video_element:
                self.video_element.srcObject = self.stream
                await self.ensure_video_ready(self.video_element)
            return True
        except Exception as error:  # noqa: BLE001
            print(f"VisionManager: camera failed {error}")
            name = getattr(error, "name", "")
            if name in ("NotAllowedError", "PermissionDeniedError"):
                self.camera_denied = True
            self.stop_camera()
            return False

    async def capture_frame(self, retry=True):
        if not self.stream or not self.is_video_track_live(self.stream):
            success = await self.start_camera()
            if not success:
                return None
        else:
            await self.ensure_video_ready(self.video_element)

        video = self.video_element
        if not video or video.videoWidth == 0 or video.videoHeight == 0:
            if not retry:
                return None
            self.stop_camera()
            return await self.capture_frame(False)

        scale = min(1, 640 / video.videoWidth)
        width = int(video.videoWidth * scale)
        height = int(video.videoHeight * scale)
        if self.canvas_element:
            self.canvas_element.width = width
            self.canvas_element.height = height
            ctx = self.canvas_element.getContext("2d")
            if ctx:
                ctx.drawImage(video, 0, 0, width, height)
            data_url = self.canvas_element.toDataURL("image/jpeg", 0.7)
            return data_url[data_url.find(",") + 1:]
        return None

    async def start_screen_share(self, on_frame_callback=None):
        self.on_screen_frame = on_frame_callback
        if self.screen_stream and self.is_video_track_live(self.screen_stream):
            return True
        self.stop_screen_share()
        try:
            if not navigator.mediaDevices or not getattr(navigator.mediaDevices, "getDisplayMedia", None):
                print("Screen sharing not supported (or permission disallowed).")
                return False
            self.screen_stream = await navigator.mediaDevices.getDisplayMedia(
                obj(video=obj(cursor="always"), audio=False)
            )
            tracks = self.screen_stream.getVideoTracks()
            if tracks.length > 0:
                tracks[0].onended = proxy(lambda event=None: self.stop_screen_share())
            video = document.createElement("video")
            video.srcObject = self.screen_stream
            video.muted = True
            try:
                await video.play()
            except Exception:  # noqa: BLE001
                pass
            self.screen_video_element = video
            await self.ensure_video_ready(video)
            self.is_sharing_screen = True
            if self.on_state_change:
                self.on_state_change(True)

            if self.on_screen_frame:
                def grab(event=None):
                    if not self.is_sharing_screen:
                        return
                    frame = self.capture_video_frame(video, 1280)
                    if frame and self.on_screen_frame:
                        self.on_screen_frame(frame)
                self.screen_share_interval = setInterval(proxy(grab), 1000)
            return True
        except Exception as error:  # noqa: BLE001
            print(f"VisionManager: screen share failed {error}")
            self.stop_screen_share()
            return False

    def stop_screen_share(self):
        if not self.is_sharing_screen and not self.screen_stream:
            return
        self.is_sharing_screen = False
        if self.on_state_change:
            self.on_state_change(False)
        self.on_screen_frame = None
        if self.screen_share_interval is not None:
            clearInterval(self.screen_share_interval)
            self.screen_share_interval = None
        if self.screen_stream:
            for track in self.screen_stream.getTracks():
                track.stop()
        self.screen_stream = None
        self.screen_video_element = None

    def capture_screen(self):
        if not self.is_sharing_screen or not self.screen_video_element:
            return None
        if not self.screen_stream or not self.is_video_track_live(self.screen_stream):
            self.stop_screen_share()
            return None
        if self.screen_video_element.videoWidth == 0 or self.screen_video_element.videoHeight == 0:
            return None
        return self.capture_video_frame(self.screen_video_element, 1920)

    def capture_video_frame(self, video, max_width):
        if video.videoWidth == 0 or video.videoHeight == 0:
            return None
        scale = min(1, max_width / video.videoWidth)
        width = int(video.videoWidth * scale)
        height = int(video.videoHeight * scale)
        if self.canvas_element:
            self.canvas_element.width = width
            self.canvas_element.height = height
            ctx = self.canvas_element.getContext("2d")
            if ctx:
                ctx.drawImage(video, 0, 0, width, height)
            data_url = self.canvas_element.toDataURL("image/jpeg", 0.6)
            return data_url[data_url.find(",") + 1:]
        return None

    async def capture_camera_clip(self, duration_ms=1800):
        if not self.stream or not self.is_video_track_live(self.stream):
            success = await self.start_camera()
            if not success:
                return None
        return await self.record_stream_clip(self.stream, duration_ms)

    async def capture_screen_clip(self, duration_ms=1800):
        if not self.screen_stream or not self.is_video_track_live(self.screen_stream):
            return None
        return await self.record_stream_clip(self.screen_stream, duration_ms)

    async def record_stream_clip(self, stream, duration_ms=1800):
        if not stream or self.is_recording_clip or not hasattr(window, "MediaRecorder"):
            return None

        mime_candidates = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm"]
        mime_type = ""
        for c in mime_candidates:
            if window.MediaRecorder.isTypeSupported(c):
                mime_type = c
                break

        self.is_recording_clip = True
        fut = asyncio.get_event_loop().create_future()
        ctx = {"chunks": [], "recorder": None, "timeout_id": None}

        def finalize(blob=None):
            if ctx["timeout_id"] is not None:
                clearTimeout(ctx["timeout_id"])
            self.is_recording_clip = False
            if not fut.done():
                fut.set_result(blob)

        try:
            opts = obj(mimeType=mime_type, videoBitsPerSecond=900000) if mime_type else obj(videoBitsPerSecond=900000)
            ctx["recorder"] = window.MediaRecorder.new(stream, opts)
        except Exception:  # noqa: BLE001
            finalize(None)
            return await fut

        def on_data(event):
            if event.data and event.data.size > 0:
                ctx["chunks"].append(event.data)
        ctx["recorder"].ondataavailable = proxy(on_data)
        ctx["recorder"].onerror = proxy(lambda event=None: finalize(None))

        def on_stop(event=None):
            if len(ctx["chunks"]) == 0:
                finalize(None)
                return
            blob_type = mime_type or "video/webm"
            finalize(window.Blob.new(to_js(ctx["chunks"]), obj(type=blob_type)))
        ctx["recorder"].onstop = proxy(on_stop)

        try:
            ctx["recorder"].start()
        except Exception:  # noqa: BLE001
            finalize(None)
            return await fut

        def on_timeout(event=None):
            rec = ctx["recorder"]
            if rec and rec.state != "inactive":
                rec.stop()
            else:
                finalize(None)
        ctx["timeout_id"] = setTimeout(proxy(on_timeout), max(600, duration_ms))

        return await fut

    def reset(self):
        self.camera_denied = False
        self.stop_camera()
        self.stop_screen_share()

    def cleanup(self):
        self.stop_screen_share()
        self.stop_camera()
        self.camera_denied = False
        if self.video_element:
            self.video_element.pause()
            self.video_element.srcObject = None
            if self.video_element.parentNode:
                document.body.removeChild(self.video_element)
        if self.screen_video_element:
            self.screen_video_element.pause()
            self.screen_video_element.srcObject = None
        self.video_element = None
        self.canvas_element = None
        self.screen_video_element = None
        self.is_initialized = False

    # camelCase aliases for orchestrator parity
    captureFrame = capture_frame
    captureScreen = capture_screen
    captureCameraClip = capture_camera_clip
    captureScreenClip = capture_screen_clip
    startScreenShare = start_screen_share
    stopScreenShare = stop_screen_share
    startCamera = start_camera
    stopCamera = stop_camera
