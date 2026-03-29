// rpc wrapper — centralizes invoke() calls with error handling
//
// Error routing conventions:
// 1. User action fails → rpcNotify() + optionally addMessage()
// 2. Background refresh fails → rpcWarn()
// 3. View init fails → rpc() + catch renders fallback UI + console.warn
// 4. Cleanup/fire-and-forget → rpc().catch(e => console.warn(...))

import { notify } from './notifications.js';
const { invoke } = window.__TAURI__.core;

function summarizeArgs(args) { // truncated, redacts secrets
  if (!args || typeof args !== 'object') return '';
  const safe = {};
  for (const [k, v] of Object.entries(args)) {
    if (/key|token|secret|password/i.test(k)) { safe[k] = '***'; continue; }
    const s = typeof v === 'string' ? v : JSON.stringify(v);
    safe[k] = s && s.length > 60 ? s.slice(0, 57) + '...' : s;
  }
  const out = JSON.stringify(safe);
  return out.length > 200 ? out.slice(0, 197) + '...' : out;
}

function parseRpcError(e) { // extract code/message from JSON-RPC error strings
  const s = String(e);
  try {
    const obj = JSON.parse(s);
    return { code: obj.code, message: obj.message || s, data: obj.data };
  } catch { return { code: null, message: s, data: null }; }
}

class RpcError extends Error {
  constructor(method, args, durationMs, originalError) {
    const parsed = parseRpcError(originalError);
    super(parsed.message);
    this.name = 'RpcError';
    this.method = method;
    this.argsSummary = summarizeArgs(args);
    this.timestamp = new Date().toISOString();
    this.durationMs = Math.round(durationMs);
    this.code = parsed.code;
    this.errorData = parsed.data;
    this.originalError = originalError;
  }
  toDetail() {
    return {
      method: this.method,
      args: this.argsSummary,
      timestamp: this.timestamp,
      durationMs: this.durationMs,
      errorCode: this.code,
      errorData: this.errorData,
      errorMessage: this.message,
      stack: this.stack,
    };
  }
}

export async function rpc(cmd, args = {}) {
  const start = performance.now();
  console.debug(`[rpc:req] ${cmd}`, args);
  try {
    const result = await invoke(cmd, args);
    const ms = Math.round(performance.now() - start);
    console.debug(`[rpc:res] ${cmd} (${ms}ms)`, typeof result === 'object' ? JSON.stringify(result).slice(0, 200) : result);
    return result;
  } catch (e) {
    const ms = performance.now() - start;
    const err = new RpcError(cmd, args, ms, e);
    console.error(`[rpc:err] ${cmd} (${err.durationMs}ms):`, err.message, { code: err.code, args: err.argsSummary });
    throw err;
  }
}

export async function rpcNotify(cmd, args = {}, label) { // for user-initiated actions
  try { return await rpc(cmd, args); }
  catch (e) {
    notify({
      title: label || `${cmd} failed`,
      body: e.message || String(e),
      type: 'error',
      detail: e.toDetail ? e.toDetail() : { errorMessage: String(e), method: cmd, timestamp: new Date().toISOString() },
    });
    return null;
  }
}

export async function rpcWarn(cmd, args = {}) { // for background refreshes
  try { return await rpc(cmd, args); }
  catch (e) {
    notify({
      title: cmd,
      body: e.message || String(e),
      type: 'warning',
      detail: e.toDetail ? e.toDetail() : { errorMessage: String(e), method: cmd, timestamp: new Date().toISOString() },
    });
    return null;
  }
}
