import * as THREE from 'three';
import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js';
import * as vrm from '@pixiv/three-vrm';
import * as vrma from '@pixiv/three-vrm-animation';
import * as genai from '@google/genai';

window.THREE = THREE;
window.GoogleGenAI = genai.GoogleGenAI;
window.GENAI = genai;
window.GLTFLoader = GLTFLoader;
window.OrbitControls = OrbitControls;
window.VRM = vrm;
window.VRMLoaderPlugin = vrm.VRMLoaderPlugin;
window.VRMUtils = vrm.VRMUtils;
window.VRMA = vrma;
window.VRMAnimationLoaderPlugin = vrma.VRMAnimationLoaderPlugin;
window.createVRMAnimationClip = vrma.createVRMAnimationClip;

window.__libsReady = Promise.resolve(true);
console.log('✅ Local Three.js + three-vrm libraries bundled and exposed');
