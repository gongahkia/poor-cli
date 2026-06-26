<script lang="ts">
  import { createEventDispatcher, onDestroy, onMount } from 'svelte';
  import * as THREE from 'three';
  import { GLTFExporter } from 'three/examples/jsm/exporters/GLTFExporter.js';
  import { GLTFLoader } from 'three/examples/jsm/loaders/GLTFLoader.js';
  import type { LayoutData, LayoutItem } from './types';
  import { downloadBlob } from './storage';

  export let layout: LayoutData;
  export let selectedId = '';
  export let mode: 'select' | 'draw_wall' | 'measure' = 'select';
  export let showGrid = true;
  export let wireframe = false;
  export let shadows = true;
  export let gridSize = 0.25;
  export let lightMode = false;

  const dispatch = createEventDispatcher<{
    select: string;
    move: { id: string; x: number; z: number };
    wall: { a: { x: number; z: number }; b: { x: number; z: number } };
    measure: { distance: number };
    glb: LayoutItem[];
  }>();

  let host: HTMLDivElement;
  let renderer: THREE.WebGLRenderer;
  let scene: THREE.Scene;
  let camera: THREE.PerspectiveCamera;
  let grid: THREE.GridHelper;
  let raycaster: THREE.Raycaster;
  let pointer = new THREE.Vector2();
  let plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), 0);
  let groundPoint = new THREE.Vector3();
  let meshes = new Map<string, THREE.Mesh>();
  let raf = 0;
  let wallStart: { x: number; z: number } | null = null;
  let measureStart: { x: number; z: number } | null = null;
  let dragging = '';

  $: if (scene) renderLayout();
  $: if (scene) {
    grid.visible = showGrid;
    scene.background = new THREE.Color(lightMode ? 0xf7fafa : 0x0b0b0d);
    for (const mesh of meshes.values()) {
      const mat = mesh.material as THREE.MeshStandardMaterial;
      mat.wireframe = wireframe;
      mesh.castShadow = shadows;
      mesh.receiveShadow = shadows;
      const outline = mesh.getObjectByName('selection-outline') as THREE.LineSegments | undefined;
      if (outline) outline.visible = mesh.userData.id === selectedId;
    }
  }

  onMount(() => {
    scene = new THREE.Scene();
    scene.background = new THREE.Color(0x0b0b0d);
    camera = new THREE.PerspectiveCamera(55, 1, 0.05, 200);
    camera.position.set(5.8, 5.3, 5.8);
    camera.lookAt(0, 0, 0);
    renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    renderer.shadowMap.enabled = true;
    host.appendChild(renderer.domElement);
    raycaster = new THREE.Raycaster();

    const hemi = new THREE.HemisphereLight(0xffffff, 0x223033, 1.6);
    scene.add(hemi);
    const sun = new THREE.DirectionalLight(0xffffff, 1.8);
    sun.position.set(4, 8, 3);
    sun.castShadow = true;
    scene.add(sun);
    grid = new THREE.GridHelper(40, 160, 0x314143, 0x20282a);
    scene.add(grid);

    resize();
    renderLayout();
    window.addEventListener('resize', resize);
    renderer.domElement.addEventListener('pointerdown', pointerDown);
    renderer.domElement.addEventListener('pointermove', pointerMove);
    window.addEventListener('pointerup', pointerUp);
    tick();
  });

  onDestroy(() => {
    cancelAnimationFrame(raf);
    window.removeEventListener('resize', resize);
    window.removeEventListener('pointerup', pointerUp);
    renderer?.dispose();
  });

  function resize() {
    const rect = host.getBoundingClientRect();
    renderer.setSize(Math.max(1, rect.width), Math.max(1, rect.height), false);
    camera.aspect = Math.max(1, rect.width) / Math.max(1, rect.height);
    camera.updateProjectionMatrix();
  }

  function tick() {
    renderer.render(scene, camera);
    raf = requestAnimationFrame(tick);
  }

  function snap(value: number) {
    return Math.round(value / gridSize) * gridSize;
  }

  function itemMaterial(item: LayoutItem) {
    const color = item.color || (item.type === 'wall' ? 0x9aa4a8 : 0x66717a);
    return new THREE.MeshStandardMaterial({
      color,
      roughness: 0.72,
      metalness: 0.03,
      wireframe,
    });
  }

  function outlineFor(item: LayoutItem) {
    const geo = new THREE.EdgesGeometry(new THREE.BoxGeometry(item.geo[0] + 0.02, item.geo[1] + 0.02, item.geo[2] + 0.02));
    const line = new THREE.LineSegments(geo, new THREE.LineBasicMaterial({ color: 0xffffff, linewidth: 2 }));
    line.name = 'selection-outline';
    line.visible = item.id === selectedId;
    return line;
  }

  function renderLayout() {
    const nextIds = new Set((layout.items || []).map((item) => item.id || ''));
    for (const [id, mesh] of meshes) {
      if (!nextIds.has(id)) {
        scene.remove(mesh);
        meshes.delete(id);
      }
    }
    for (const item of layout.items || []) {
      const id = item.id || '';
      if (!id || !item.geo || !item.pos) continue;
      let mesh = meshes.get(id);
      if (!mesh) {
        mesh = new THREE.Mesh(new THREE.BoxGeometry(item.geo[0], item.geo[1], item.geo[2]), itemMaterial(item));
        mesh.userData.id = id;
        mesh.userData.itemType = item.type;
        mesh.add(outlineFor(item));
        scene.add(mesh);
        meshes.set(id, mesh);
      } else {
        mesh.geometry.dispose();
        mesh.geometry = new THREE.BoxGeometry(item.geo[0], item.geo[1], item.geo[2]);
        const material = mesh.material as THREE.MeshStandardMaterial;
        material.color.setHex(item.color || (item.type === 'wall' ? 0x9aa4a8 : 0x66717a));
        material.wireframe = wireframe;
      }
      mesh.position.set(item.pos[0], item.pos[1], item.pos[2]);
      mesh.rotation.y = item.rot || 0;
      mesh.visible = item.visible !== false;
      mesh.castShadow = shadows;
      mesh.receiveShadow = shadows;
      mesh.userData.locked = Boolean(item.locked);
      const outline = mesh.getObjectByName('selection-outline') as THREE.LineSegments | undefined;
      if (outline) outline.visible = id === selectedId;
    }
  }

  function pick(event: PointerEvent) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects([...meshes.values()], false);
    return hits[0]?.object as THREE.Mesh | undefined;
  }

  function ground(event: PointerEvent) {
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    raycaster.ray.intersectPlane(plane, groundPoint);
    return { x: snap(groundPoint.x), z: snap(groundPoint.z) };
  }

  function pointerDown(event: PointerEvent) {
    const point = ground(event);
    if (mode === 'draw_wall') {
      if (!wallStart) wallStart = point;
      else {
        dispatch('wall', { a: wallStart, b: point });
        wallStart = null;
      }
      return;
    }
    if (mode === 'measure') {
      if (!measureStart) measureStart = point;
      else {
        dispatch('measure', { distance: Math.hypot(point.x - measureStart.x, point.z - measureStart.z) });
        measureStart = null;
      }
      return;
    }
    const hit = pick(event);
    if (hit) {
      dispatch('select', hit.userData.id);
      if (!hit.userData.locked) {
        dragging = hit.userData.id;
        renderer.domElement.setPointerCapture(event.pointerId);
      }
    } else {
      dispatch('select', '');
    }
  }

  function pointerMove(event: PointerEvent) {
    if (!dragging) return;
    const point = ground(event);
    dispatch('move', { id: dragging, x: point.x, z: point.z });
  }

  function pointerUp() {
    dragging = '';
  }

  export function screenshot() {
    renderer.domElement.toBlob((blob) => {
      if (blob) downloadBlob(blob, 'haus-screenshot.png');
    });
  }

  export function frame() {
    const box = new THREE.Box3();
    for (const mesh of meshes.values()) box.expandByObject(mesh);
    const size = box.getSize(new THREE.Vector3());
    const center = box.getCenter(new THREE.Vector3());
    const radius = Math.max(4, size.length() * 0.7);
    camera.position.set(center.x + radius, radius * 0.75, center.z + radius);
    camera.lookAt(center.x, 0, center.z);
  }

  export async function loadGlb(file: File) {
    const url = URL.createObjectURL(file);
    try {
      const gltf = await new GLTFLoader().loadAsync(url);
      const imported: LayoutItem[] = [];
      gltf.scene.updateMatrixWorld(true);
      gltf.scene.traverse((child) => {
        const mesh = child as THREE.Mesh;
        if (!mesh.isMesh) return;
        const box = new THREE.Box3().setFromObject(mesh);
        const size = box.getSize(new THREE.Vector3());
        const center = box.getCenter(new THREE.Vector3());
        imported.push({
          id: crypto.randomUUID?.() || `glb-${Date.now()}`,
          type: 'model_part',
          name: mesh.name || 'GLB part',
          pos: [center.x, Math.max(size.y / 2, center.y), center.z],
          geo: [Math.max(0.05, size.x), Math.max(0.05, size.y), Math.max(0.05, size.z)],
          rot: mesh.rotation.y || 0,
          color: (mesh.material as THREE.MeshStandardMaterial)?.color?.getHex?.() || 0x8b9499,
          visible: true,
        });
      });
      dispatch('glb', imported);
    } finally {
      URL.revokeObjectURL(url);
    }
  }

  export function exportGlb() {
    const exportScene = new THREE.Scene();
    for (const mesh of meshes.values()) {
      if (!mesh.visible) continue;
      const clone = mesh.clone();
      clone.userData = { ...clone.userData, hausSemantic: true, units: 'meters' };
      const outline = clone.getObjectByName('selection-outline');
      if (outline) clone.remove(outline);
      exportScene.add(clone);
    }
    new GLTFExporter().parse(
      exportScene,
      (result) => downloadBlob(new Blob([result as ArrayBuffer], { type: 'application/octet-stream' }), 'haus-export.glb'),
      (error) => console.error('GLB export failed', error),
      { binary: true },
    );
  }
</script>

<div class="scene-canvas" bind:this={host}></div>
