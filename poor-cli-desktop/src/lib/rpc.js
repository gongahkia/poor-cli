// rpc wrapper — centralizes invoke() calls with error handling
const { invoke } = window.__TAURI__.core;
export async function rpc(cmd, args = {}) {
  console.debug(`[rpc:req] ${cmd}`, args);
  try {
    const result = await invoke(cmd, args);
    console.debug(`[rpc:res] ${cmd}`, typeof result === 'object' ? JSON.stringify(result).slice(0, 200) : result);
    return result;
  } catch (e) {
    console.error(`[rpc:err] ${cmd}:`, e);
    throw e;
  }
}
