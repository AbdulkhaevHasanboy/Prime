"""AnimationManager — Python port of managers/animationManager.js.

Faithful port of the VRMA clip pipeline + emotional/expression system that the JS
version drove through Three.js. Everything here drives JS objects (THREE,
@pixiv/three-vrm, @pixiv/three-vrm-animation) through Pyodide interop. THREE,
GLTFLoader, VRMAnimationLoaderPlugin and createVRMAnimationClip are exposed on
``window`` by the index.html bootstrap.

Responsibilities ported:
  - VRMA clip loading via GLTFLoader + VRMAnimationLoaderPlugin + createVRMAnimationClip
  - THREE.AnimationMixer playback with crossfade blending
  - Emotional expression mapping / normalization / smoothing
  - Procedural breathing, head sway, emotional posture, blink, micro-expressions, lookAt
  - Audio-driven lip-sync state (speech intensity / visemes / beat estimation)
  - Idle return on finished one-shot clips

snake_case methods are canonical; camelCase aliases are added for the methods the
orchestrator calls so integration is drop-in.

Notes / approximations:
  - The JS version went through a ``cacheManager`` (IndexedDB) before fetching the
    .vrma bytes. There is no cache_manager in the Python port, so we fetch the
    bytes directly via ``window.fetch`` (the browser HTTP cache covers repeat hits),
    matching how vrm_loader.py dropped its IndexedDB cache.
  - ``setExpression`` keeps the JS semantics: ``duration`` is in *seconds* (default
    3.0). The orchestrator port passes through whatever the AI client gives it.
  - The orchestrator calls both ``animationManager.update(delta)`` and
    ``vrm.update(delta)`` itself, so (like the JS original) ``update`` here does NOT
    call ``vrm.update``.
"""

import asyncio
import math
import random

from js import window, console
from pyodide.ffi import to_js

from .jsutil import proxy


def _clamp(value, lo, hi):
    return lo if value < lo else (hi if value > hi else value)


def _lerp(a, b, t):
    return a + (b - a) * t


def _num(value, default=0.0):
    """Mirror Number(value) with a finite-fallback default."""
    try:
        n = float(value)
    except (TypeError, ValueError):
        return default
    if n != n or n in (float("inf"), float("-inf")):
        return default
    return n


class AnimationManager:
    def __init__(self, vrm, camera=None):
        self.THREE = window.THREE
        self.vrm = vrm
        self.camera = camera
        self.mixer = self.THREE.AnimationMixer.new(vrm.scene)
        self.actions = {}
        self.active_action = None

        self.loader = window.GLTFLoader.new()
        self.loader.setCrossOrigin("anonymous")
        # register((parser) => new VRMAnimationLoaderPlugin(parser))
        self.loader.register(proxy(lambda parser: window.VRMAnimationLoaderPlugin.new(parser)))

        self.current_state = "idle"
        self.main_idle = "HappyIdle"
        self.current_expression = "neutral"
        self.target_expression = "neutral"
        self.target_expression_weights = {"neutral": 1}
        self.expression_timer = None  # JS setTimeout handle

        self.core_mood_keys = ["neutral", "happy", "angry", "sad", "relaxed", "surprised"]
        self.mouth_keys = ["aa", "ee", "ih", "oh", "ou"]
        self.active_expression_keys = set(self.core_mood_keys)
        self.supported_expression_track_cache = {}
        self.background_load_task = None

        # Blink State
        self.blink_timer = 0.0
        self.next_blink_time = 3.0
        self.is_blinking = False
        self.blink_duration = 0.15
        self.blink_progress = 0.0
        self._is_double_blinking = False

        # Micro-Expression State
        self.micro_timer = 0.0
        self.micro_intensity = 0.0

        # Speaking State
        self.is_speaking = False
        self.speech_intensity = 0.0
        self.speech_cadence_phase = 0.0
        self.speech_cadence = 0.0
        self.speech_text_cursor = ""
        self.speech_pending_word = ""
        self.speech_beat_queue = 0.0
        self.speech_beat_progress = 0.0
        self.speech_beat_open = 0.0
        self.speech_state = {
            "intensity": 0, "activity": 0, "pulse": 0, "openness": 0,
            "wide": 0, "round": 0, "narrow": 0,
            "aa": 0, "ee": 0, "ih": 0, "oh": 0, "ou": 0,
        }
        self.speech_target = {
            "intensity": 0, "activity": 0, "pulse": 0, "openness": 0,
            "wide": 0, "round": 0, "narrow": 0,
            "aa": 0, "ee": 0, "ih": 0, "oh": 0, "ou": 0,
        }
        self.expression_style = {
            "transitionSpeed": 5.0,
            "microAmplitude": 0.02,
            "microFrequency": 2.0,
            "squint": 0.0,
            "blinkMinInterval": 2.0,
            "blinkMaxInterval": 5.0,
            "blinkDuration": 0.15,
            "mouthBias": {"aa": 0, "ee": 0, "ih": 0, "oh": 0, "ou": 0},
            "mouthInfluenceWhileSpeaking": 0.28,
        }

        # Procedural-state scratch fields (lazily initialized in update())
        self._breath_timer = 0.0
        self._look_at_target = None
        self._saccade_timer = 0.0
        self._saccade_offset = None

        self.expression_map = self._build_expression_map()

        self._apply_expression_target("neutral")
        self.next_blink_time = self._get_next_blink_time()

    # ------------------------------------------------------------------ #
    # Expression map
    # ------------------------------------------------------------------ #
    @staticmethod
    def _build_expression_map():
        return {
            # ===== CORE BASE EMOTIONS (Pure) =====
            "neutral": "neutral", "happy": "happy", "sad": "sad",
            "angry": "angry", "surprised": "surprised", "relaxed": "relaxed",

            # ===== HAPPINESS SPECTRUM =====
            "joy": {"happy": 1.0, "ee": 0.15},
            "ecstatic": {"happy": 1.0, "surprised": 0.3, "aa": 0.25, "ee": 0.25},
            "euphoric": {"happy": 1.0, "relaxed": 0.4, "ee": 0.2},
            "delighted": {"happy": 0.9, "surprised": 0.2, "ee": 0.15},
            "cheerful": {"happy": 0.7, "relaxed": 0.2, "ee": 0.1},
            "content": {"happy": 0.5, "relaxed": 0.5},
            "satisfied": {"happy": 0.4, "relaxed": 0.6},
            "amused": {"happy": 0.6, "surprised": 0.2, "ee": 0.1},
            "giggly": {"happy": 0.8, "surprised": 0.3, "ee": 0.2, "ih": 0.15},
            "grinning": {"happy": 0.9, "ee": 0.25},
            "beaming": {"happy": 1.0, "surprised": 0.1, "ee": 0.2},
            "radiant": {"happy": 0.95, "relaxed": 0.3, "ee": 0.2},
            "blissful": {"happy": 0.8, "relaxed": 0.7, "ee": 0.15},
            "gleeful": {"happy": 0.95, "surprised": 0.2, "ee": 0.2},
            "jubilant": {"happy": 1.0, "surprised": 0.4, "aa": 0.2, "ee": 0.2},
            "thrilled": {"happy": 0.9, "surprised": 0.5, "aa": 0.15, "ee": 0.2},
            "elated": {"happy": 0.95, "surprised": 0.3, "ee": 0.25},
            "overjoyed": {"happy": 1.0, "surprised": 0.5, "aa": 0.25, "ee": 0.25},
            "excited": {"happy": 0.8, "surprised": 0.6, "aa": 0.2, "ee": 0.15},
            "hyper": {"happy": 0.7, "surprised": 0.8, "aa": 0.25, "ee": 0.15},

            # ===== LAUGH/SMILE =====
            "laugh": {"happy": 1.0, "aa": 0.3, "ee": 0.2, "surprised": 0.2},
            "laughing": {"happy": 1.0, "aa": 0.35, "ee": 0.25, "surprised": 0.3},
            "lol": {"happy": 1.0, "aa": 0.3, "ee": 0.2, "surprised": 0.2},
            "lmao": {"happy": 1.0, "aa": 0.4, "ee": 0.25, "surprised": 0.4},
            "smile": {"happy": 0.8, "ee": 0.15},
            "grin": {"happy": 0.9, "ee": 0.25},
            # NOTE: "smirk" is defined twice in the JS object; the later definition
            # (in the confidence/pride section) wins in JS object-literal semantics,
            # so we keep only that one below.
            "chuckle": {"happy": 0.7, "aa": 0.15, "ee": 0.2},

            # ===== SADNESS SPECTRUM =====
            "sorrow": {"sad": 1.0},
            "grief": {"sad": 1.0, "angry": 0.2},
            "heartbroken": {"sad": 1.0, "surprised": 0.3},
            "devastated": {"sad": 1.0, "angry": 0.3},
            "crushed": {"sad": 0.95, "surprised": 0.2},
            "despairing": {"sad": 1.0, "relaxed": 0.4},
            "hopeless": {"sad": 0.9, "relaxed": 0.5},
            "melancholy": {"sad": 0.7, "relaxed": 0.4},
            "gloomy": {"sad": 0.6, "neutral": 0.3},
            "downcast": {"sad": 0.5, "neutral": 0.4},
            "dejected": {"sad": 0.7, "neutral": 0.2},
            "crestfallen": {"sad": 0.8, "surprised": 0.1},
            "disappointed": {"sad": 0.6, "angry": 0.2},
            "let_down": {"sad": 0.5, "angry": 0.3},
            "blue": {"sad": 0.6, "relaxed": 0.3},
            "down": {"sad": 0.5, "neutral": 0.3},
            "crying": {"sad": 1.0},
            "weeping": {"sad": 1.0, "surprised": 0.2},
            "sobbing": {"sad": 1.0, "angry": 0.1},
            "teary": {"sad": 0.7, "surprised": 0.1},

            # ===== ANGER SPECTRUM =====
            "furious": {"angry": 1.0, "surprised": 0.3},
            "enraged": {"angry": 1.0, "sad": 0.1},
            "livid": {"angry": 1.0},
            "seething": {"angry": 0.95, "neutral": 0.2},
            "fuming": {"angry": 0.9, "surprised": 0.2},
            "irate": {"angry": 0.85},
            "wrathful": {"angry": 1.0, "sad": 0.2},
            "hostile": {"angry": 0.8, "neutral": 0.3},
            "aggressive": {"angry": 0.9, "surprised": 0.4},
            "irritated": {"angry": 0.6, "neutral": 0.2},
            "agitated": {"angry": 0.7, "surprised": 0.3},
            "annoyed": {"angry": 0.5, "neutral": 0.3},
            "peeved": {"angry": 0.4, "neutral": 0.4},
            "vexed": {"angry": 0.6, "surprised": 0.1},
            "miffed": {"angry": 0.45, "neutral": 0.3},
            "cross": {"angry": 0.5, "sad": 0.1},
            "grumpy": {"angry": 0.4, "sad": 0.2},
            "cranky": {"angry": 0.5, "relaxed": 0.1},
            "bitter": {"angry": 0.6, "sad": 0.4},
            "resentful": {"angry": 0.7, "sad": 0.3},

            # ===== DISGUST SPECTRUM =====
            "disgusted": {"angry": 0.3, "sad": 0.6, "surprised": 0.2, "ih": 0.4},
            "revolted": {"angry": 0.2, "sad": 0.7, "surprised": 0.4, "ih": 0.5},
            "repulsed": {"angry": 0.25, "sad": 0.65, "surprised": 0.3, "ih": 0.4},
            "nauseated": {"sad": 0.7, "surprised": 0.2, "relaxed": 0.3, "ou": 0.3},
            "sickened": {"sad": 0.8, "angry": 0.1, "surprised": 0.2, "ou": 0.4},
            "appalled": {"surprised": 0.6, "angry": 0.3, "sad": 0.3, "oh": 0.3},
            "horrified": {"surprised": 0.8, "sad": 0.5, "angry": 0.1, "oh": 0.5, "aa": 0.3},
            "repelled": {"angry": 0.2, "sad": 0.5, "surprised": 0.5, "ih": 0.3},
            "aversion": {"angry": 0.3, "sad": 0.5, "neutral": 0.3, "ih": 0.2},
            "distaste": {"angry": 0.2, "sad": 0.4, "neutral": 0.5, "ih": 0.2},
            "contempt": {"angry": 0.5, "sad": 0.2, "neutral": 0.4, "ih": 0.3},
            "disdain": {"angry": 0.4, "neutral": 0.6, "sad": 0.1, "ih": 0.2},
            "scorn": {"angry": 0.6, "neutral": 0.4, "happy": 0.1, "ih": 0.4},
            "loathing": {"angry": 0.4, "sad": 0.7, "ih": 0.5},
            "abhorrence": {"angry": 0.3, "sad": 0.8, "surprised": 0.2, "ih": 0.6},

            # ===== FEAR/ANXIETY SPECTRUM =====
            "terrified": {"surprised": 1.0, "sad": 0.6},
            "petrified": {"surprised": 1.0, "sad": 0.5, "neutral": 0.3},
            "frightened": {"surprised": 0.9, "sad": 0.4},
            "scared": {"surprised": 0.8, "sad": 0.3},
            "afraid": {"surprised": 0.7, "sad": 0.4},
            "fearful": {"surprised": 0.7, "sad": 0.5},
            "panicked": {"surprised": 1.0, "angry": 0.3},
            "alarmed": {"surprised": 0.9, "angry": 0.2},
            "startled": {"surprised": 1.0},
            "shocked": {"surprised": 1.0, "neutral": 0.2},
            "stunned": {"surprised": 0.9, "neutral": 0.5},
            "anxious": {"surprised": 0.4, "sad": 0.5, "angry": 0.2},
            "nervous": {"surprised": 0.3, "sad": 0.3, "neutral": 0.2},
            "worried": {"sad": 0.5, "surprised": 0.3, "angry": 0.2},
            "uneasy": {"surprised": 0.3, "neutral": 0.4, "sad": 0.2},
            "apprehensive": {"surprised": 0.4, "sad": 0.4, "neutral": 0.2},
            "tense": {"angry": 0.3, "surprised": 0.4, "neutral": 0.3},
            "jittery": {"surprised": 0.5, "happy": 0.2, "neutral": 0.2},

            # ===== SURPRISE SPECTRUM =====
            "astonished": {"surprised": 1.0, "happy": 0.2, "oh": 0.5},
            "astounded": {"surprised": 1.0, "happy": 0.3, "oh": 0.6},
            "amazed": {"surprised": 0.9, "happy": 0.4, "aa": 0.3, "oh": 0.4},
            "awestruck": {"surprised": 0.8, "happy": 0.5, "neutral": 0.2, "oh": 0.5},
            "flabbergasted": {"surprised": 1.0, "angry": 0.2, "aa": 0.4, "oh": 0.5},
            "dumbfounded": {"surprised": 0.9, "neutral": 0.4, "oh": 0.3},
            "bewildered": {"surprised": 0.7, "sad": 0.3, "neutral": 0.2, "oh": 0.2},
            "baffled": {"surprised": 0.6, "angry": 0.3, "neutral": 0.3, "ou": 0.2},
            "perplexed": {"surprised": 0.5, "angry": 0.4, "neutral": 0.3, "ou": 0.3},
            "puzzled": {"surprised": 0.4, "angry": 0.3, "neutral": 0.4, "ou": 0.2},
            "curious": {"surprised": 0.5, "happy": 0.3, "neutral": 0.2, "ou": 0.1},
            "intrigued": {"surprised": 0.4, "happy": 0.4, "relaxed": 0.2, "ou": 0.2},
            "gasp": {"surprised": 1.0, "oh": 0.7, "aa": 0.3},

            # ===== CONFIDENCE/PRIDE SPECTRUM =====
            "confident": {"happy": 0.4, "relaxed": 0.6, "neutral": 0.3},
            "self_assured": {"happy": 0.3, "relaxed": 0.7, "neutral": 0.2},
            "proud": {"happy": 0.6, "relaxed": 0.4, "neutral": 0.3},
            "triumphant": {"happy": 0.8, "surprised": 0.3, "relaxed": 0.2},
            "victorious": {"happy": 0.9, "surprised": 0.4},
            "accomplished": {"happy": 0.7, "relaxed": 0.5},
            "smug": {"happy": 0.3, "relaxed": 0.4, "neutral": 0.4},
            # "smirk" later definition wins (see note above).
            "smirk": {"happy": 0.25, "relaxed": 0.35, "neutral": 0.5},
            "cocky": {"happy": 0.4, "relaxed": 0.3, "neutral": 0.5},
            "arrogant": {"neutral": 0.6, "happy": 0.2, "angry": 0.3},
            "haughty": {"neutral": 0.7, "angry": 0.4, "happy": 0.1},
            "superior": {"neutral": 0.6, "relaxed": 0.4, "angry": 0.2},
            "boastful": {"happy": 0.5, "relaxed": 0.3, "surprised": 0.2},
            "cheeky": {"happy": 0.6, "relaxed": 0.2, "surprised": 0.2},
            "sassy": {"happy": 0.4, "angry": 0.3, "relaxed": 0.3},

            # ===== EMBARRASSMENT/SHAME SPECTRUM =====
            "embarrassed": {"sad": 0.4, "happy": 0.3, "surprised": 0.2},
            "ashamed": {"sad": 0.7, "angry": 0.3, "neutral": 0.2},
            "humiliated": {"sad": 0.9, "angry": 0.4},
            "mortified": {"sad": 0.85, "surprised": 0.5},
            "sheepish": {"sad": 0.3, "happy": 0.2, "neutral": 0.5},
            "bashful": {"sad": 0.2, "happy": 0.4, "neutral": 0.4},
            "shy": {"sad": 0.3, "neutral": 0.6, "surprised": 0.1},
            "timid": {"sad": 0.4, "neutral": 0.5, "surprised": 0.2},
            "flustered": {"surprised": 0.5, "sad": 0.3, "angry": 0.2},
            "self_conscious": {"sad": 0.4, "neutral": 0.5, "surprised": 0.1},
            "guilt": {"sad": 0.6, "angry": 0.4},
            "remorseful": {"sad": 0.8, "angry": 0.2},

            # ===== LOVE/AFFECTION SPECTRUM =====
            "loving": {"happy": 0.7, "relaxed": 0.6},
            "adoring": {"happy": 0.8, "relaxed": 0.5, "surprised": 0.2},
            "affectionate": {"happy": 0.6, "relaxed": 0.5},
            "tender": {"happy": 0.5, "relaxed": 0.7, "sad": 0.1},
            "caring": {"happy": 0.5, "relaxed": 0.6},
            "warm": {"happy": 0.6, "relaxed": 0.7},
            "fond": {"happy": 0.5, "relaxed": 0.5},
            "devoted": {"happy": 0.6, "relaxed": 0.6, "sad": 0.2},
            "infatuated": {"happy": 0.8, "surprised": 0.4, "relaxed": 0.3},
            "romantic": {"happy": 0.7, "relaxed": 0.5, "surprised": 0.2},
            "passionate": {"happy": 0.6, "surprised": 0.5, "angry": 0.3},
            "lustful": {"happy": 0.5, "surprised": 0.4, "relaxed": 0.4},

            # ===== PLAYFULNESS/MISCHIEF SPECTRUM =====
            "playful": {"happy": 0.7, "relaxed": 0.3, "surprised": 0.2},
            "mischievous": {"happy": 0.6, "surprised": 0.3, "neutral": 0.2},
            "impish": {"happy": 0.65, "surprised": 0.4, "relaxed": 0.1},
            "teasing": {"happy": 0.5, "relaxed": 0.3, "neutral": 0.3},
            "joking": {"happy": 0.7, "relaxed": 0.4},
            "silly": {"happy": 0.8, "surprised": 0.3},
            "goofy": {"happy": 0.85, "surprised": 0.4},
            "whimsical": {"happy": 0.6, "surprised": 0.3, "relaxed": 0.4},
            "wink": {"happy": 0.4, "blinkLeft": 1.0},
            "winkleft": {"happy": 0.3, "blinkLeft": 1.0},
            "winkright": {"happy": 0.3, "blinkRight": 1.0},
            "flirty": {"happy": 0.6, "relaxed": 0.4, "surprised": 0.2},
            "coy": {"happy": 0.4, "sad": 0.2, "neutral": 0.5},
            "sly": {"neutral": 0.5, "happy": 0.3, "relaxed": 0.3},
            "cunning": {"neutral": 0.6, "angry": 0.2, "happy": 0.2},
            "devious": {"neutral": 0.5, "angry": 0.3, "happy": 0.3},
            "scheming": {"neutral": 0.7, "angry": 0.3, "surprised": 0.2},

            # ===== TIREDNESS/RELAXATION SPECTRUM =====
            "exhausted": {"relaxed": 0.9, "sad": 0.5},
            "drained": {"relaxed": 0.8, "sad": 0.6},
            "fatigued": {"relaxed": 0.7, "sad": 0.4, "neutral": 0.3},
            "weary": {"relaxed": 0.6, "sad": 0.5, "neutral": 0.2},
            "tired": {"relaxed": 0.6, "sad": 0.3},
            "sleepy": {"relaxed": 0.9, "neutral": 0.4},
            "drowsy": {"relaxed": 0.85, "neutral": 0.5},
            "lethargic": {"relaxed": 0.7, "neutral": 0.6},
            "sluggish": {"relaxed": 0.6, "neutral": 0.5, "sad": 0.2},
            "lazy": {"relaxed": 0.8, "neutral": 0.4, "happy": 0.2},
            "chill": {"relaxed": 0.9, "happy": 0.3},
            "calm": {"relaxed": 1.0, "neutral": 0.3},

            # ===== BOREDOM/DISINTEREST SPECTRUM =====
            "bored": {"neutral": 0.8, "relaxed": 0.4, "sad": 0.2},
            "uninterested": {"neutral": 0.9, "relaxed": 0.3},
            "indifferent": {"neutral": 1.0, "relaxed": 0.2},
            "apathetic": {"neutral": 0.95, "sad": 0.3},
            "listless": {"neutral": 0.7, "sad": 0.4, "relaxed": 0.3},
            "unamused": {"neutral": 0.6, "angry": 0.4},
            "unimpressed": {"neutral": 0.7, "angry": 0.3},
            "underwhelmed": {"neutral": 0.6, "sad": 0.2, "relaxed": 0.3},
            "dismissive": {"neutral": 0.5, "angry": 0.4, "relaxed": 0.2},
            "eye_roll": {"neutral": 0.4, "angry": 0.5, "surprised": 0.2},

            # ===== CONFUSION/CONTEMPLATION SPECTRUM =====
            "confused": {"surprised": 0.5, "angry": 0.3, "neutral": 0.3},
            "thinking": {"neutral": 0.6, "angry": 0.2, "relaxed": 0.3},
            "pondering": {"neutral": 0.7, "relaxed": 0.4, "surprised": 0.1},
            "contemplating": {"neutral": 0.8, "relaxed": 0.5},
            "pensive": {"sad": 0.3, "neutral": 0.6, "relaxed": 0.3},
            "reflective": {"neutral": 0.7, "sad": 0.2, "relaxed": 0.4},
            "deep_in_thought": {"neutral": 0.9, "relaxed": 0.5},
            "concentrating": {"angry": 0.4, "neutral": 0.6},
            "focused": {"angry": 0.3, "neutral": 0.7},
            "absorbed": {"neutral": 0.8, "relaxed": 0.3},
            "engrossed": {"neutral": 0.7, "surprised": 0.2, "relaxed": 0.2},
            "lost_in_thought": {"neutral": 0.8, "sad": 0.3, "relaxed": 0.4},

            # ===== PHYSICAL DISCOMFORT SPECTRUM =====
            "sick": {"sad": 0.7, "relaxed": 0.5, "neutral": 0.2},
            "ill": {"sad": 0.65, "relaxed": 0.6},
            "unwell": {"sad": 0.6, "relaxed": 0.5, "neutral": 0.3},
            "nauseous": {"sad": 0.7, "surprised": 0.3, "angry": 0.2},
            "queasy": {"sad": 0.6, "surprised": 0.4, "relaxed": 0.3},
            "pain": {"angry": 0.5, "sad": 0.6, "surprised": 0.3},
            "aching": {"sad": 0.5, "angry": 0.3, "relaxed": 0.4},
            "suffering": {"sad": 0.8, "angry": 0.4},
            "agonized": {"sad": 0.9, "angry": 0.6, "surprised": 0.3},
            "grimace": {"angry": 0.6, "sad": 0.3, "surprised": 0.4},

            # ===== AWKWARDNESS/DISCOMFORT SPECTRUM =====
            "awkward": {"sad": 0.4, "surprised": 0.3, "neutral": 0.4},
            "uncomfortable": {"sad": 0.3, "angry": 0.4, "neutral": 0.3},
            "restless": {"surprised": 0.4, "angry": 0.3, "neutral": 0.3},
            "fidgety": {"surprised": 0.5, "neutral": 0.3, "happy": 0.2},
            "antsy": {"surprised": 0.5, "angry": 0.3, "happy": 0.2},
            "edgy": {"angry": 0.5, "surprised": 0.4, "neutral": 0.2},
            "on_edge": {"angry": 0.4, "surprised": 0.5, "sad": 0.2},
            "stressed": {"angry": 0.6, "sad": 0.4, "surprised": 0.3},
            "overwhelmed": {"surprised": 0.6, "sad": 0.5, "angry": 0.3},

            # ===== MIXED/COMPLEX EMOTIONS =====
            "bittersweet": {"happy": 0.5, "sad": 0.5},
            "conflicted": {"surprised": 0.4, "sad": 0.4, "angry": 0.3},
            "ambivalent": {"neutral": 0.7, "surprised": 0.3},
            "nostalgic": {"sad": 0.4, "happy": 0.4, "relaxed": 0.3},
            "wistful": {"sad": 0.5, "happy": 0.3, "relaxed": 0.4},
            "yearning": {"sad": 0.6, "surprised": 0.3, "happy": 0.2},
            "longing": {"sad": 0.7, "surprised": 0.2, "relaxed": 0.3},
            "homesick": {"sad": 0.7, "relaxed": 0.4},
            "touched": {"sad": 0.4, "happy": 0.5, "surprised": 0.2},
            "moved": {"sad": 0.3, "happy": 0.6, "surprised": 0.3},
            "emotional": {"sad": 0.5, "happy": 0.4, "surprised": 0.3},
            "sentimental": {"sad": 0.4, "happy": 0.4, "relaxed": 0.4},
            "melancholic": {"sad": 0.7, "relaxed": 0.6},
            "melting": {"relaxed": 0.9, "sad": 0.4, "happy": 0.2},
            "swooning": {"happy": 0.6, "relaxed": 0.7, "surprised": 0.3},

            # ===== NEUTRAL/EXPRESSIONLESS SPECTRUM =====
            "blank": {"neutral": 1.0},
            "empty": {"neutral": 0.95, "sad": 0.2},
            "numb": {"neutral": 0.9, "sad": 0.3},
            "detached": {"neutral": 0.85, "relaxed": 0.4},
            "distant": {"neutral": 0.8, "sad": 0.3, "relaxed": 0.2},
            "spaced_out": {"neutral": 0.9, "relaxed": 0.5},
            "zoned_out": {"neutral": 0.85, "relaxed": 0.6},
            "expressionless": {"neutral": 1.0},

            # ===== INTENSITY MODIFIERS =====
            "slight": {"neutral": 0.8},
            "moderate": {"neutral": 0.5},
            "intense": {"angry": 0.3, "surprised": 0.3},
            "extreme": {"angry": 0.5, "surprised": 0.5},

            # ===== ALIASES & SHORTCUTS =====
            "deadpan": {"neutral": 1.0},
            "serious": {"angry": 0.4, "neutral": 0.6},
            "determined": {"angry": 0.5, "neutral": 0.5, "surprised": 0.2},
            "resolved": {"angry": 0.3, "neutral": 0.7},
            "stubborn": {"angry": 0.6, "neutral": 0.5},
            "defiant": {"angry": 0.7, "surprised": 0.3},
            "rebellious": {"angry": 0.6, "happy": 0.3, "surprised": 0.2},
        }

    # ------------------------------------------------------------------ #
    # Catalog
    # ------------------------------------------------------------------ #
    def get_available_animations(self):
        return list(self.actions.keys())

    def get_animation_catalog(self):
        return [
            {"name": "HappyIdle", "path": "/animations/HappyIdle.vrma", "loop": True},
            {"name": "wave", "path": "/animations/Waving.vrma", "loop": False},
            {"name": "Macarena_dance", "path": "/animations/MacarenaDance.vrma", "loop": False},
            {"name": "dance", "path": "/animations/HipHopDance.vrma", "loop": False},
            {"name": "clap", "path": "/animations/Clapping.vrma", "loop": False},
            {"name": "thumbs_up", "path": "/animations/ThumbsUp.vrma", "loop": False},
            {"name": "shrug", "path": "/animations/Shrugging.vrma", "loop": False},
            {"name": "pointing", "path": "/animations/Pointing.vrma", "loop": False},
            {"name": "laugh", "path": "/animations/Laughing.vrma", "loop": False},
            {"name": "salute", "path": "/animations/Salute.vrma", "loop": False},
            {"name": "angry", "path": "/animations/Angry.vrma", "loop": False},
            {"name": "backflip", "path": "/animations/Backflip.vrma", "loop": False},
            {"name": "acknowledging", "path": "/animations/Acknowledging.vrma", "loop": False},
            {"name": "blow_kiss", "path": "/animations/BlowKiss.vrma", "loop": False},
            {"name": "bored", "path": "/animations/Bored.vrma", "loop": False},
            {"name": "looking_around", "path": "/animations/LookingAround.vrma", "loop": False},
            {"name": "cutthroat", "path": "/animations/CutthroatGesture.vrma", "loop": False},
            {"name": "gangnam_style", "path": "/animations/GangnamStyle.vrma", "loop": False},
            {"name": "sleeping", "path": "/animations/Sleeping.vrma", "loop": False},
            {"name": "looking_at_finger", "path": "/animations/LookingAtFingerFromBoredom.vrma", "loop": False},
            {"name": "taunt", "path": "/animations/Taunt Gesture.vrma", "loop": False},
        ]

    def get_animation_repo_base(self):
        return (
            "https://raw.githubusercontent.com/AbdulkhaevHasanboy/VRM_1/"
            "aede9fafde98b47ee6f43702889a2a62c6e3e93f/public/animations"
        )

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #
    async def load_animation_file(self, file):
        name = file.get("name")
        if not name or self.actions.get(name):
            return self.actions.get(name)

        remote_url = f"{self.get_animation_repo_base()}/{file['path'].split('/')[-1]}"
        await self.load_clip_with_fallback(name, file["path"], remote_url, file["loop"])
        return self.actions.get(name)

    async def load_animation_batch(self, files, options=None):
        options = options or {}
        on_progress = options.get("onProgress")
        continue_on_error = options.get("continueOnError", False)
        total = len(files)

        for index, file in enumerate(files):
            try:
                await self.load_animation_file(file)
            except Exception as error:  # noqa: BLE001
                if not continue_on_error:
                    raise
                console.warn(f"AnimationManager: Skipped animation '{file.get('name')}'", str(error))

            if on_progress:
                on_progress({"current": index + 1, "total": total, "name": file.get("name")})

    def start_background_animation_load(self, options=None):
        options = options or {}
        if self.background_load_task:
            return self.background_load_task

        on_progress = options.get("onProgress")
        remaining_files = [f for f in self.get_animation_catalog() if not self.actions.get(f["name"])]
        if not remaining_files:
            return None

        async def _run():
            try:
                await self.load_animation_batch(
                    remaining_files,
                    {"onProgress": on_progress, "continueOnError": True},
                )
            finally:
                self.background_load_task = None

        self.background_load_task = asyncio.ensure_future(_run())
        return self.background_load_task

    async def initialize(self, options=None):
        options = options or {}
        on_progress = options.get("onProgress")
        initial_animations = options.get("initialAnimations")
        load_remaining_in_background = options.get("loadRemainingInBackground", False)
        on_background_progress = options.get("onBackgroundProgress")

        console.log("AnimationManager: Loading clips...")
        self.mixer.addEventListener("finished", proxy(self.on_animation_finished))

        files = self.get_animation_catalog()
        initial_set = None
        if isinstance(initial_animations, (list, tuple)) and len(initial_animations) > 0:
            initial_set = set([self.main_idle, *initial_animations])
        initial_files = [f for f in files if f["name"] in initial_set] if initial_set else files

        await self.load_animation_batch(initial_files, {"onProgress": on_progress})

        console.log("AnimationManager Ready")
        if self.actions.get(self.main_idle):
            self.play(self.main_idle)

        if load_remaining_in_background:
            self.start_background_animation_load({"onProgress": on_background_progress})

    async def load_clip_with_fallback(self, name, local_path, remote_url, is_loop):
        try:
            await self.load_clip(name, local_path, is_loop)
        except Exception:  # noqa: BLE001
            await self.load_clip(name, remote_url, is_loop)

    async def load_clip(self, name, url, is_loop):
        THREE = self.THREE
        try:
            # NOTE: JS went through cacheManager (IndexedDB) first; there is no
            # cache_manager in the Python port, so fetch the bytes directly.
            response = await window.fetch(url)
            if not response.ok:
                raise RuntimeError(f"Failed to fetch {url}")
            array_buffer = await response.arrayBuffer()

            future = asyncio.get_event_loop().create_future()

            def on_load(gltf):
                try:
                    clip = None
                    vrm_anims = getattr(gltf.userData, "vrmAnimations", None)
                    if vrm_anims is not None and len(vrm_anims) > 0:
                        clip = window.createVRMAnimationClip(vrm_anims[0], self.vrm)
                    elif gltf.animations is not None and len(gltf.animations) > 0:
                        clip = window.createVRMAnimationClip(gltf.animations[0], self.vrm)

                    if clip:
                        clip.name = name
                        action = self.mixer.clipAction(clip)
                        action.loop = THREE.LoopRepeat if is_loop else THREE.LoopOnce
                        action.clampWhenFinished = True
                        self.actions[name] = action
                        if not future.done():
                            future.set_result(action)
                    else:
                        console.warn(f"Empty animation: {url}")
                        if not future.done():
                            future.set_result(None)
                except Exception as err:  # noqa: BLE001
                    if not future.done():
                        future.set_exception(err)

            def on_error(err):
                console.warn(f"Parse failed: {url}", str(err))
                if not future.done():
                    future.set_exception(RuntimeError(str(err)))

            self.loader.parse(array_buffer, url, proxy(on_load), proxy(on_error))
            return await future
        except Exception as err:  # noqa: BLE001
            console.warn(f"Load failed: {url}", str(err))
            raise

    # ------------------------------------------------------------------ #
    # Expression resolution / normalization
    # ------------------------------------------------------------------ #
    def _has_expression_track(self, name):
        em = getattr(self.vrm, "expressionManager", None)
        if not name or not em:
            return False
        if name in self.supported_expression_track_cache:
            return self.supported_expression_track_cache[name]
        exists = bool(em.getExpressionTrackName(name))
        self.supported_expression_track_cache[name] = exists
        return exists

    def _normalize_expression_weights(self, weights=None):
        weights = weights or {}
        normalized = {}

        for key, value in weights.items():
            numeric_value = _num(value, default=float("nan"))
            if numeric_value != numeric_value or numeric_value <= 0:
                continue
            if key not in self.core_mood_keys and not self._has_expression_track(key):
                continue
            normalized[key] = _clamp(numeric_value, 0, 1)

        if len(normalized) == 0:
            normalized["neutral"] = 1
            return normalized

        core_sum = sum(normalized.get(key, 0) for key in self.core_mood_keys)
        if core_sum > 1.25:
            scale = 1.25 / core_sum
            for key in self.core_mood_keys:
                if not normalized.get(key):
                    continue
                normalized[key] = _clamp(normalized[key] * scale, 0, 1)

        has_core_mood = any(normalized.get(key, 0) > 0 for key in self.core_mood_keys)
        if not has_core_mood:
            normalized["neutral"] = max(normalized.get("neutral", 0), 0.15)

        return normalized

    def _resolve_expression_target(self, name):
        if isinstance(name, str) and len(name.strip()) > 0:
            raw_name = name.strip().lower()
        else:
            raw_name = "neutral"

        resolved_name = raw_name
        resolved_weights = None

        if self._has_expression_track(raw_name):
            resolved_weights = {raw_name: 1}
        else:
            mapped = self.expression_map.get(raw_name)
            if isinstance(mapped, str):
                resolved_name = mapped
                if self._has_expression_track(mapped) or mapped in self.core_mood_keys:
                    resolved_weights = {mapped: 1}
            elif isinstance(mapped, dict):
                resolved_weights = dict(mapped)

        if not resolved_weights:
            resolved_name = "neutral"
            resolved_weights = {"neutral": 1}

        return {
            "resolvedName": resolved_name,
            "weights": self._normalize_expression_weights(resolved_weights),
        }

    def _build_expression_style(self, weights=None):
        weights = weights or {}
        mood = {}
        for key in self.core_mood_keys:
            mood[key] = _clamp(_num(weights.get(key, 0)), 0, 1)

        smile = _clamp(
            mood["happy"] * 0.65 + mood["relaxed"] * 0.35 - mood["sad"] * 0.3 - mood["angry"] * 0.35,
            0, 1,
        )
        frown = _clamp(
            mood["sad"] * 0.75 + mood["angry"] * 0.55 - mood["happy"] * 0.25,
            0, 1,
        )
        awe = _clamp(
            mood["surprised"] * 0.9 + mood["happy"] * 0.15 + mood["sad"] * 0.2,
            0, 1,
        )
        tension = _clamp(mood["angry"] * 0.75 + mood["surprised"] * 0.35, 0, 1)

        explicit_visemes = {
            "aa": _num(weights.get("aa", 0)),
            "ee": _num(weights.get("ee", 0)),
            "ih": _num(weights.get("ih", 0)),
            "oh": _num(weights.get("oh", 0)),
            "ou": _num(weights.get("ou", 0)),
        }

        mouth_bias = {
            "aa": max(explicit_visemes["aa"], _clamp(awe * 0.05 + tension * 0.02, 0, 0.15)),
            "ee": max(explicit_visemes["ee"], _clamp(smile * 0.1, 0, 0.15)),
            "ih": max(explicit_visemes["ih"], _clamp(smile * 0.05 + frown * 0.05 + tension * 0.03, 0, 0.15)),
            "oh": max(explicit_visemes["oh"], _clamp(awe * 0.1 + mood["sad"] * 0.05, 0, 0.15)),
            "ou": max(explicit_visemes["ou"], _clamp(mood["sad"] * 0.05 + mood["relaxed"] * 0.05 + awe * 0.05, 0, 0.15)),
        }

        blink_min_interval = _clamp(
            2.8 - mood["angry"] * 0.9 - mood["surprised"] * 0.8 + mood["relaxed"] * 1.1 + mood["sad"] * 0.5,
            1.2, 5.4,
        )
        blink_range = _clamp(
            1.6 + mood["relaxed"] * 1.4 + mood["sad"] * 0.6 - mood["angry"] * 0.3,
            1.2, 3.8,
        )

        return {
            "transitionSpeed": _clamp(
                4.6 + mood["angry"] * 2.2 + mood["surprised"] * 1.8 + mood["happy"] * 0.8 - mood["sad"] * 0.2,
                4.2, 8.5,
            ),
            "microAmplitude": _clamp(
                0.014 + mood["angry"] * 0.03 + mood["surprised"] * 0.026 + mood["happy"] * 0.015 + mood["sad"] * 0.02,
                0.01, 0.08,
            ),
            "microFrequency": _clamp(
                1.6 + mood["angry"] * 1.2 + mood["surprised"] * 1.0 + mood["relaxed"] * 0.35,
                1.2, 3.8,
            ),
            "squint": _clamp(
                mood["angry"] * 0.18 + mood["happy"] * 0.08 + mood["sad"] * 0.09 - mood["surprised"] * 0.15,
                0, 0.3,
            ),
            "blinkMinInterval": blink_min_interval,
            "blinkMaxInterval": blink_min_interval + blink_range,
            "blinkDuration": _clamp(
                0.11 + mood["sad"] * 0.03 + mood["relaxed"] * 0.02 - mood["surprised"] * 0.02,
                0.08, 0.18,
            ),
            "mouthBias": mouth_bias,
            "mouthInfluenceWhileSpeaking": 0.18,
        }

    def _get_next_blink_time(self):
        style = self.expression_style or {}
        mn = style.get("blinkMinInterval", 2)
        mx = style.get("blinkMaxInterval", 5)
        safe_max = max(mn + 0.05, mx)
        return mn + random.random() * (safe_max - mn)

    def _apply_expression_target(self, name):
        resolved = self._resolve_expression_target(name)
        self.current_expression = resolved["resolvedName"]
        self.target_expression = resolved["resolvedName"]
        self.target_expression_weights = resolved["weights"]
        self.expression_style = self._build_expression_style(self.target_expression_weights)
        self.blink_duration = self.expression_style["blinkDuration"]
        self.next_blink_time = self._get_next_blink_time()
        return resolved

    def set_expression(self, name, duration=3.0):
        resolved = self._apply_expression_target(name)
        console.log(
            f"Face: {name} => {resolved['resolvedName']} ({duration}s)",
            to_js(resolved["weights"]),
        )
        self.target_expression = resolved["resolvedName"]

        if self.expression_timer is not None:
            window.clearTimeout(self.expression_timer)
            self.expression_timer = None
        if duration and duration > 0:
            self.expression_timer = window.setTimeout(
                proxy(lambda *_: self._apply_expression_target("neutral")),
                duration * 1000,
            )

    # ------------------------------------------------------------------ #
    # Speaking / lip-sync state
    # ------------------------------------------------------------------ #
    def set_speaking_state(self, is_speaking):
        self.is_speaking = is_speaking
        if not is_speaking:
            self.speech_intensity = 0
            self.speech_cadence = 0
            self.speech_cadence_phase = 0
            self.speech_text_cursor = ""
            self.speech_pending_word = ""
            self.speech_beat_queue = 0
            self.speech_beat_progress = 0
            self.speech_beat_open = 0
            for key in self.speech_target:
                self.speech_target[key] = 0
        # We rely on is_speaking to unlock mouth blendshapes for the AudioAnalyzer.

    def set_speech_intensity(self, value=0):
        # Object form (rich viseme payload).
        if isinstance(value, dict):
            intensity = _clamp(_num(value.get("intensity"), 0), 0, 1)
            self.speech_intensity = intensity
            self.speech_target["intensity"] = intensity
            self.speech_target["activity"] = _clamp(_num(value.get("activity"), intensity), 0, 1)
            self.speech_target["pulse"] = _clamp(
                _num(value.get("pulse"), self.speech_target["activity"]), 0, 1
            )
            self.speech_target["openness"] = _clamp(_num(value.get("openness"), intensity), 0, 1)
            self.speech_target["wide"] = _clamp(_num(value.get("wide"), 0), 0, 1)
            self.speech_target["round"] = _clamp(_num(value.get("round"), 0), 0, 1)
            self.speech_target["narrow"] = _clamp(_num(value.get("narrow"), 0), 0, 1)

            visemes = value.get("visemes") if isinstance(value.get("visemes"), dict) else {}
            for key in self.mouth_keys:
                self.speech_target[key] = _clamp(_num(visemes.get(key), 0), 0, 1)
            return

        # Scalar form.
        normalized = _clamp(_num(value, 0), 0, 1)
        self.speech_intensity = normalized
        self.speech_target["intensity"] = normalized
        self.speech_target["activity"] = normalized
        self.speech_target["pulse"] = normalized * 0.45
        self.speech_target["openness"] = normalized
        self.speech_target["wide"] = normalized * 0.18
        self.speech_target["round"] = normalized * 0.28
        self.speech_target["narrow"] = normalized * 0.12
        self.speech_target["aa"] = normalized * 0.95
        self.speech_target["ee"] = normalized * 0.16
        self.speech_target["ih"] = normalized * 0.2
        self.speech_target["oh"] = normalized * 0.42
        self.speech_target["ou"] = normalized * 0.14

    @staticmethod
    def _estimate_syllables(word=""):
        cleaned = "".join(c for c in str(word or "").lower() if "a" <= c <= "z")
        if not cleaned:
            return 0
        if len(cleaned) <= 3:
            return 1

        import re

        sanitized = re.sub(r"(?:[^laeiouy]es|ed|[^laeiouy]e)$", "", cleaned)
        sanitized = re.sub(r"^y", "", sanitized)
        groups = re.findall(r"[aeiouy]{1,2}", sanitized)
        return max(len(groups), 1)

    def _estimate_speech_beats(self, text=""):
        import re

        words = re.findall(r"[a-z']+", str(text or "").lower())
        if not words:
            return 0
        return sum(self._estimate_syllables(word) for word in words)

    def set_speech_transcript(self, text="", is_final=False):
        normalized = text if isinstance(text, str) else ""
        if not normalized:
            if is_final:
                self.speech_text_cursor = ""
                self.speech_pending_word = ""
            return

        import re

        appended = normalized
        if self.speech_text_cursor and normalized.startswith(self.speech_text_cursor):
            appended = normalized[len(self.speech_text_cursor):]
        elif self.speech_text_cursor:
            appended = normalized.replace(self.speech_text_cursor, "", 1)

        combined = f"{self.speech_pending_word}{appended}"
        complete_chunk = combined
        pending_word = ""

        if not is_final:
            trailing = re.search(r"[a-z']+$", combined, re.IGNORECASE)
            if trailing:
                pending_word = trailing.group(0)
                complete_chunk = combined[: -len(pending_word)]

        beat_count = self._estimate_speech_beats(complete_chunk)
        if is_final and pending_word:
            beat_count += self._estimate_speech_beats(pending_word)
            pending_word = ""

        if beat_count > 0:
            self.speech_beat_queue = min(self.speech_beat_queue + beat_count, 24)

        self.speech_pending_word = pending_word
        self.speech_text_cursor = normalized
        if is_final:
            self.speech_text_cursor = ""
            self.speech_pending_word = ""

    def _update_speech_beat(self, delta, activity, pulse):
        if not self.is_speaking:
            self.speech_beat_queue = 0
            self.speech_beat_progress = 0
            self.speech_beat_open = _lerp(self.speech_beat_open, 0, _clamp(delta * 10, 0, 1))
            return self.speech_beat_open

        if self.speech_beat_queue > 0:
            beat_rate = _clamp(
                4.2 + activity * 2.2 + pulse * 1.6 + min(self.speech_beat_queue, 6) * 0.35,
                4.2, 8.4,
            )
            self.speech_beat_progress += delta * beat_rate

            completed_beats = math.floor(self.speech_beat_progress)
            if completed_beats > 0:
                self.speech_beat_queue = max(0, self.speech_beat_queue - completed_beats)
                self.speech_beat_progress -= completed_beats

            beat_shape = math.sin(self.speech_beat_progress * math.pi)
            beat_accent = _clamp(0.58 + pulse * 0.24 + activity * 0.1, 0.5, 0.94)
            self.speech_beat_open = _lerp(
                self.speech_beat_open, beat_shape * beat_accent, _clamp(delta * 18, 0, 1)
            )
            return self.speech_beat_open

        fallback_pulse = _clamp(pulse * 0.45 + activity * 0.14, 0, 0.36)
        self.speech_beat_open = _lerp(self.speech_beat_open, fallback_pulse, _clamp(delta * 8, 0, 1))
        return self.speech_beat_open

    def _sync_speech_state(self, delta):
        attack = _clamp(delta * 24, 0, 1)
        release = _clamp(delta * 12, 0, 1)
        for key in self.speech_state:
            current = self.speech_state[key] or 0
            target = (self.speech_target.get(key, 0) or 0) if self.is_speaking else 0
            factor = attack if target > current else release
            self.speech_state[key] = _lerp(current, target, factor)

    # ------------------------------------------------------------------ #
    # Per-frame update
    # ------------------------------------------------------------------ #
    def update(self, delta):
        vrm = self.vrm
        humanoid = getattr(vrm, "humanoid", None) if vrm else None

        if humanoid:
            # Reset procedurally-driven bones to avoid accumulated rotation drift.
            for bone_name in ("spine", "head", "neck", "leftShoulder", "rightShoulder"):
                bone = humanoid.getNormalizedBoneNode(bone_name)
                if bone:
                    bone.rotation.set(0, 0, 0)

        if self.mixer:
            self.mixer.update(delta)

        if not vrm:
            return

        if humanoid:
            self._breath_timer += delta

            spine = humanoid.getNormalizedBoneNode("spine")
            if spine:
                spine.rotation.x += math.sin(self._breath_timer * 1.8) * 0.007

            head = humanoid.getNormalizedBoneNode("head")
            if head:
                head.rotation.x += math.sin(self._breath_timer * 0.85) * 0.012
                head.rotation.y += math.cos(self._breath_timer * 0.62) * 0.008
                head.rotation.z += math.sin(self._breath_timer * 0.44) * 0.006

            em = getattr(vrm, "expressionManager", None)
            if em:
                happy = em.getValue("happy") or 0
                sad = em.getValue("sad") or 0
                angry = em.getValue("angry") or 0
                surprised = em.getValue("surprised") or 0

                left_shoulder = humanoid.getNormalizedBoneNode("leftShoulder")
                right_shoulder = humanoid.getNormalizedBoneNode("rightShoulder")
                if left_shoulder and right_shoulder:
                    shrug_z = (angry * 0.08) + (surprised * 0.1) - (sad * 0.07)
                    left_shoulder.rotation.z += shrug_z
                    right_shoulder.rotation.z -= shrug_z

                    shrug_y = angry * 0.04
                    left_shoulder.rotation.y += shrug_y
                    right_shoulder.rotation.y -= shrug_y

                neck = humanoid.getNormalizedBoneNode("neck")
                if neck:
                    pitch = (sad * 0.08) + (angry * 0.06) - (surprised * 0.08)
                    neck.rotation.x += pitch

        if getattr(vrm, "expressionManager", None):
            self.update_blink(delta)
            self.update_expressions(delta)

        # LookAt — eyes track camera with micro-saccades.
        look_at = getattr(vrm, "lookAt", None)
        if look_at and self.camera:
            if not self._look_at_target:
                self._look_at_target = self.THREE.Object3D.new()
                self.camera.add(self._look_at_target)
            if self._saccade_offset is None:
                self._saccade_offset = self.THREE.Vector3.new()

            self._saccade_timer -= delta
            if self._saccade_timer <= 0:
                self._saccade_timer = 1.5 + random.random() * 2.0
                if random.random() < 0.75:
                    self._saccade_offset.set(
                        (random.random() - 0.5) * 0.04,
                        (random.random() - 0.5) * 0.04,
                        (random.random() - 0.5) * 0.04,
                    )
                else:
                    self._saccade_offset.set(0, 0, 0)

            self._look_at_target.position.copy(self._saccade_offset)
            self._look_at_target.updateMatrixWorld(True)
            look_at.target = self._look_at_target
            look_at.update(delta)

    def update_blink(self, delta):
        self.blink_timer += delta
        if self.blink_timer >= self.next_blink_time:
            self.is_blinking = True
            self.blink_timer = 0
            self.next_blink_time = self._get_next_blink_time()

        if self.is_blinking:
            self.blink_progress += delta
            if self.blink_progress >= self.blink_duration:
                self.is_blinking = False
                self.blink_progress = 0

                # Double-blink doublet: ~18% chance to immediately re-trigger.
                if random.random() < 0.18 and not self._is_double_blinking:
                    self._is_double_blinking = True
                    self.blink_timer = self.next_blink_time - (0.08 + random.random() * 0.14)
                else:
                    self._is_double_blinking = False

    def update_expressions(self, delta):
        manager = self.vrm.expressionManager
        speed = self.expression_style["transitionSpeed"] * delta

        # 1. Blink
        blink_value = 0
        if self.is_blinking:
            t = math.pi * (self.blink_progress / self.blink_duration)
            blink_value = math.sin(t)

        # 2. Micro-Expressions
        self.micro_timer += delta
        base_freq = self.expression_style["microFrequency"]
        self.micro_intensity = (
            math.sin(self.micro_timer * base_freq)
            + 0.45 * math.sin(self.micro_timer * base_freq * 2.3)
            + 0.25 * math.cos(self.micro_timer * base_freq * 4.7)
        ) * (self.expression_style["microAmplitude"] / 1.7)

        # 3. Moods
        target_weights = self.target_expression_weights or {"neutral": 1}
        keys_to_update = set(self.core_mood_keys)
        keys_to_update.update(self.active_expression_keys)
        keys_to_update.update(target_weights.keys())

        next_active_keys = set(self.core_mood_keys)

        for key in keys_to_update:
            if key not in self.core_mood_keys and not self._has_expression_track(key):
                continue
            current_val = manager.getValue(key) or 0
            base_target = target_weights.get(key, 0.0)

            if base_target > 0.05:
                base_target += self.micro_intensity * min(1, base_target + 0.2)
            base_target = _clamp(base_target, 0, 1)

            # Duck core emotions slightly when speaking to avoid mouth clipping.
            if self.is_speaking and key in self.core_mood_keys:
                duck_factor = 1.0 - (self.speech_intensity or 0) * 0.3
                base_target *= duck_factor

            new_val = _lerp(current_val, base_target, speed)
            manager.setValue(key, 0 if new_val < 0.01 else new_val)
            if new_val >= 0.01 or base_target >= 0.01:
                next_active_keys.add(key)

        self.active_expression_keys = next_active_keys

        squint_target = _clamp(
            self.expression_style["squint"] + max(0, self.micro_intensity * 0.2),
            0, 0.35,
        )

        current_target_weights = self.target_expression_weights or {}
        explicit_blink_left = current_target_weights.get("blinkLeft", 0)
        explicit_blink_right = current_target_weights.get("blinkRight", 0)
        explicit_blink = current_target_weights.get("blink", 0)

        left_val = max(blink_value, squint_target, explicit_blink_left, explicit_blink)
        right_val = max(blink_value, squint_target, explicit_blink_right, explicit_blink)

        if self._has_expression_track("blinkLeft") and self._has_expression_track("blinkRight"):
            manager.setValue("blinkLeft", left_val)
            manager.setValue("blinkRight", right_val)
            manager.setValue("blink", 0)
        else:
            manager.setValue("blink", max(left_val, right_val))

        # 4. Mouth Movement Control
        speaking_influence = (
            self.expression_style["mouthInfluenceWhileSpeaking"] if self.is_speaking else 1
        )
        for key in self.mouth_keys:
            if not self._has_expression_track(key):
                continue
            current_val = manager.getValue(key) or 0
            emotion_target = _clamp(
                (self.expression_style["mouthBias"].get(key, 0) or 0) * speaking_influence, 0, 1
            ) + max(0, self.micro_intensity * 0.35)
            target_val = max(current_val, emotion_target) if self.is_speaking else emotion_target
            new_val = _lerp(current_val, target_val, speed * 0.9)
            manager.setValue(key, 0 if new_val < 0.01 else new_val)

        manager.update()

    # ------------------------------------------------------------------ #
    # Playback control
    # ------------------------------------------------------------------ #
    def trigger_named_animation(self, name):
        if not isinstance(name, str) or not name.strip():
            return
        requested_name = name.strip()

        # 1. Exact match.
        if self.actions.get(requested_name):
            self.play(requested_name)
            return

        # 2. Case-insensitive match.
        lower_name = requested_name.lower()
        found_key = next((k for k in self.actions if k.lower() == lower_name), None)
        if found_key:
            self.play(found_key)
            return

        # 3. Lazy-load from catalog for cold-start cases.
        catalog_match = next(
            (f for f in self.get_animation_catalog() if f["name"].lower() == lower_name), None
        )
        if catalog_match:
            async def _load_and_play():
                try:
                    await self.load_animation_file(catalog_match)
                    loaded_key = next((k for k in self.actions if k.lower() == lower_name), None)
                    if loaded_key:
                        self.play(loaded_key)
                except Exception as error:  # noqa: BLE001
                    console.warn(f"Animation '{requested_name}' failed to load on demand.", str(error))

            asyncio.ensure_future(_load_and_play())
            return

        console.warn(f"Animation '{requested_name}' not found.")

    def on_animation_finished(self, e):
        clip_name = e.action.getClip().name
        is_loop_once = e.action.loop == self.THREE.LoopOnce

        if clip_name != "HappyIdle" and clip_name != "Macarena_dance" and is_loop_once:
            self.play(self.main_idle)

    def play(self, name):
        action = self.actions.get(name)
        if not action:
            return
        if self.active_action == action:
            return

        if self.active_action:
            self.active_action.fadeOut(0.5)

        action.reset().setEffectiveTimeScale(1).setEffectiveWeight(1).fadeIn(0.5).play()
        self.active_action = action

        if name == self.main_idle:
            self.current_state = "idle"
        else:
            self.current_state = name

    def cleanup(self):
        if self.mixer:
            self.mixer.stopAllAction()
        if self.expression_timer is not None:
            window.clearTimeout(self.expression_timer)
            self.expression_timer = None

    # ------------------------------------------------------------------ #
    # camelCase aliases for the orchestrator (drop-in integration)
    # ------------------------------------------------------------------ #
    getAvailableAnimations = get_available_animations
    getAnimationCatalog = get_animation_catalog
    setSpeakingState = set_speaking_state
    setSpeechIntensity = set_speech_intensity
    setSpeechTranscript = set_speech_transcript
    triggerNamedAnimation = trigger_named_animation
    setExpression = set_expression
