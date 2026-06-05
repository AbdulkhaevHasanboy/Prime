"""SceneManager — Python port of managers/sceneManager.js.

Builds and drives the Three.js scene (renderer, camera, lighting, OrbitControls,
render loop) entirely from Python via JS interop. THREE is exposed on `window`
by the index.html bootstrap.
"""

import math
import re

from js import window, document, performance, requestAnimationFrame

from .jsutil import obj, proxy


class SceneManager:
    def __init__(self, canvas, options=None):
        options = options or {}
        self.canvas = canvas
        self.THREE = window.THREE
        self.options = {
            "antialias": options.get("antialias", False),
            "alpha": options.get("alpha", False),
            "shadows": options.get("shadows", False),
            "powerPreference": options.get("powerPreference", "high-performance"),
            "pixelRatioCap": options["pixelRatioCap"]
            if isinstance(options.get("pixelRatioCap"), (int, float)) and options["pixelRatioCap"] > 0
            else 1,
        }
        self.renderer = None
        self.scene = None
        self.camera = None
        self.controls = None
        self.clock = self.THREE.Clock.new()
        self.mouse = {"x": 0.0, "y": 0.0}
        self.update_callbacks = []
        self.current_fps = 0
        self._fps_frames = 0
        self._fps_last = performance.now()
        self.is_rendering = False
        self.render_pixel_ratio = 1
        self.background_color = self.normalize_background_color(options.get("backgroundColor"))
        self._animate_proxy = None
        self.animation_frame_id = None

    def initialize(self):
        THREE = self.THREE
        try:
            self.renderer = THREE.WebGLRenderer.new(
                obj(
                    antialias=self.options["antialias"],
                    canvas=self.canvas,
                    alpha=self.options["alpha"],
                    powerPreference=self.options["powerPreference"],
                    preserveDrawingBuffer=False,
                    stencil=False,
                )
            )
            self.renderer.setSize(window.innerWidth, window.innerHeight)
            self.render_pixel_ratio = min(window.devicePixelRatio or 1, self.options["pixelRatioCap"])
            self.renderer.setPixelRatio(self.render_pixel_ratio)
            self.renderer.shadowMap.enabled = self.options["shadows"]
            self.renderer.shadowMap.type = THREE.PCFSoftShadowMap

            self.scene = THREE.Scene.new()
            self.scene.background = THREE.Color.new(self.background_color)

            self.camera = THREE.PerspectiveCamera.new(35, window.innerWidth / window.innerHeight, 0.1, 100)
            self.camera.position.set(0, 1.4, 3.5)

            self.setup_lighting()

            self.controls = window.OrbitControls.new(self.camera, self.renderer.domElement)
            self.controls.target.set(0, 1.2, 0)
            self.controls.enablePan = False
            self.controls.minDistance = 1.0
            self.controls.maxDistance = 5.0
            self.controls.maxPolarAngle = math.pi / 2
            self.controls.update()

            self.setup_resize_handler()
            self.setup_mouse_handler()
            return True
        except Exception as error:  # noqa: BLE001
            print(f"SceneManager.initialize error: {error}")
            return False

    def setup_mouse_handler(self):
        def on_move(event):
            self.mouse["x"] = (event.clientX / window.innerWidth) * 2 - 1
            self.mouse["y"] = -(event.clientY / window.innerHeight) * 2 + 1

        window.addEventListener("mousemove", proxy(on_move))

    def setup_lighting(self):
        THREE = self.THREE
        ambient = THREE.AmbientLight.new(0xFFFFFF, 0.4)
        self.scene.add(ambient)

        main_light = THREE.DirectionalLight.new(0xFFFFFF, 1.2)
        main_light.position.set(2, 2, 5)
        main_light.castShadow = self.options["shadows"]
        self.scene.add(main_light)

        rim = THREE.SpotLight.new(0x6366F1, 3.0)
        rim.position.set(-2, 4, -2)
        rim.lookAt(0, 1, 0)
        self.scene.add(rim)

    def setup_resize_handler(self):
        def on_resize(event=None):
            if not self.camera or not self.renderer:
                return
            self.camera.aspect = window.innerWidth / window.innerHeight
            self.camera.updateProjectionMatrix()
            self.renderer.setSize(window.innerWidth, window.innerHeight)
            self.renderer.setPixelRatio(self.render_pixel_ratio)

        window.addEventListener("resize", proxy(on_resize))

    def add_to_scene(self, object3d):
        if self.scene:
            self.scene.add(object3d)

    def remove_from_scene(self, object3d):
        if self.scene:
            self.scene.remove(object3d)

    def normalize_background_color(self, value):
        if isinstance(value, str):
            n = value.strip()
            if re.fullmatch(r"#([0-9a-fA-F]{6})", n):
                return n.lower()
        if isinstance(value, (int, float)) and value == value:
            v = max(0, min(0xFFFFFF, int(value)))
            return "#" + format(v, "06x")
        return "#111827"

    def set_background_color(self, value):
        nxt = self.normalize_background_color(value)
        self.background_color = nxt
        if self.scene:
            self.scene.background = self.THREE.Color.new(nxt)
        return nxt

    def set_background_image(self, url):
        if not url:
            if self.scene:
                self.scene.background = self.THREE.Color.new(self.background_color)
            return
        # Route through server-side proxy to avoid CORS blocks from remote image hosts.
        proxy_url = f"/api/proxy-image?url={window.encodeURIComponent(url)}"

        def on_blob(blob):
            object_url = window.URL.createObjectURL(blob)
            loader = self.THREE.TextureLoader.new()
            loader.crossOrigin = "anonymous"

            def on_tex(texture):
                if self.scene:
                    texture.colorSpace = self.THREE.SRGBColorSpace
                    self.scene.background = texture
                window.URL.revokeObjectURL(object_url)

            def on_err(error=None):
                print(f"Failed to parse background texture: {error}")
                window.URL.revokeObjectURL(object_url)

            loader.load(object_url, proxy(on_tex), None, proxy(on_err))

        def on_response(response):
            if not response.ok:
                raise RuntimeError(f"HTTP error! status: {response.status}")
            return response.blob()

        window.fetch(proxy_url).then(proxy(on_response)).then(proxy(on_blob)).catch(
            proxy(lambda error=None: print(f"Failed to fetch background image: {error}"))
        )

    def cleanup(self):
        self.is_rendering = False
        if self._animate_proxy is not None:
            try:
                from js import cancelAnimationFrame
                if self.animation_frame_id is not None:
                    cancelAnimationFrame(self.animation_frame_id)
            except Exception:  # noqa: BLE001
                pass
        if self.renderer:
            self.renderer.dispose()

    def add_update_callback(self, callback):
        self.update_callbacks.append(callback)

    def start_render_loop(self):
        if self.is_rendering:
            return
        self.is_rendering = True

        def animate(timestamp):
            if not self.is_rendering:
                return
            delta = self.clock.getDelta()
            if self.controls:
                self.controls.update()

            for cb in self.update_callbacks:
                try:
                    cb(delta)
                except Exception as e:  # noqa: BLE001
                    print(f"update callback error: {e}")

            if self.renderer and self.scene and self.camera:
                self.renderer.render(self.scene, self.camera)

            self._fps_frames += 1
            now = performance.now()
            elapsed = now - self._fps_last
            if elapsed >= 1000:
                self.current_fps = round((self._fps_frames * 1000) / elapsed)
                self._fps_frames = 0
                self._fps_last = now
                hud = document.getElementById("hud")
                if hud:
                    hud.textContent = f"{self.current_fps} fps · python · three.js"

            requestAnimationFrame(self._animate_proxy)

        self._animate_proxy = proxy(animate)
        requestAnimationFrame(self._animate_proxy)

    def get_current_fps(self):
        return self.current_fps

    # camelCase aliases for orchestrator parity
    addToScene = add_to_scene
    removeFromScene = remove_from_scene
    addUpdateCallback = add_update_callback
    startRenderLoop = start_render_loop
    setBackgroundColor = set_background_color
    setBackgroundImage = set_background_image
    getCurrentFps = get_current_fps
