"""VRMLoader — Python port of managers/vrmLoader.js.

Loads a .vrm via Three.js GLTFLoader + @pixiv/three-vrm's VRMLoaderPlugin, then
applies the same scene transform and T-pose fix as the original. (IndexedDB
caching from the JS version is omitted for now; the browser HTTP cache covers it.)
"""

import math

from js import window

from .jsutil import proxy


class VRMLoader:
    def __init__(self):
        self.THREE = window.THREE
        self.loader = window.GLTFLoader.new()
        self.loader.setCrossOrigin("anonymous")
        # register((parser) => new VRMLoaderPlugin(parser))
        self.loader.register(proxy(lambda parser: window.VRMLoaderPlugin.new(parser)))

    async def load_vrm_from_path(self, path):
        if not path:
            print("VRMLoader: Empty path provided")
            return None
        try:
            print(f"🌐 VRMLoader: Fetching from network: {path}")
            gltf = await self.loader.loadAsync(path)
            vrm = gltf.userData.vrm
            self.setup_vrm_model(vrm)
            return vrm
        except Exception as error:  # noqa: BLE001
            print(f"VRMLoader: Error loading {error}")
            raise

    async def load_vrm_from_file(self, file):
        try:
            print(f"Loading VRM model from file: {file.name}")
            array_buffer = await file.arrayBuffer()
            gltf = await self.loader.parseAsync(array_buffer, "")
            vrm = gltf.userData.vrm
            self.setup_vrm_model(vrm)
            return vrm
        except Exception as error:  # noqa: BLE001
            print(f"Failed to load VRM from file: {error}")
            raise

    def cleanup_vrm(self, vrm):
        if not vrm:
            return
        if hasattr(vrm, "dispose"):
            try:
                vrm.dispose()
            except Exception as e:  # noqa: BLE001
                print(f"Error disposing VRM instance: {e}")
        if getattr(vrm, "scene", None):
            def on_child(child):
                if getattr(child, "isMesh", False):
                    if getattr(child, "geometry", None):
                        child.geometry.dispose()
                    mat = child.material
                    materials = mat if hasattr(mat, "length") else [mat]
                    for material in materials:
                        if material:
                            material.dispose()
                return None
            from .jsutil import proxy as _proxy
            vrm.scene.traverse(_proxy(on_child))

    def setup_vrm_model(self, vrm):
        if not vrm:
            return
        vrm.scene.rotation.y = math.pi
        vrm.scene.scale.set(2, 2, 2)
        vrm.scene.position.set(0, -1.2, -0.3)
        vrm.scene.castShadow = True
        vrm.scene.receiveShadow = True
        self.fix_t_pose(vrm)

    def fix_t_pose(self, vrm):
        if not vrm or not vrm.humanoid:
            return
        try:
            left = vrm.humanoid.getNormalizedBoneNode("leftUpperArm")
            right = vrm.humanoid.getNormalizedBoneNode("rightUpperArm")
            if left:
                left.rotation.z = 1.0
                left.rotation.x = 0.3
                left.rotation.y = 0.2
            if right:
                right.rotation.z = -1.0
                right.rotation.x = 0.3
                right.rotation.y = -0.2
        except Exception as error:  # noqa: BLE001
            print(f"Error fixing T-pose: {error}")

    # camelCase aliases for orchestrator parity
    loadVRMFromPath = load_vrm_from_path
    loadVRMFromFile = load_vrm_from_file
    cleanupVRM = cleanup_vrm
