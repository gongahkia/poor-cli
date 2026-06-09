import * as THREE from 'three';
export const PLANNER_W = 440;
export function sceneViewportLeft() {
  return innerWidth <= 900 ? 0 : Number.parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--planner-w')) || PLANNER_W;
}
export function sceneViewportWidth() {
  return Math.max(1, innerWidth - sceneViewportLeft());
}
export function scenePointerX(clientX) {
  return ((clientX - sceneViewportLeft()) / sceneViewportWidth()) * 2 - 1;
}
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
  caseReview: null, caseOverlayGroup: null,
  raycaster: new THREE.Raycaster(), mouse: new THREE.Vector2(),
  dragPlane: new THREE.Plane(new THREE.Vector3(0, 1, 0), 0),
};
export const fn = {};
