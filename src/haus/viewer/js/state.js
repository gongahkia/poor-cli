import * as THREE from 'three';
export const SIDEBAR_W = 220;
export const MAX_UNDO = 50;
export const WALL_COLOR = 0x666666;
export const S = {
  scene: null, camera: null, renderer: null, orbit: null, dirLight: null, gridGroup: null,
  draggables: [], modelParts: [], userWalls: [], hiddenObjects: [],
  undoStack: [], redoStack: [],
  selectedTarget: null, multiSelected: [], dragTarget: null, dragStartPos: null,
  dragOffset: new THREE.Vector3(), dragLastValid: null,
  snapEnabled: true, gridDivisions: 4, collisionEnabled: true,
  wallMode: false, wallStart: null, wallPreview: null, wallHeight: 2.6, wallThickness: 0.15,
  placeMode: false, placeGhost: null, placeType: null, placeBlocked: false,
  fpsMode: false, measureMode: false, measureStart: null, measureLine: null, measureLabel: null,
  clipboard: null,
  layoutMetadata: null, layoutRooms: [],
  raycaster: new THREE.Raycaster(), mouse: new THREE.Vector2(),
  dragPlane: new THREE.Plane(new THREE.Vector3(0, 1, 0), 0),
};
export const fn = {};
