import * as THREE from 'three';
import { S, fn } from './state.js';

const STORAGE_KEY = 'haus_project_state';
const AUTOSAVE_DELAY_MS = 500;
const JOURNEYS = {
  renovation: 'Renovation Concept Pack',
  accessibility: 'Accessibility Checker',
  furniture_fit: 'Furniture Fit Planner',
  designer: 'Designer Pre-Sales Assistant',
  blank: 'Blank Project',
};
const SEVERITIES = ['info', 'warning', 'serious', 'blocked'];
const PRODUCT_DISCLAIMER = 'Haus is a concept planning and spatial validation workbench, not BIM authoring, code certification, medical advice, occupational therapy assessment, contractor-ready documentation, or a substitute for professional site verification.';
const ACCESSIBILITY_DISCLAIMER = 'Accessibility checks are planning guidance only, not ADA certification, medical advice, or an occupational therapy assessment.';
const RENOVATION_DISCLAIMER = 'Renovation wall, opening, plumbing, electrical, stair, and structural ideas are concept-only until verified by qualified professionals on site.';

let autosaveTimer = null;
let calibrationClicks = [];

function $(id) {
  return document.getElementById(id);
}

function nowIso() {
  return new Date().toISOString();
}

function uid(prefix) {
  return `${prefix}-${Math.random().toString(16).slice(2, 10)}`;
}

function numberValue(id, fallback = 0) {
  const parsed = Number.parseFloat($(id)?.value || '');
  return Number.isFinite(parsed) ? parsed : fallback;
}

function currentLayout() {
  if (fn.getLayoutData) return migrateLayout(fn.getLayoutData());
  return migrateLayout({ version: 1, items: [] });
}

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function migrateLayout(raw) {
  const layout = raw && typeof raw === 'object' ? clone(raw) : {};
  layout.version = Number(layout.version || 1);
  layout.schema = 'haus.layout.v2';
  layout.layout_schema_version = 2;
  if (!Array.isArray(layout.items)) layout.items = [];
  if (!Array.isArray(layout.rooms)) layout.rooms = [];
  if (!layout.metadata || typeof layout.metadata !== 'object') layout.metadata = {};
  if (!layout.metadata.calibration || typeof layout.metadata.calibration !== 'object') {
    layout.metadata.calibration = {
      scale_m_per_px: layout.metadata.scale_m_per_px || null,
      confidence: layout.metadata.scale_m_per_px ? 'estimated' : 'unknown',
      user_confirmed: false,
    };
  }
  layout.metadata.units = layout.metadata.units || 'm';
  layout.assumptions = Array.isArray(layout.assumptions) ? layout.assumptions : [];
  layout.validation_reports = Array.isArray(layout.validation_reports) ? layout.validation_reports : [];
  layout.exports = Array.isArray(layout.exports) ? layout.exports : [];
  layout.layout_versions = Array.isArray(layout.layout_versions) ? layout.layout_versions : [];
  layout.scenarios = Array.isArray(layout.scenarios) ? layout.scenarios : [];
  layout.items.forEach((item, index) => {
    item.id = item.id || `item-${index + 1}`;
    item.confidence = item.confidence || 'estimated';
    if (item.type === 'wall') {
      item.structural_status = item.structural_status || 'unknown';
      item.structural_confidence = item.structural_confidence || 'unknown';
    }
  });
  layout.rooms.forEach((room, index) => {
    room.id = room.id || `room-${index + 1}`;
    room.label = room.label || room.name || room.id;
    room.kind = room.kind || 'room';
    room.confidence = room.confidence || 'estimated';
  });
  return layout;
}

function newProject(journey = 'blank', layout = currentLayout()) {
  const cleanJourney = JOURNEYS[journey] ? journey : 'blank';
  const migrated = migrateLayout(layout);
  const project = {
    schema: 'haus.project.v1',
    project_schema_version: 1,
    id: uid('project'),
    title: 'Untitled Haus Project',
    journey: cleanJourney,
    journey_label: JOURNEYS[cleanJourney],
    created_at: nowIso(),
    updated_at: nowIso(),
    source_file: migrated.metadata.source_filename || null,
    calibration: migrated.metadata.calibration,
    rooms: migrated.rooms,
    layout: migrated,
    layout_versions: [],
    assumptions: [],
    unknowns: [],
    validation_reports: [],
    exports: [],
    products: [],
    shopping_list_csv: '',
    scenarios: [],
    intake: {
      dwelling_type: '',
      country_or_region: '',
      units: 'm',
      household_profile: '',
      budget_range: '',
      timeline: '',
      main_goal: '',
    },
    journey_details: {},
    chat_context: { journey: cleanJourney, journey_label: JOURNEYS[cleanJourney] },
  };
  captureVersion(project, 'draft', migrated, 'Initial draft');
  project.scenarios.push(makeScenario('Base', cleanJourney, migrated, 'draft'));
  project.active_scenario_id = project.scenarios[0].id;
  return project;
}

function captureVersion(project, status, layout, note = '') {
  const entry = {
    id: uid('version'),
    status,
    created_at: nowIso(),
    note,
    item_count: (layout.items || []).length,
    room_count: (layout.rooms || []).length,
    layout: migrateLayout(layout),
  };
  project.layout_versions.push(entry);
  project.updated_at = nowIso();
  return entry;
}

function makeScenario(name, journey, layout, status = 'draft', parentId = null) {
  const migrated = migrateLayout(layout);
  return {
    id: uid('scenario'),
    name,
    journey,
    status,
    created_at: nowIso(),
    applied_at: status === 'applied' ? nowIso() : null,
    parent_scenario_id: parentId,
    layout: migrated,
    score: scenarioScore(migrated, journey),
    warnings: [],
  };
}

export function initProjectWorkbench() {
  fn.getProjectChatContext = getProjectChatContext;
  fn.getProject = () => S.project;
  fn.migrateLayoutData = migrateLayout;
  fn.validateProjectLayout = validateLayout;
  fn.regenerateValidation = regenerateValidation;
  fn.showValidationOverlay = showValidationOverlay;
  fn.clearValidationOverlay = clearValidationOverlay;
  fn.openManualTracingTools = openManualTracingTools;
  fn.recordProjectVersion = (status, note = '') => {
    syncProjectFromLayout();
    captureVersion(S.project, status, S.project.layout, note);
    scheduleAutosave();
    renderProject();
  };

  S.project = loadProject() || newProject('blank');
  S.activeScenarioId = S.project.active_scenario_id;
  bindProjectUi();
  applyProjectToForm();
  renderProject();
  scheduleAutosave();
}

function bindProjectUi() {
  $('journey-selector')?.addEventListener('change', (e) => setJourney(e.target.value));
  document.querySelectorAll('#journey-first-run button').forEach((button) => {
    button.addEventListener('click', () => setJourney(button.dataset.journey));
  });
  $('project-title')?.addEventListener('input', () => {
    S.project.title = $('project-title').value.trim() || 'Untitled Haus Project';
    scheduleAutosave();
  });
  $('project-save-btn')?.addEventListener('click', saveProjectFile);
  $('project-load-input')?.addEventListener('change', loadProjectFile);
  ['intake-dwelling', 'intake-region', 'intake-units', 'intake-household', 'intake-budget', 'intake-timeline', 'intake-goal'].forEach((id) => {
    $(id)?.addEventListener('input', readIntakeFromForm);
    $(id)?.addEventListener('change', readIntakeFromForm);
  });
  $('save-assumptions-btn')?.addEventListener('click', saveAssumptions);
  $('add-scenario-btn')?.addEventListener('click', addScenario);
  $('duplicate-scenario-btn')?.addEventListener('click', duplicateActiveScenario);
  $('compare-scenario-btn')?.addEventListener('click', compareBeforeAfter);
  $('run-validation-btn')?.addEventListener('click', regenerateValidation);
  $('view-2d-btn')?.addEventListener('click', enter2dReview);
  $('view-3d-btn')?.addEventListener('click', enter3dWalkthrough);
  $('export-scenario-png-btn')?.addEventListener('click', exportAnnotatedPng);
  $('export-report-html-btn')?.addEventListener('click', exportHtmlReport);
  $('calibration-start-btn')?.addEventListener('click', startCalibrationWizard);
  $('recalibrate-btn')?.addEventListener('click', recalibrateFromInputs);
  $('trace-room-btn')?.addEventListener('click', traceRoomRectangle);
  $('add-door-btn')?.addEventListener('click', addDoorOpening);
  $('add-window-btn')?.addEventListener('click', addWindow);
  $('add-fixed-btn')?.addEventListener('click', addFixedElement);
  $('draft-renovation-btn')?.addEventListener('click', draftRenovationScenarios);
  $('run-accessibility-btn')?.addEventListener('click', runAccessibilityReview);
  $('draft-designer-btn')?.addEventListener('click', draftDesignerBrief);
  $('add-product-btn')?.addEventListener('click', addManualProduct);
  $('fit-product-btn')?.addEventListener('click', checkActiveProductFit);
  $('export-shopping-btn')?.addEventListener('click', exportShoppingList);
  document.querySelectorAll('#floorplan-review-checklist input').forEach((input) => {
    input.addEventListener('change', () => {
      const checks = {};
      document.querySelectorAll('#floorplan-review-checklist input').forEach((box) => {
        checks[box.dataset.reviewCheck] = box.checked;
      });
      S.project.extraction_review = checks;
      scheduleAutosave();
    });
  });
}

function setJourney(journey) {
  if (!JOURNEYS[journey]) return;
  syncProjectFromLayout();
  S.project.journey = journey;
  S.project.journey_label = JOURNEYS[journey];
  S.project.chat_context = { journey, journey_label: JOURNEYS[journey] };
  S.project.layout.metadata.project = {
    id: S.project.id,
    title: S.project.title,
    journey,
    journey_label: JOURNEYS[journey],
  };
  if (!$('project-title').value) $('project-title').value = S.project.title;
  captureVersion(S.project, 'revised', S.project.layout, `Journey set to ${JOURNEYS[journey]}`);
  renderProject();
  scheduleAutosave();
  if (fn.pushLayoutToServer) fn.pushLayoutToServer();
}

function loadProject() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || parsed.schema !== 'haus.project.v1') return null;
    parsed.layout = migrateLayout(parsed.layout || { version: 1, items: [] });
    parsed.scenarios = Array.isArray(parsed.scenarios) ? parsed.scenarios : [];
    parsed.products = Array.isArray(parsed.products) ? parsed.products : [];
    return parsed;
  } catch {
    return null;
  }
}

function scheduleAutosave() {
  if (autosaveTimer) clearTimeout(autosaveTimer);
  setAutosave('Autosave pending...');
  autosaveTimer = setTimeout(() => {
    syncProjectFromLayout();
    S.project.updated_at = nowIso();
    localStorage.setItem(STORAGE_KEY, JSON.stringify(S.project));
    setAutosave(`Autosaved ${new Date().toLocaleTimeString()}`);
  }, AUTOSAVE_DELAY_MS);
}

function setAutosave(text) {
  const el = $('autosave-indicator');
  if (el) el.textContent = text;
}

function syncProjectFromLayout() {
  if (!S.project) return;
  const layout = currentLayout();
  layout.metadata.project = {
    id: S.project.id,
    title: S.project.title,
    journey: S.project.journey,
    journey_label: S.project.journey_label,
  };
  layout.assumptions = [...(S.project.assumptions || [])];
  layout.validation_reports = [...(S.project.validation_reports || [])];
  layout.exports = [...(S.project.exports || [])];
  layout.layout_versions = (S.project.layout_versions || []).map((entry) => ({
    id: entry.id,
    status: entry.status,
    created_at: entry.created_at,
    note: entry.note,
    item_count: entry.item_count,
    room_count: entry.room_count,
  }));
  layout.scenarios = S.project.scenarios.map((scenario) => ({
    id: scenario.id,
    name: scenario.name,
    journey: scenario.journey,
    status: scenario.status,
    score: scenario.score,
    created_at: scenario.created_at,
    applied_at: scenario.applied_at,
    parent_scenario_id: scenario.parent_scenario_id,
  }));
  S.project.layout = layout;
  S.project.rooms = layout.rooms || [];
  S.project.calibration = layout.metadata.calibration || {};
  S.layoutMetadata = layout.metadata;
}

function applyProjectToForm() {
  $('project-title').value = S.project.title || '';
  $('journey-selector').value = S.project.journey || 'blank';
  $('intake-dwelling').value = S.project.intake?.dwelling_type || '';
  $('intake-region').value = S.project.intake?.country_or_region || '';
  $('intake-units').value = S.project.intake?.units || 'm';
  $('intake-household').value = S.project.intake?.household_profile || '';
  $('intake-budget').value = S.project.intake?.budget_range || '';
  $('intake-timeline').value = S.project.intake?.timeline || '';
  $('intake-goal').value = S.project.intake?.main_goal || '';
  $('assumptions-input').value = (S.project.assumptions || []).join('\n');
}

function readIntakeFromForm() {
  S.project.intake = {
    dwelling_type: $('intake-dwelling').value.trim(),
    country_or_region: $('intake-region').value.trim(),
    units: $('intake-units').value,
    household_profile: $('intake-household').value.trim(),
    budget_range: $('intake-budget').value.trim(),
    timeline: $('intake-timeline').value.trim(),
    main_goal: $('intake-goal').value.trim(),
  };
  scheduleAutosave();
}

function saveAssumptions() {
  S.project.assumptions = $('assumptions-input').value.split('\n').map((line) => line.trim()).filter(Boolean);
  scheduleAutosave();
  regenerateValidation();
}

function renderProject() {
  if (!S.project) return;
  $('journey-selector').value = S.project.journey;
  document.querySelectorAll('.journey-panel').forEach((panel) => {
    panel.style.display = panel.dataset.panel === S.project.journey ? '' : 'none';
  });
  renderVersionHistory();
  renderScenarios();
  renderUnknowns();
  renderProducts();
}

function renderVersionHistory() {
  const root = $('project-version-history');
  if (!root) return;
  const latest = (S.project.layout_versions || []).slice(-5).reverse();
  root.innerHTML = latest.map((entry) => `<div><strong>${esc(entry.status)}</strong> ${esc(entry.note || '')} <span>${entry.item_count} item(s)</span></div>`).join('');
}

function renderScenarios() {
  const root = $('scenario-list');
  if (!root) return;
  root.innerHTML = '';
  for (const scenario of S.project.scenarios || []) {
    const row = document.createElement('div');
    row.className = `scenario-row${scenario.id === S.activeScenarioId ? ' active' : ''}`;
    const title = document.createElement('strong');
    title.textContent = scenario.name;
    const score = document.createElement('span');
    const values = scenario.score || {};
    score.textContent = `fit ${values.fit ?? '-'} · circulation ${values.circulation ?? '-'} · accessibility ${values.accessibility ?? '-'} · cost ${values.cost_complexity ?? '-'} · confidence ${values.confidence ?? '-'}`;
    const apply = document.createElement('button');
    apply.type = 'button';
    apply.textContent = 'Apply';
    apply.addEventListener('click', () => applyScenario(scenario.id));
    row.addEventListener('click', () => {
      S.activeScenarioId = scenario.id;
      S.project.active_scenario_id = scenario.id;
      renderScenarios();
      scheduleAutosave();
    });
    row.appendChild(title);
    row.appendChild(score);
    row.appendChild(apply);
    root.appendChild(row);
  }
}

function renderUnknowns() {
  const unknowns = unknownsForLayout(currentLayout());
  S.project.unknowns = unknowns;
  const root = $('unknowns-list');
  if (!root) return;
  root.innerHTML = unknowns.length
    ? unknowns.map((item) => `<div class="unknown-row"><strong>${esc(item.field)}</strong><span>${esc(item.message)}</span><em>${esc(item.fix)}</em></div>`).join('')
    : '<div class="unknown-row"><span>No missing measurement blockers recorded.</span></div>';
}

function addScenario() {
  syncProjectFromLayout();
  const name = $('scenario-name').value.trim() || `Scenario ${S.project.scenarios.length + 1}`;
  const scenario = makeScenario(name, S.project.journey, S.project.layout, 'draft');
  S.project.scenarios.push(scenario);
  S.activeScenarioId = scenario.id;
  S.project.active_scenario_id = scenario.id;
  captureVersion(S.project, 'draft', S.project.layout, `Scenario added: ${name}`);
  scheduleAutosave();
  renderProject();
}

function duplicateActiveScenario() {
  const active = activeScenario();
  if (!active) return;
  const cloneScenario = clone(active);
  cloneScenario.id = uid('scenario');
  cloneScenario.name = `${active.name} copy`;
  cloneScenario.status = 'draft';
  cloneScenario.created_at = nowIso();
  cloneScenario.applied_at = null;
  cloneScenario.parent_scenario_id = active.id;
  S.project.scenarios.push(cloneScenario);
  S.activeScenarioId = cloneScenario.id;
  S.project.active_scenario_id = cloneScenario.id;
  captureVersion(S.project, 'revised', currentLayout(), `Scenario duplicated from ${active.name}`);
  scheduleAutosave();
  renderProject();
}

function activeScenario() {
  return (S.project.scenarios || []).find((scenario) => scenario.id === S.activeScenarioId) || S.project.scenarios?.[0] || null;
}

function applyScenario(id) {
  const scenario = (S.project.scenarios || []).find((item) => item.id === id);
  if (!scenario || !fn.applyLayoutData) return;
  fn.applyLayoutData(scenario.layout, { frame: false });
  scenario.status = 'applied';
  scenario.applied_at = nowIso();
  captureVersion(S.project, 'applied', scenario.layout, `Applied ${scenario.name}`);
  if (fn.pushLayoutToServer) fn.pushLayoutToServer();
  regenerateValidation();
}

function compareBeforeAfter() {
  const first = S.project.layout_versions?.[0];
  const active = activeScenario();
  const root = $('validation-results');
  if (!first || !active || !root) return;
  root.innerHTML = `<div class="validation-card info"><strong>Before / After Comparison</strong><p>Before: ${first.item_count} item(s). After: ${(active.layout.items || []).length} item(s). Active scenario: ${esc(active.name)}.</p></div>`;
}

function saveProjectFile() {
  syncProjectFromLayout();
  captureVersion(S.project, 'exported', S.project.layout, 'Project JSON exported');
  downloadText(JSON.stringify(S.project, null, 2), `${slug(S.project.title)}.haus-project.json`, 'application/json');
  S.project.exports.push({ kind: 'project_json', filename: `${slug(S.project.title)}.haus-project.json`, created_at: nowIso(), disclaimer: PRODUCT_DISCLAIMER });
  scheduleAutosave();
  renderProject();
}

function loadProjectFile(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const parsed = JSON.parse(String(reader.result || '{}'));
      if (parsed.schema !== 'haus.project.v1') throw new Error('Not a Haus project JSON file.');
      parsed.layout = migrateLayout(parsed.layout);
      parsed.layout_versions = Array.isArray(parsed.layout_versions) ? parsed.layout_versions : [];
      parsed.scenarios = Array.isArray(parsed.scenarios) ? parsed.scenarios : [];
      parsed.products = Array.isArray(parsed.products) ? parsed.products : [];
      S.project = parsed;
      S.activeScenarioId = parsed.active_scenario_id || parsed.scenarios[0]?.id || null;
      if (fn.applyLayoutData) fn.applyLayoutData(parsed.layout, { frame: true });
      captureVersion(S.project, 'imported', parsed.layout, `Imported ${file.name}`);
      applyProjectToForm();
      renderProject();
      scheduleAutosave();
    } catch (err) {
      setAutosave(err.message || String(err));
    }
  };
  reader.readAsText(file);
  event.target.value = '';
}

function getProjectChatContext(message = '') {
  syncProjectFromLayout();
  return {
    metadata: {
      id: S.project.id,
      title: S.project.title,
      journey: S.project.journey,
      journey_label: S.project.journey_label,
      intake: S.project.intake,
      assumptions: S.project.assumptions,
      unknowns: S.project.unknowns,
    },
    route: routeCommand(message),
    system_prompt: systemPrompt(S.project.journey),
  };
}

function routeCommand(message) {
  const text = String(message || '').toLowerCase();
  if (/\b(apply|use this|commit scenario)\b/.test(text)) return 'apply_plan';
  if (/\b(revise|make it|cheaper|more storage|less renovation|more accessible)\b/.test(text)) return 'revise_plan';
  if (/\b(export|download|report|brief|shopping list)\b/.test(text)) return 'export_report';
  if (/\b(validate|check|sanity|risk|warning|fit)\b/.test(text)) return 'validate_layout';
  if (/\b(move|rotate|resize|delete|lock|unlock|edit)\b/.test(text)) return 'edit_object';
  if (/\b(draft|design|generate|plan|scenario|concept)\b/.test(text)) return 'draft_plan';
  return 'ask_question';
}

function systemPrompt(journey) {
  const boundaries = [PRODUCT_DISCLAIMER];
  if (journey === 'accessibility') boundaries.push(ACCESSIBILITY_DISCLAIMER);
  if (journey === 'renovation') boundaries.push(RENOVATION_DISCLAIMER);
  return `Use the active ${JOURNEYS[journey] || 'Haus'} metadata, keep assumptions editable, cite source URLs when web research influences recommendations, and preserve boundaries: ${boundaries.join(' ')}`;
}

function regenerateValidation() {
  syncProjectFromLayout();
  const report = validateLayout(S.project.layout, S.project.journey);
  S.validationReport = report;
  S.project.validation_reports.push(report);
  S.project.layout.validation_reports = S.project.validation_reports;
  renderValidation(report);
  showValidationOverlay(report.overlays);
  scheduleAutosave();
  return report;
}

function validateLayout(layout, journey = 'blank') {
  const migrated = migrateLayout(layout);
  const warnings = [];
  const items = migrated.items.filter((item) => item.visible !== false);
  const unknowns = unknownsForLayout(migrated);
  if (unknowns.length) {
    warnings.push(warning('warning', 'missing_measurements', 'Some measurements are missing or unconfirmed.', 'Checks are less reliable when scale, rooms, doors, or product dimensions are unknown.', 'Confirm the unknowns before buying or renovating.', 'Project', { unknowns }));
  }
  for (let i = 0; i < items.length; i += 1) {
    for (let j = i + 1; j < items.length; j += 1) {
      const a = rectForItem(items[i]);
      const b = rectForItem(items[j]);
      if (rectsIntersect(a, b)) {
        warnings.push(warning('serious', 'overlap', `${labelForItem(items[i])} overlaps ${labelForItem(items[j])}.`, 'Overlapping footprints can make a scenario impossible.', 'Move or resize one object and regenerate validation.', items[i].room || items[j].room || 'Project', { blocked_area: unionRect(a, b), item_ids: [items[i].id, items[j].id] }));
      }
    }
  }
  if (journey === 'renovation') {
    items.filter((item) => item.type === 'wall' && (item.structural_status || 'unknown') === 'unknown').forEach((item) => {
      warnings.push(warning('serious', 'structural_unknown', 'Wall structural status is unknown.', 'Plan images do not prove whether walls are structural.', 'Treat wall changes as concept-only until verified on site.', 'Project', { item_id: item.id, footprint: rectForItem(item) }));
    });
  }
  if (journey === 'accessibility') {
    warnings.push(...accessibilityWarnings(migrated));
  }
  return {
    id: uid('validation'),
    generated_at: nowIso(),
    journey,
    severity_model: SEVERITIES,
    warnings,
    unknowns,
    room_summaries: roomSummaries(migrated, warnings),
    overlays: overlaysForReport(migrated, warnings),
    disclaimers: [PRODUCT_DISCLAIMER, journey === 'accessibility' ? ACCESSIBILITY_DISCLAIMER : null, journey === 'renovation' ? RENOVATION_DISCLAIMER : null].filter(Boolean),
  };
}

function warning(severity, code, message, explanation, suggestedFix, room = 'Project', geometry = {}) {
  return { severity, code, message, explanation, suggested_fix: suggestedFix, room, geometry };
}

function unknownsForLayout(layout) {
  const unknowns = [];
  const calibration = layout.metadata?.calibration || {};
  if (!calibration.user_confirmed) unknowns.push({ field: 'scale', message: 'Scale is estimated rather than user-confirmed.', fix: 'Draw or enter a known-length segment.' });
  if (!layout.rooms?.length) unknowns.push({ field: 'rooms', message: 'Room boundaries are missing or unconfirmed.', fix: 'Use manual room tracing or confirm extracted rooms.' });
  const hasDoorWidth = layout.items?.some((item) => item.type === 'door' || item.type === 'opening' || item.width_m);
  if (!hasDoorWidth) unknowns.push({ field: 'door_widths', message: 'Door widths are missing.', fix: 'Add door/opening widths for fit and accessibility checks.' });
  (S.project?.products || []).filter((product) => ['unknown', 'estimated'].includes(product.source_confidence)).forEach((product) => {
    unknowns.push({ field: 'product_dimensions', message: `${product.name} dimensions are unverified.`, fix: 'Confirm dimensions from the retailer or manual measurement.' });
  });
  return unknowns;
}

function accessibilityWarnings(layout) {
  const profile = $('access-profile')?.value || 'general_aging_ready';
  const targets = {
    general_aging_ready: [0.8, 0.85, 1.2],
    cane: [0.8, 0.85, 1.2],
    walker: [0.86, 0.9, 1.35],
    wheelchair: [0.915, 0.915, 1.5],
    caregiver_assisted: [0.915, 1.05, 1.65],
    low_vision: [0.8, 0.9, 1.2],
    fall_risk_bathroom: [0.86, 0.9, 1.35],
  }[profile] || [0.8, 0.85, 1.2];
  const [doorMin, pathMin, turning] = targets;
  const warnings = [];
  for (const item of layout.items || []) {
    const width = Number(item.width_m || (item.type === 'door' ? dimsForItem(item).w : 0));
    if ((item.type === 'door' || item.type === 'opening') && width && width < doorMin) {
      warnings.push(warning('blocked', 'doorway_width', `${labelForItem(item)} is ${width.toFixed(2)}m wide; target is ${doorMin.toFixed(2)}m.`, 'The selected profile may not pass through this doorway comfortably.', 'Verify on site and consider widening, removing, or changing the route.', item.room || 'Project', { width_m: width, target_m: doorMin }));
    }
    if (item.furnitureType === 'rug' || item.hazard) {
      warnings.push(warning('warning', 'trip_hazard', `${labelForItem(item)} is marked as a trip hazard.`, 'Rugs, thresholds, clutter zones, and loose obstacles increase fall risk.', 'Remove, secure, or reroute around the hazard.', item.room || 'Project', { footprint: rectForItem(item) }));
    }
  }
  for (let i = 0; i < layout.items.length; i += 1) {
    for (let j = i + 1; j < layout.items.length; j += 1) {
      const gap = rectGap(rectForItem(layout.items[i]), rectForItem(layout.items[j]));
      if (gap > 0 && gap < pathMin) warnings.push(warning('serious', 'path_clearance', `Route gap is ${gap.toFixed(2)}m; target is ${pathMin.toFixed(2)}m.`, 'The active accessibility profile needs a wider route.', 'Move furniture, remove hazards, or create a wider path.', layout.items[i].room || layout.items[j].room || 'Project', { clearance_m: gap, target_m: pathMin }));
    }
  }
  if (layoutBounds(layout).minSide < turning) warnings.push(warning('serious', 'turning_circle', `No obvious ${turning.toFixed(2)}m turning circle fits.`, 'Wheelchair and caregiver-assisted profiles need clear turning space.', 'Clear furniture or verify room dimensions.', 'Project', { diameter_m: turning }));
  if (layout.items.some((item) => item.furnitureType?.startsWith('bed'))) warnings.push(warning('warning', 'bed_transfer', 'Check bed transfer clearance on one side and the foot of bed.', 'Bed transfer access is important for mobility aid and caregiver profiles.', 'Keep at least one side and the foot clear.', 'Bedroom'));
  if (layout.items.some((item) => item.furnitureType === 'toilet')) warnings.push(warning('warning', 'toilet_transfer', 'Check toilet transfer clearance.', 'Bathroom transfer space should be confirmed from actual fixture positions.', 'Mark fixture clearances and verify on site.', 'Bathroom'));
  if (layout.items.some((item) => item.furnitureType === 'shower')) warnings.push(warning('info', 'shower_access', 'Confirm shower label: step-in, walk-in, or curbless.', 'Shower access depends on threshold and floor slope, not only footprint.', 'Record the shower type before recommending changes.', 'Bathroom'));
  if (layout.items.some((item) => item.furnitureType === 'sink')) warnings.push(warning('info', 'vanity_approach', 'Confirm sink and vanity approach clearance.', 'Approach clearance depends on fixture and cabinet depth.', 'Keep front approach clear.', 'Bathroom'));
  if (layout.items.some((item) => ['fridge', 'sink', 'kitchen_counter', 'stove', 'washer'].includes(item.furnitureType))) warnings.push(warning('info', 'kitchen_reach_access', 'Confirm kitchen reach and appliance access.', 'Fridge, sink, counter, stove, and washer need front access.', 'Keep approach and pull-out zones clear.', 'Kitchen'));
  warnings.push(warning('info', 'lighting_recommendation', 'Review lighting for entry, corridor, bathroom, stairs, and night path.', 'Lighting is a non-geometric recommendation until fixtures are entered.', 'Add lighting markers for night routes.'));
  warnings.push(warning('info', 'storage_reach_height', 'Review storage reach heights for daily-use items.', 'Reach height is non-geometric unless shelf heights are entered.', 'Keep daily-use storage between knee and shoulder height.'));
  return warnings;
}

function roomSummaries(layout, warnings) {
  const labels = layout.rooms?.map((room) => room.label) || [];
  const rooms = labels.length ? labels : ['Project'];
  return rooms.map((room) => {
    const roomWarnings = warnings.filter((item) => item.room === room || item.room === 'Project');
    const highest = [...SEVERITIES].reverse().find((sev) => roomWarnings.some((item) => item.severity === sev)) || 'info';
    return { room, warning_count: roomWarnings.length, highest_severity: highest, summary: roomWarnings.length ? `${roomWarnings.length} issue(s) need review.` : 'No blocking issues found.' };
  });
}

function overlaysForReport(layout, warnings) {
  const bounds = layoutBounds(layout);
  const footprints = (layout.items || []).map((item) => ({ type: 'product_footprint', item_id: item.id, label: labelForItem(item), rect: rectForItem(item), measurement: `${dimsForItem(item).w.toFixed(2)}m x ${dimsForItem(item).d.toFixed(2)}m` }));
  return {
    walkway_corridors: [{ type: 'walkway', from: { x: bounds.xMin, z: (bounds.zMin + bounds.zMax) / 2 }, to: { x: bounds.xMax, z: (bounds.zMin + bounds.zMax) / 2 }, width_m: 0.9, measurement: '0.90m target corridor' }],
    blocked_areas: warnings.map((item) => item.geometry?.blocked_area).filter(Boolean),
    door_clearances: (layout.items || []).filter((item) => item.type === 'door' || item.type === 'opening').map((item) => ({ item_id: item.id, width_m: Number(item.width_m || dimsForItem(item).w), measurement: `${Number(item.width_m || dimsForItem(item).w).toFixed(2)}m` })),
    turning_circles: [{ center: { x: (bounds.xMin + bounds.xMax) / 2, z: (bounds.zMin + bounds.zMax) / 2 }, diameter_m: 1.5, measurement: '1.50m turning circle' }],
    product_footprints: footprints,
  };
}

function renderValidation(report) {
  const root = $('validation-results');
  if (!root) return;
  root.innerHTML = '';
  for (const summary of report.room_summaries) {
    const row = document.createElement('div');
    row.className = `validation-card ${summary.highest_severity}`;
    row.innerHTML = `<strong>${esc(summary.room)}</strong><p>${esc(summary.summary)}</p>`;
    root.appendChild(row);
  }
  for (const item of report.warnings) {
    const card = document.createElement('div');
    card.className = `validation-card ${item.severity}`;
    const button = document.createElement('button');
    button.type = 'button';
    button.textContent = 'Show me why';
    button.addEventListener('click', () => showValidationOverlay({ blocked_areas: item.geometry?.blocked_area ? [item.geometry.blocked_area] : [], product_footprints: report.overlays.product_footprints, walkway_corridors: report.overlays.walkway_corridors, door_clearances: report.overlays.door_clearances, turning_circles: report.overlays.turning_circles }));
    card.innerHTML = `<strong>${esc(item.message)}</strong><p>${esc(item.explanation)}</p><p>${esc(item.suggested_fix)}</p>`;
    card.appendChild(button);
    root.appendChild(card);
  }
  renderUnknowns();
}

function showValidationOverlay(overlays) {
  clearValidationOverlay();
  const group = new THREE.Group();
  group.name = 'haus_validation_overlays';
  const addRect = (rect, color, opacity = 0.26, y = 0.04) => {
    if (!rect) return;
    const width = Math.max(0.05, rect.x_max - rect.x_min);
    const depth = Math.max(0.05, rect.z_max - rect.z_min);
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, depth), new THREE.MeshBasicMaterial({ color, transparent: true, opacity, side: THREE.DoubleSide }));
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set((rect.x_min + rect.x_max) / 2, y, (rect.z_min + rect.z_max) / 2);
    group.add(mesh);
  };
  (overlays.blocked_areas || []).forEach((rect) => addRect(rect, 0xef4444, 0.34, 0.06));
  (overlays.product_footprints || []).forEach((item) => addRect(item.rect, 0x2563eb, 0.14, 0.04));
  (overlays.walkway_corridors || []).forEach((corridor) => {
    const rect = {
      x_min: Math.min(corridor.from.x, corridor.to.x),
      z_min: corridor.from.z - corridor.width_m / 2,
      x_max: Math.max(corridor.from.x, corridor.to.x),
      z_max: corridor.from.z + corridor.width_m / 2,
    };
    addRect(rect, 0x22c55e, 0.16, 0.05);
    group.add(labelSprite(corridor.measurement, (rect.x_min + rect.x_max) / 2, rect.z_min, 0x22c55e));
  });
  (overlays.turning_circles || []).forEach((circle) => {
    const mesh = new THREE.Mesh(new THREE.CircleGeometry(circle.diameter_m / 2, 48), new THREE.MeshBasicMaterial({ color: 0xf59e0b, transparent: true, opacity: 0.18, side: THREE.DoubleSide }));
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(circle.center.x, 0.07, circle.center.z);
    group.add(mesh);
    group.add(labelSprite(circle.measurement, circle.center.x, circle.center.z, 0xf59e0b));
  });
  (overlays.door_clearances || []).forEach((door, index) => {
    group.add(labelSprite(door.measurement, -1 + index * 0.45, -1, 0xa855f7));
  });
  S.scene.add(group);
  S.validationOverlayGroup = group;
}

function clearValidationOverlay() {
  if (!S.validationOverlayGroup) return;
  S.scene.remove(S.validationOverlayGroup);
  S.validationOverlayGroup.traverse((child) => {
    if (child.geometry) child.geometry.dispose();
    if (child.material) child.material.dispose();
  });
  S.validationOverlayGroup = null;
}

function labelSprite(text, x, z, color) {
  const canvas = document.createElement('canvas');
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'rgba(255,255,255,0.88)';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = `#${color.toString(16).padStart(6, '0')}`;
  ctx.font = '24px system-ui, sans-serif';
  ctx.fillText(text, 10, 40);
  const texture = new THREE.CanvasTexture(canvas);
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: texture, transparent: true }));
  sprite.position.set(x, 0.35, z);
  sprite.scale.set(1.5, 0.38, 1);
  return sprite;
}

function draftRenovationScenarios() {
  syncProjectFromLayout();
  const priorities = Array.from(document.querySelectorAll('#renovation-priorities input:checked')).map((box) => box.value);
  S.project.journey_details.renovation = {
    goals: $('renovation-goals').value.trim(),
    allowed_wall_changes: $('renovation-wall-changes').value,
    room_priorities: priorities,
  };
  const specs = [
    ['conservative', 'low', 78, 'Keep walls and services fixed; improve storage, furniture, and room functions.'],
    ['balanced', 'medium', 64, 'Explore non-structural openings, visual zoning, and room reassignment.'],
    ['ambitious', 'high', 46, 'Conceptual open-plan and service-zone ideas needing professional verification.'],
  ];
  S.project.scenarios = specs.map(([name, cost, confidence, summary]) => {
    const scenario = makeScenario(name, 'renovation', S.project.layout, 'draft');
    scenario.summary = summary;
    scenario.cost_tier = cost;
    scenario.confidence = confidence;
    scenario.room_priorities = priorities;
    scenario.proposed_wall_changes = name === 'conservative' ? [] : proposedWallChanges(S.project.layout, name);
    scenario.storage_plan = storagePlan(S.project.layout);
    scenario.contractor_questions = renovationQuestions(S.project.layout);
    scenario.materials_and_finishes = { status: 'placeholder', note: 'Qualitative notes only; Haus does not estimate exact costs.' };
    scenario.score = { fit: 70, circulation: name === 'balanced' ? 78 : 66, accessibility: name === 'ambitious' ? 60 : 45, cost_complexity: cost === 'low' ? 25 : cost === 'medium' ? 55 : 85, confidence };
    return scenario;
  });
  S.activeScenarioId = S.project.scenarios[0].id;
  captureVersion(S.project, 'draft', S.project.layout, 'Drafted renovation scenarios');
  renderProject();
  regenerateValidation();
}

function proposedWallChanges(layout, scenarioName) {
  return (layout.items || []).filter((item) => item.type === 'wall').slice(0, 1).map((item) => ({
    item_id: item.id,
    action: scenarioName === 'balanced' ? 'review_opening' : 'review_removal',
    concept_only: true,
    requires_professional_verification: true,
    structural_status: item.structural_status || 'unknown',
  }));
}

function storagePlan(layout) {
  const rooms = layout.rooms?.length ? layout.rooms.map((room) => room.label) : ['Project'];
  return rooms.map((room) => {
    const storageItems = (layout.items || []).filter((item) => item.room === room && /storage|wardrobe|cabinet/i.test(`${item.furnitureType || ''} ${item.name || ''}`));
    return { room, status: storageItems.length ? 'served' : 'under_served', recommendation: storageItems.length ? 'Keep storage accessible.' : 'Add closed storage or built-in placeholder.' };
  });
}

function renovationQuestions(layout) {
  const questions = ['Which walls are confirmed non-structural?', 'Where are plumbing stacks and wet-area constraints?', 'Which rooms, doors, windows, walls, or fixtures are do-not-touch?'];
  if (unknownsForLayout(layout).length) questions.push('Which missing measurements can be verified on site?');
  return questions;
}

function runAccessibilityReview() {
  setJourney('accessibility');
  S.project.journey_details.accessibility = {
    profile: $('access-profile').value,
    needs: $('access-needs').value.trim(),
  };
  const report = regenerateValidation();
  report.title = 'Home Accessibility Planning Review';
  report.fix_list = groupedFixList(report);
  report.quick_wins = report.warnings.filter((item) => ['trip_hazard', 'lighting_recommendation'].includes(item.code));
  report.ask_a_professional = report.warnings.filter((item) => ['doorway_width', 'turning_circle', 'toilet_transfer', 'shower_access'].includes(item.code));
  report.caregiver_routes = ['caregiver-assisted bedroom to bathroom route', 'caregiver-assisted entry to living route'];
  report.night_route = 'night route from bed to bathroom';
  report.bathroom_safety_checklist = ['walk-in shower label', 'grab bar locations', 'non-slip surface', 'door swing direction'];
  renderValidation(report);
  scheduleAutosave();
}

function groupedFixList(report) {
  const groups = { move_furniture: [], remove_hazard: [], change_product: [], renovate: [], verify_on_site: [] };
  for (const item of report.warnings) {
    if (['path_clearance', 'bed_transfer', 'kitchen_reach_access'].includes(item.code)) groups.move_furniture.push(item);
    else if (item.code === 'trip_hazard') groups.remove_hazard.push(item);
    else if (['doorway_width', 'turning_circle', 'toilet_transfer', 'shower_access'].includes(item.code)) groups.renovate.push(item);
    else if (item.code === 'missing_measurements') groups.verify_on_site.push(item);
    else groups.change_product.push(item);
  }
  return groups;
}

function draftDesignerBrief() {
  setJourney('designer');
  const text = $('designer-intake').value.trim();
  const scenario = makeScenario('Designer pre-sales brief', 'designer', currentLayout(), 'draft');
  scenario.summary = text || 'Client needs, spatial risks, likely scope, and follow-up questions captured for pre-sales.';
  scenario.client_safe = true;
  S.project.scenarios.push(scenario);
  S.activeScenarioId = scenario.id;
  captureVersion(S.project, 'draft', S.project.layout, 'Drafted designer pre-sales brief');
  renderProject();
}

function addManualProduct() {
  setJourney('furniture_fit');
  const product = {
    id: uid('product'),
    name: $('product-name').value.trim() || 'Manual product',
    width_m: numberValue('product-width', 1.2),
    depth_m: numberValue('product-depth', 0.6),
    height_m: numberValue('product-height', 0.75),
    clearance_need_m: 0.6,
    orientation: 'either',
    source_url: $('product-url').value.trim(),
    source_confidence: $('product-url').value.trim() ? 'user_entered_url' : 'manual',
    last_checked_date: new Date().toISOString().slice(0, 10),
    price: null,
    fit_status: 'unchecked',
  };
  S.project.products.push(product);
  scheduleAutosave();
  renderProducts();
}

function checkActiveProductFit() {
  const product = S.project.products[S.project.products.length - 1];
  if (!product) return;
  const result = fitProduct(product, currentLayout());
  product.fit_status = result.status;
  product.fit_notes = result;
  if (result.status === 'fails') product.substitutes = suggestSubstitutes(product);
  renderProducts();
  scheduleAutosave();
}

function fitProduct(product, layout) {
  const bounds = layoutBounds(layout);
  const orientations = [[product.width_m, product.depth_m, '0deg'], [product.depth_m, product.width_m, '90deg']];
  const usable = orientations.filter(([w, d]) => w + product.clearance_need_m * 2 <= bounds.width && d + product.clearance_need_m * 2 <= bounds.depth);
  const warningText = unknownsForLayout(layout).length || ['unknown', 'estimated'].includes(product.source_confidence) ? 'Buy nothing yet: confirm scale, doorway width, and product dimensions first.' : '';
  return {
    status: usable.length ? 'fits' : 'fails',
    clearance_m: product.clearance_need_m,
    usable_orientations: usable.map((item) => item[2]),
    all_orientations: orientations.map((item) => item[2]),
    door_swing: 'check door swing overlay',
    walkway: usable.length ? 'clear' : 'at risk',
    delivery_path: ['entry door', 'corridor', 'bedroom door', 'elevator placeholder', 'stair placeholder'],
    warning: warningText,
  };
}

function suggestSubstitutes(product) {
  return commonProducts().filter((item) => item.category === (product.category || 'sofa') && (item.width_m < product.width_m || item.depth_m < product.depth_m)).slice(0, 3);
}

function commonProducts() {
  return [
    { id: 'fixture-queen-bed', name: 'Queen bed', category: 'bed', width_m: 1.52, depth_m: 2.03, height_m: 0.6 },
    { id: 'fixture-single-bed', name: 'Single bed', category: 'bed', width_m: 0.91, depth_m: 1.91, height_m: 0.55 },
    { id: 'fixture-sofa', name: 'Compact sofa', category: 'sofa', width_m: 1.8, depth_m: 0.82, height_m: 0.85 },
    { id: 'fixture-desk', name: 'Desk', category: 'desk', width_m: 1.2, depth_m: 0.6, height_m: 0.75 },
    { id: 'fixture-wardrobe', name: 'Wardrobe', category: 'wardrobe', width_m: 1.2, depth_m: 0.6, height_m: 2.0 },
    { id: 'fixture-dining-table', name: 'Dining table', category: 'table', width_m: 1.4, depth_m: 0.8, height_m: 0.75 },
    { id: 'fixture-storage-shelf', name: 'Storage shelf', category: 'storage', width_m: 0.8, depth_m: 0.35, height_m: 1.8 },
  ];
}

function renderProducts() {
  const root = $('product-results');
  if (!root) return;
  root.innerHTML = '';
  for (const product of S.project.products || []) {
    const card = document.createElement('div');
    card.className = 'product-card';
    const notes = product.fit_notes ? `<span>${esc(product.fit_notes.walkway)} · ${esc(product.fit_notes.usable_orientations.join(', ') || 'no orientation')}</span>` : '';
    const warningText = product.fit_notes?.warning ? `<em>${esc(product.fit_notes.warning)}</em>` : '';
    const substitutes = product.substitutes?.length ? `<span>Substitutes: ${product.substitutes.map((item) => esc(item.name)).join(', ')}</span>` : '';
    card.innerHTML = `<strong>${esc(product.name)}</strong><span>${product.width_m.toFixed(2)} x ${product.depth_m.toFixed(2)} x ${product.height_m.toFixed(2)}m</span><span>${esc(product.source_url || product.source_confidence)}</span><span>${esc(product.fit_status || 'unchecked')}</span>${notes}${warningText}${substitutes}`;
    root.appendChild(card);
  }
}

function exportShoppingList() {
  const lines = ['Product,Width m,Depth m,Height m,Quantity,Source URL,Fit notes'];
  for (const product of S.project.products || []) {
    lines.push([product.name, product.width_m.toFixed(2), product.depth_m.toFixed(2), product.height_m.toFixed(2), product.quantity || 1, product.source_url || '', product.fit_status || 'unchecked'].map(csv).join(','));
  }
  S.project.shopping_list_csv = lines.join('\n');
  downloadText(S.project.shopping_list_csv, `${slug(S.project.title)}-shopping-list.csv`, 'text/csv');
  S.project.exports.push({ kind: 'shopping_list_csv', filename: `${slug(S.project.title)}-shopping-list.csv`, created_at: nowIso(), disclaimer: PRODUCT_DISCLAIMER });
  scheduleAutosave();
}

function startCalibrationWizard() {
  calibrationClicks = [];
  setAutosave('Click two points on the plan for the known-length segment.');
  S.renderer.domElement.addEventListener('click', collectCalibrationPoint, { once: true });
}

function collectCalibrationPoint(event) {
  calibrationClicks.push({ x: event.clientX, y: event.clientY });
  if (calibrationClicks.length < 2) {
    setAutosave('Click the second calibration point.');
    S.renderer.domElement.addEventListener('click', collectCalibrationPoint, { once: true });
    return;
  }
  const [a, b] = calibrationClicks;
  const px = Math.hypot(a.x - b.x, a.y - b.y);
  const meters = numberValue('floorplan-known-m', 1);
  applyCalibration(px, meters, true, 'drawn_segment');
}

function recalibrateFromInputs() {
  const px = numberValue('floorplan-known-px', 0);
  const meters = numberValue('floorplan-known-m', 0);
  if (!px || !meters) {
    setAutosave('Enter known px and known meters before recalibrating.');
    return;
  }
  applyCalibration(px, meters, true, 'manual_recalibration');
}

function applyCalibration(px, meters, confirmed, source) {
  syncProjectFromLayout();
  const scale = meters / px;
  S.project.layout.metadata.calibration = { scale_m_per_px: scale, confidence: confirmed ? 'confirmed' : 'estimated', user_confirmed: confirmed, source };
  S.project.calibration = S.project.layout.metadata.calibration;
  captureVersion(S.project, 'revised', S.project.layout, 'Recalibrated without replacing objects');
  if (fn.applyLayoutData) fn.applyLayoutData(S.project.layout, { frame: false });
  regenerateValidation();
  setAutosave(`Scale ${scale.toFixed(5)} m/px`);
}

function openManualTracingTools() {
  $('sidebar')?.classList.add('open');
  $('manual-model-section')?.scrollIntoView({ block: 'nearest' });
  setAutosave('Manual tracing tools are ready.');
}

function traceRoomRectangle() {
  syncProjectFromLayout();
  const label = $('trace-room-label').value.trim() || `Room ${S.project.layout.rooms.length + 1}`;
  const count = S.project.layout.rooms.length;
  const x = count * 0.4;
  const room = {
    id: uid('room'),
    label,
    kind: label.toLowerCase().replace(/\s+/g, '_'),
    bounds: { x_min: x - 1.8, z_min: -1.4, x_max: x + 1.8, z_max: 1.4 },
    confidence: 'user_confirmed',
    source: 'manual_trace',
  };
  S.project.layout.rooms.push(room);
  if (fn.applyLayoutData) fn.applyLayoutData(S.project.layout, { frame: false });
  captureVersion(S.project, 'revised', S.project.layout, `Traced room ${label}`);
  scheduleAutosave();
  renderProject();
}

function addDoorOpening() {
  const width = numberValue('door-width', 0.8);
  const kind = $('door-kind').value;
  addLayoutMarker({
    type: kind === 'no_door' ? 'opening' : 'door',
    name: kind === 'no_door' ? 'No-door opening' : 'Door',
    width_m: width,
    swing_direction: kind,
    pos: [0, 1, 0],
    geo: [width, 2.0, 0.08],
    color: 0x7c3aed,
    confidence: 'user_entered',
  });
}

function addWindow() {
  const width = numberValue('window-width', 1.2);
  addLayoutMarker({
    type: 'window',
    name: 'Window',
    width_m: width,
    sill_height_m: numberValue('window-sill', 0.9),
    wall_association: $('window-wall').value.trim(),
    pos: [0, 1.2, 1],
    geo: [width, 1.0, 0.08],
    color: 0x38bdf8,
    confidence: 'user_entered',
  });
}

function addFixedElement() {
  const fixedType = $('fixed-element-type').value;
  addLayoutMarker({
    type: 'fixed_element',
    name: fixedType.replace(/_/g, ' '),
    fixed_type: fixedType,
    pos: [0.6, 0.5, 0.6],
    geo: fixedType === 'column' ? [0.35, 2.6, 0.35] : [0.8, 1.0, 0.6],
    color: 0xf59e0b,
    locked: true,
    do_not_touch: true,
    confidence: 'user_entered',
  });
}

function addLayoutMarker(item) {
  item.id = uid(item.type || 'item');
  item.rot = 0;
  item.visible = true;
  if (fn.addLayoutItem) fn.addLayoutItem(item);
  syncProjectFromLayout();
  captureVersion(S.project, 'revised', S.project.layout, `Added ${item.name || item.type}`);
  regenerateValidation();
}

function enter2dReview() {
  if (fn.setCameraView) fn.setCameraView('top');
  if (S.camera.fov !== 1 && fn.toggleOrtho) fn.toggleOrtho();
}

function enter3dWalkthrough() {
  if (fn.toggleFps && !S.fpsMode) fn.toggleFps();
}

function exportAnnotatedPng() {
  const report = S.validationReport || regenerateValidation();
  showValidationOverlay(report.overlays);
  S.renderer.render(S.scene, S.camera);
  const url = S.renderer.domElement.toDataURL('image/png');
  const a = document.createElement('a');
  const filename = `${slug(activeScenario()?.name || S.project.title)}-annotated.png`;
  a.href = url;
  a.download = filename;
  a.click();
  S.project.exports.push({ kind: 'annotated_png', filename, created_at: nowIso(), disclaimer: PRODUCT_DISCLAIMER });
  captureVersion(S.project, 'exported', S.project.layout, `Exported ${filename}`);
  scheduleAutosave();
}

function exportHtmlReport() {
  const report = S.validationReport || regenerateValidation();
  const include = {
    assumptions: $('report-assumptions').checked,
    warnings: $('report-warnings').checked,
    shopping: $('report-shopping').checked,
    scenarios: $('report-scenarios').checked,
    images: $('report-images').checked,
  };
  const title = esc(S.project.title || 'Haus Report');
  const parts = [
    '<!doctype html><html><head><meta charset="utf-8">',
    `<title>${title}</title>`,
    '<style>body{font-family:system-ui,sans-serif;margin:32px;line-height:1.45;color:#1f2937}h1,h2{color:#111827}.warning{border-left:4px solid #b45309;padding:8px 12px;background:#fffbeb}.serious,.blocked{border-left-color:#b91c1c;background:#fef2f2}.info{border-left-color:#2563eb;background:#eff6ff}@media print{button{display:none}body{margin:18mm}}</style>',
    '</head><body>',
    `<h1>${title}</h1>`,
    `<p>${esc(PRODUCT_DISCLAIMER)}</p>`,
  ];
  report.disclaimers.filter((item) => item !== PRODUCT_DISCLAIMER).forEach((item) => parts.push(`<p>${esc(item)}</p>`));
  if (include.assumptions) parts.push('<h2>Assumptions</h2><ul>', ...(S.project.assumptions.length ? S.project.assumptions : ['No assumptions entered.']).map((item) => `<li>${esc(item)}</li>`), '</ul>');
  if (include.warnings) parts.push('<h2>Warnings</h2>', ...report.warnings.map((item) => `<div class="warning ${esc(item.severity)}"><strong>${esc(item.message)}</strong><p>${esc(item.explanation)}</p><p>Suggested fix: ${esc(item.suggested_fix)}</p></div>`));
  if (include.scenarios) parts.push('<h2>Scenarios</h2><ul>', ...S.project.scenarios.map((item) => `<li>${esc(item.name)}: ${esc(item.status)} (${esc(String(item.score?.confidence ?? '-'))} confidence)</li>`), '</ul>');
  if (include.shopping && S.project.shopping_list_csv) parts.push('<h2>Shopping List</h2><pre>', esc(S.project.shopping_list_csv), '</pre>');
  if (include.images) parts.push('<h2>Images</h2><p>Attach exported annotated PNG snapshots for scenario visuals.</p>');
  parts.push('<button onclick="window.print()">Print / Save PDF</button></body></html>');
  const filename = `${slug(S.project.title)}-report.html`;
  downloadText(parts.join('\n'), filename, 'text/html');
  S.project.exports.push({ kind: 'html_report', filename, created_at: nowIso(), disclaimer: PRODUCT_DISCLAIMER });
  captureVersion(S.project, 'exported', S.project.layout, `Exported ${filename}`);
  scheduleAutosave();
}

function scenarioScore(layout, journey) {
  const report = validateLayout(layout, journey);
  const blocked = report.warnings.filter((item) => item.severity === 'blocked').length;
  const serious = report.warnings.filter((item) => item.severity === 'serious').length;
  const warn = report.warnings.filter((item) => item.severity === 'warning').length;
  const confidence = Math.max(0, Math.min(100, 100 - blocked * 30 - serious * 18 - warn * 8 - report.unknowns.length * 5));
  return {
    fit: Math.max(0, 100 - blocked * 35 - serious * 20 - warn * 10),
    circulation: Math.max(0, 100 - blocked * 40 - serious * 18 - warn * 8),
    accessibility: Math.max(0, 100 - blocked * 45 - serious * 20 - warn * 8),
    cost_complexity: Math.min(100, (layout.items || []).length * 3 + serious * 15 + warn * 8),
    confidence,
  };
}

function rectForItem(item) {
  const { w, d } = dimsForItem(item);
  const pos = item.pos || [0, 0, 0];
  return { x_min: pos[0] - w / 2, z_min: pos[2] - d / 2, x_max: pos[0] + w / 2, z_max: pos[2] + d / 2 };
}

function dimsForItem(item) {
  const geo = item.geo || [item.width_m || 1, item.height_m || 1, item.depth_m || 1];
  return { w: Number(geo[0] || 1), h: Number(geo[1] || 1), d: Number(geo[2] || 1) };
}

function rectsIntersect(a, b) {
  return !(a.x_max <= b.x_min || b.x_max <= a.x_min || a.z_max <= b.z_min || b.z_max <= a.z_min);
}

function rectGap(a, b) {
  const dx = Math.max(b.x_min - a.x_max, a.x_min - b.x_max, 0);
  const dz = Math.max(b.z_min - a.z_max, a.z_min - b.z_max, 0);
  return Math.hypot(dx, dz);
}

function unionRect(a, b) {
  return { x_min: Math.min(a.x_min, b.x_min), z_min: Math.min(a.z_min, b.z_min), x_max: Math.max(a.x_max, b.x_max), z_max: Math.max(a.z_max, b.z_max) };
}

function layoutBounds(layout) {
  const rects = (layout.items || []).map(rectForItem);
  (layout.rooms || []).forEach((room) => {
    if (room.bounds) rects.push({ x_min: room.bounds.x_min, z_min: room.bounds.z_min, x_max: room.bounds.x_max, z_max: room.bounds.z_max });
  });
  if (!rects.length) return { xMin: -2, zMin: -2, xMax: 2, zMax: 2, width: 4, depth: 4, minSide: 4 };
  const xMin = Math.min(...rects.map((rect) => rect.x_min));
  const zMin = Math.min(...rects.map((rect) => rect.z_min));
  const xMax = Math.max(...rects.map((rect) => rect.x_max));
  const zMax = Math.max(...rects.map((rect) => rect.z_max));
  return { xMin, zMin, xMax, zMax, width: xMax - xMin, depth: zMax - zMin, minSide: Math.min(xMax - xMin, zMax - zMin) };
}

function labelForItem(item) {
  return item.name || item.furnitureType || item.fixed_type || item.type || 'object';
}

function downloadText(text, filename, type) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function csv(value) {
  const text = String(value ?? '');
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function slug(text) {
  return String(text || 'haus').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'haus';
}

function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[ch]);
}
