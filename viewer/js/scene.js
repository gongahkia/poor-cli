import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { S, SIDEBAR_W } from './state.js';
export function initScene() {
  S.scene = new THREE.Scene();
  S.scene.background = new THREE.Color(0x222222);
  S.camera = new THREE.PerspectiveCamera(50, (innerWidth - SIDEBAR_W) / innerHeight, 0.1, 500);
  S.camera.position.set(10, 8, 10);
  S.camera.lookAt(0, 0, 0);
  S.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  S.renderer.setSize(innerWidth - SIDEBAR_W, innerHeight);
  S.renderer.setPixelRatio(devicePixelRatio);
  S.renderer.shadowMap.enabled = true;
  S.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  S.renderer.toneMapping = THREE.ACESFilmicToneMapping;
  S.renderer.toneMappingExposure = 1.0;
  document.body.prepend(S.renderer.domElement);
  S.orbit = new OrbitControls(S.camera, S.renderer.domElement);
  S.orbit.enableDamping = true;
  S.scene.add(new THREE.AmbientLight(0xffffff, 0.4));
  S.scene.add(new THREE.HemisphereLight(0xb1e1ff, 0xb97a20, 0.3));
  S.dirLight = new THREE.DirectionalLight(0xffffff, 0.9);
  S.dirLight.position.set(10, 20, 10);
  S.dirLight.castShadow = true;
  S.dirLight.shadow.mapSize.set(2048, 2048);
  Object.assign(S.dirLight.shadow.camera, { left: -20, right: 20, top: 20, bottom: -20 });
  S.scene.add(S.dirLight);
  const ground = new THREE.Mesh(
    new THREE.PlaneGeometry(100, 100),
    new THREE.ShadowMaterial({ opacity: 0.15 })
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  S.scene.add(ground);
  document.getElementById('wireframe-toggle').addEventListener('change', (e) => {
    for (const m of S.modelParts) if (m.material) m.material.wireframe = e.target.checked;
  });
  document.getElementById('shadows-toggle').addEventListener('change', (e) => {
    S.renderer.shadowMap.enabled = e.target.checked;
    for (const m of S.modelParts) { m.castShadow = e.target.checked; m.receiveShadow = e.target.checked; }
    S.dirLight.castShadow = e.target.checked;
    S.renderer.shadowMap.needsUpdate = true;
  });
  window.addEventListener('resize', () => {
    S.camera.aspect = (innerWidth - SIDEBAR_W) / innerHeight;
    S.camera.updateProjectionMatrix();
    S.renderer.setSize(innerWidth - SIDEBAR_W, innerHeight);
  });
}
