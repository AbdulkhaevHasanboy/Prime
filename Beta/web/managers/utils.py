"""Utils — Python port of managers/utils.js."""

import asyncio

from js import window


class Utils:
    @staticmethod
    async def delay(ms):
        await asyncio.sleep(ms / 1000.0)

    @staticmethod
    def create_error_handler(context):
        def handler(error):
            print(f"Error in {context}: {error}")
            return {"message": getattr(error, "message", str(error))}
        return handler

    @staticmethod
    def get_feature_support():
        return {
            "webgl": bool(getattr(window, "WebGLRenderingContext", None)),
            "webaudio": bool(getattr(window, "AudioContext", None) or getattr(window, "webkitAudioContext", None)),
            "speechRecognition": bool(getattr(window, "SpeechRecognition", None) or getattr(window, "webkitSpeechRecognition", None)),
            "worklet": bool(getattr(window, "AudioContext", None) and getattr(window.AudioContext.prototype, "audioWorklet", None)),
        }

    # camelCase aliases
    createErrorHandler = create_error_handler
    getFeatureSupport = get_feature_support
