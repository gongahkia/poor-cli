import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { S, SIDEBAR_W } from './state.js';

const THEMES = {
  dark: {
    background: 0x0f0f0f,
    fog: 0x0f0f0f,
    floor: 0x1f1f1f,
    ambient: 0.32,
    hemiSky: 0xd8ccff,
    hemiGround: 0x19141f,
    hemi: 0.48,
  },
  light: {
    background: 0xf4f1fb,
    fog: 0xf4f1fb,
    floor: 0xded8ea,
    ambient: 0.54,
    hemiSky: 0xf5f3ff,
    hemiGround: 0xb3a8c8,
    hemi: 0.42,
  },
};

let floorMesh = null;
let ambientLight = null;
let hemisphereLight = null;
let contactShadowTexture = null;

export function createSceneMaterial(kind, color, options = {}) {
  const base = new THREE.Color(color ?? 0x888888);
  const isGhost = kind === 'ghost';
  const materialColor = base.clone();

  if (kind === 'wall' || kind === 'model') {
    materialColor.lerp(new THREE.Color(0xf3eee3), 0.18);
  } else if (kind === 'furniture') {
    materialColor.offsetHSL(0, 0.02, 0.02);
  }

  const material = new THREE.MeshStandardMaterial({
    color: materialColor,
    roughness: kind === 'furniture' ? 0.68 : 0.82,
    metalness: 0.02,
    envMapIntensity: 0.45,
    transparent: isGhost || options.transparent === true,
    opacity: options.opacity ?? (isGhost ? 0.46 : 1),
  });

  if (isGhost) {
    material.depthWrite = false;
    material.roughness = 0.5;
  }

  return material;
}

export function prepareMeshForScene(mesh, kind, color, options = {}) {
  if (options.replaceMaterial !== false) {
    const oldMaterial = mesh.material;
    mesh.material = createSceneMaterial(kind, color, options);
    if (oldMaterial && oldMaterial !== mesh.material && !Array.isArray(oldMaterial)) {
      oldMaterial.dispose?.();
    }
  } else if (mesh.material?.isMeshStandardMaterial) {
    mesh.material.roughness = Math.max(mesh.material.roughness ?? 0, 0.62);
    mesh.material.metalness = Math.min(mesh.material.metalness ?? 0.02, 0.08);
    mesh.material.envMapIntensity = Math.max(mesh.material.envMapIntensity ?? 0, 0.35);
  }

  mesh.castShadow = true;
  mesh.receiveShadow = true;
  if (kind !== 'ghost' && options.contactShadow !== false) addContactShadow(mesh, kind);
  return mesh;
}

function getContactShadowTexture() {
  if (contactShadowTexture) return contactShadowTexture;
  const canvas = document.createElement('canvas');
  canvas.width = 96;
  canvas.height = 96;
  const ctx = canvas.getContext('2d');
  const gradient = ctx.createRadialGradient(48, 48, 4, 48, 48, 48);
  gradient.addColorStop(0, 'rgba(0,0,0,0.38)');
  gradient.addColorStop(0.45, 'rgba(0,0,0,0.18)');
  gradient.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, 96, 96);
  contactShadowTexture = new THREE.CanvasTexture(canvas);
  contactShadowTexture.colorSpace = THREE.SRGBColorSpace;
  return contactShadowTexture;
}

function meshLocalSize(mesh) {
  const params = mesh.geometry?.parameters;
  if (params?.width && params?.height && params?.depth) {
    return new THREE.Vector3(params.width, params.height, params.depth);
  }
  mesh.geometry?.computeBoundingBox?.();
  const box = mesh.geometry?.boundingBox;
  return box ? box.getSize(new THREE.Vector3()) : new THREE.Vector3(1, 1, 1);
}

function addContactShadow(mesh, kind) {
  if (mesh.getObjectByName('_contact_shadow')) return;
  const size = meshLocalSize(mesh);
  if (size.x < 0.04 || size.z < 0.04) return;
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(size.x * 1.35, size.z * 1.35),
    new THREE.MeshBasicMaterial({
      map: getContactShadowTexture(),
      transparent: true,
      opacity: kind === 'wall' || kind === 'model' ? 0.18 : 0.24,
      depthWrite: false,
    })
  );
  shadow.name = '_contact_shadow';
  shadow.rotation.x = -Math.PI / 2;
  shadow.position.y = -size.y / 2 + 0.006;
  shadow.renderOrder = -2;
  shadow.raycast = () => {};
  mesh.add(shadow);
}

function applySceneTheme(light) {
  const theme = light ? THEMES.light : THEMES.dark;
  S.scene.background = new THREE.Color(theme.background);
  S.scene.fog = new THREE.Fog(theme.fog, 32, 82);
  if (floorMesh) floorMesh.material.color.setHex(theme.floor);
  if (ambientLight) ambientLight.intensity = theme.ambient;
  if (hemisphereLight) {
    hemisphereLight.color.setHex(theme.hemiSky);
    hemisphereLight.groundColor.setHex(theme.hemiGround);
    hemisphereLight.intensity = theme.hemi;
  }
  if (S.renderer) S.renderer.toneMappingExposure = light ? 0.98 : 1.08;
}

export function initScene() {
  S.scene = new THREE.Scene();
  const isLight = localStorage.getItem('haus-theme') === 'light';
  if (isLight) document.body.classList.add('light');
  S.camera = new THREE.PerspectiveCamera(45, (innerWidth - SIDEBAR_W) / innerHeight, 0.1, 500);
  S.camera.position.set(8.5, 6.2, 9.5);
  S.camera.lookAt(0, 0.7, 0);
  S.renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
  S.renderer.setSize(innerWidth - SIDEBAR_W, innerHeight);
  S.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
  S.renderer.shadowMap.enabled = true;
  S.renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  S.renderer.toneMapping = THREE.ACESFilmicToneMapping;
  S.renderer.outputColorSpace = THREE.SRGBColorSpace;
  document.body.prepend(S.renderer.domElement);
  S.orbit = new OrbitControls(S.camera, S.renderer.domElement);
  S.orbit.enableDamping = true;
  S.orbit.target.set(0, 0.7, 0);
  S.orbit.maxPolarAngle = Math.PI * 0.47;
  S.orbit.minDistance = 2.5;
  S.orbit.maxDistance = 55;
  ambientLight = new THREE.AmbientLight(0xffffff, 0.35);
  S.scene.add(ambientLight);
  hemisphereLight = new THREE.HemisphereLight(0xd8ccff, 0x19141f, 0.45);
  S.scene.add(hemisphereLight);
  S.dirLight = new THREE.DirectionalLight(0xfff7ed, 1.35);
  S.dirLight.position.set(-8, 18, 11);
  S.dirLight.castShadow = true;
  S.dirLight.shadow.mapSize.set(2048, 2048);
  S.dirLight.shadow.bias = -0.00008;
  S.dirLight.shadow.normalBias = 0.025;
  S.dirLight.shadow.radius = 5;
  Object.assign(S.dirLight.shadow.camera, {
    left: -28,
    right: 28,
    top: 28,
    bottom: -28,
    near: 1,
    far: 55,
  });
  S.scene.add(S.dirLight);
  const fillLight = new THREE.DirectionalLight(0x8b5cf6, 0.18);
  fillLight.position.set(12, 8, -10);
  S.scene.add(fillLight);
  floorMesh = new THREE.Mesh(
    new THREE.PlaneGeometry(120, 120),
    new THREE.MeshStandardMaterial({ color: 0x1f1f1f, roughness: 0.94, metalness: 0.0 })
  );
  floorMesh.rotation.x = -Math.PI / 2;
  floorMesh.position.y = -0.02;
  floorMesh.receiveShadow = true;
  S.scene.add(floorMesh);
  applySceneTheme(isLight);
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
  const themeBtn = document.getElementById('theme-btn');
  if (isLight) themeBtn.textContent = 'Dark';
  themeBtn.addEventListener('click', () => {
    const light = document.body.classList.toggle('light');
    applySceneTheme(light);
    localStorage.setItem('haus-theme', light ? 'light' : 'dark');
    themeBtn.textContent = light ? 'Dark' : 'Light';
  });
}
