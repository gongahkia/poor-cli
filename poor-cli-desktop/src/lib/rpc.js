// rpc wrapper — centralizes invoke() calls with error handling
const { invoke } = window.__TAURI__.core;
export async function rpc(cmd, args = {}) {
  try { return await invoke(cmd, args); }
  catch (e) { console.error(`rpc ${cmd}:`, e); throw e; }
}
