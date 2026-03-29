// view router — toggles .view-panel elements by data-view attribute
// registered views: chat, settings, skills, automations, history, tasks, checkpoints,
// commands, workflows, tools, diagnostics, mission-control, context, git,
// timeline, memory, sessions, economy, instructions, prompt-library, qa-watch
const views = {};
let current = 'chat';
export function registerView(name, initFn) { views[name] = { initFn, initialized: false }; }
export function showView(name) {
  document.querySelectorAll('.view-panel').forEach(el => el.hidden = el.dataset.view !== name);
  if (views[name] && !views[name].initialized) {
    views[name].initFn();
    views[name].initialized = true;
  }
  current = name;
  document.querySelectorAll('.sidebar-nav-item').forEach(el => {
    el.classList.toggle('active', el.dataset.nav === name);
  });
}
export function currentView() { return current; }
