import { S } from './state.js';
import { initScene } from './scene.js';
import { initGrid } from './grid.js';
import { initCollision } from './collision.js';
import { initUndo } from './undo.js';
import { initSelection } from './selection.js';
import { initFurniture } from './furniture.js';
import { initWalls } from './walls.js';
import { initSceneList } from './sceneList.js';
import { initCamera, updateFps } from './camera.js';
import { initIO } from './io.js';
import { initShortcuts } from './shortcuts.js';
import { initContextMenu } from './contextmenu.js';
import { initOverlay } from './overlay.js';
import { initMeasure } from './measure.js';
import { initSvgExport } from './svgExport.js';
import { initChat } from './chat.js';
import { initCommandPalette } from './commandpalette.js';
import { initSightline } from './sightline.js';
import { initBtoLibrary } from './btoLibrary.js';
import { initRoomCapture } from './roomCapture.js';
import { initCatalog } from './catalog.js';
import { initFloorplanUpload } from './floorplanUpload.js';
import { initProjectWorkbench } from './project.js';
initScene();
initGrid();
initCollision();
initUndo();
initSelection();
initFurniture();
initWalls();
initSceneList();
initCamera();
initIO();
initBtoLibrary();
initFloorplanUpload();
initRoomCapture();
initCatalog();
initProjectWorkbench();
const actionsToggle = document.getElementById('actions-toggle');
const toolbar = document.getElementById('toolbar');
if (actionsToggle && toolbar) {
  actionsToggle.addEventListener('click', () => {
    toolbar.classList.toggle('open');
  });
}
const toolsToggle = document.getElementById('tools-toggle');
const sidebar = document.getElementById('sidebar');
if (toolsToggle && sidebar) {
  toolsToggle.addEventListener('click', () => {
    sidebar.classList.toggle('open');
  });
}
initShortcuts();
initContextMenu();
initOverlay();
initMeasure();
initSvgExport();
initSightline();
initChat();
initCommandPalette();
function animate() {
  requestAnimationFrame(animate);
  updateFps();
  S.orbit.update();
  S.renderer.render(S.scene, S.camera);
}
animate();
