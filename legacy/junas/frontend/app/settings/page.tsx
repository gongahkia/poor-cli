"use client";
import { useState, useEffect, useRef, useCallback } from "react";
import { listJurisdictions } from "../../lib/api-client";
import { LOCAL_MODELS } from "../../lib/ml/model-registry";
import { getAllModelStatus, downloadModel, deleteModel, deleteAllModels, clearAllSiteData, type ModelMeta } from "../../lib/ml/model-cache";
import { addNotification } from "../../lib/notification-store";
import { useTheme, COLOR_THEMES, type ColorTheme } from "../../lib/theme-provider";

const PROVIDERS = ["claude", "openai", "gemini", "ollama", "lmstudio"];
const PROVIDER_INFO: Record<string, { label: string; hint: string; local?: boolean }> = {
  claude: { label: "Claude", hint: "Anthropic API key" },
  openai: { label: "OpenAI", hint: "OpenAI API key" },
  gemini: { label: "Gemini", hint: "Google AI API key" },
  ollama: { label: "Ollama", hint: "Local — no key required", local: true },
  lmstudio: { label: "LM Studio", hint: "Local — no key required", local: true },
};

type Jurisdiction = { id: string; name: string; short_name: string; system_prompt_addition: string };
type Tab = "providers" | "server" | "local" | "display";
type ServerStatus = { services: Record<string, boolean> } | null;
type ServerMetrics = { uptime_seconds: number; models_loaded: string[]; benchmark_runs: number; conversations: number } | null;
type DownloadState = Record<string, { progress: number; abort?: AbortController }>;

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function SettingsPage() {
  const { colorTheme, darkMode, focusMode, setColorTheme, setDarkMode, setFocusMode } = useTheme();
  const [tab, setTab] = useState<Tab>("providers");
  // providers
  const [keys, setKeys] = useState<Record<string, string>>({});
  const [jurisdictions, setJurisdictions] = useState<Jurisdiction[]>([]);
  const [selectedJurisdiction, setSelectedJurisdiction] = useState("");
  // server
  const [serverStatus, setServerStatus] = useState<ServerStatus>(null);
  const [serverMetrics, setServerMetrics] = useState<ServerMetrics>(null);
  const [serverLoading, setServerLoading] = useState(false);
  const [serverError, setServerError] = useState("");
  // local models
  const [modelStatus, setModelStatus] = useState<{ model: typeof LOCAL_MODELS[0]; meta: ModelMeta | null }[]>([]);
  const [downloads, setDownloads] = useState<DownloadState>({});

  // init providers
  useEffect(() => {
    const loaded: Record<string, string> = {};
    PROVIDERS.forEach(p => { loaded[p] = localStorage.getItem(`junas_apikey_${p}`) || ""; });
    setKeys(loaded);
    setSelectedJurisdiction(localStorage.getItem("junas_jurisdiction") || "");
    listJurisdictions().then(d => setJurisdictions(Array.isArray(d) ? d : [])).catch(() => {});
  }, []);

  // init local models
  useEffect(() => { refreshLocalModels(); }, []);

  const refreshLocalModels = () => setModelStatus(getAllModelStatus());

  // fetch server status
  const fetchServer = useCallback(async () => {
    setServerLoading(true);
    setServerError("");
    try {
      const [readyResp, metricsResp] = await Promise.all([
        fetch(`${API}/api/v1/ready`).then(r => r.json()),
        fetch(`${API}/api/v1/metrics`).then(r => r.json()),
      ]);
      setServerStatus(readyResp);
      setServerMetrics(metricsResp);
    } catch (err: any) {
      setServerError(err.message || "Cannot reach backend");
    } finally { setServerLoading(false); }
  }, []);

  useEffect(() => { if (tab === "server") fetchServer(); }, [tab, fetchServer]);

  // save providers
  const saveProviders = () => {
    PROVIDERS.forEach(p => { if (keys[p]) localStorage.setItem(`junas_apikey_${p}`, keys[p]); else localStorage.removeItem(`junas_apikey_${p}`); });
    if (selectedJurisdiction) {
      localStorage.setItem("junas_jurisdiction", selectedJurisdiction);
      const j = jurisdictions.find(x => x.id === selectedJurisdiction);
      if (j?.system_prompt_addition) localStorage.setItem("junas_jurisdiction_prompt", j.system_prompt_addition);
      else localStorage.removeItem("junas_jurisdiction_prompt");
    } else {
      localStorage.removeItem("junas_jurisdiction");
      localStorage.removeItem("junas_jurisdiction_prompt");
    }
    addNotification("success", "Settings Saved", "API keys and jurisdiction updated.");
  };

  // model download
  const handleDownload = async (modelId: string) => {
    const model = LOCAL_MODELS.find(m => m.id === modelId);
    if (!model) return;
    const abort = new AbortController();
    setDownloads(prev => ({ ...prev, [modelId]: { progress: 0, abort } }));
    try {
      await downloadModel(model, pct => {
        setDownloads(prev => ({ ...prev, [modelId]: { ...prev[modelId], progress: pct } }));
      }, abort.signal);
      addNotification("success", "Model Ready", `${model.name} downloaded successfully.`);
      refreshLocalModels();
    } catch (err: any) {
      if (err.name !== "AbortError") addNotification("error", "Download Failed", `${model.name}: ${err.message}`);
    } finally {
      setDownloads(prev => { const n = { ...prev }; delete n[modelId]; return n; });
    }
  };

  const handleCancelDownload = (modelId: string) => {
    downloads[modelId]?.abort?.abort();
    setDownloads(prev => { const n = { ...prev }; delete n[modelId]; return n; });
  };

  const handleDeleteModel = async (modelId: string) => {
    await deleteModel(modelId);
    refreshLocalModels();
    addNotification("info", "Model Removed", `${LOCAL_MODELS.find(m => m.id === modelId)?.name} deleted.`);
  };

  const handleDeleteAll = async () => {
    await deleteAllModels();
    refreshLocalModels();
    addNotification("info", "All Models Removed", "Local model cache cleared.");
  };

  const handleClearSiteData = () => {
    if (!confirm("This will clear all saved data including conversations, API keys, and cached models. Continue?")) return;
    clearAllSiteData();
    addNotification("warning", "Site Data Cleared", "All local data has been removed.");
    setTimeout(() => window.location.reload(), 1000);
  };

  const formatUptime = (s: number) => {
    if (s < 60) return `${Math.floor(s)}s`;
    if (s < 3600) return `${Math.floor(s / 60)}m`;
    return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  };

  const formatBytes = (b: number) => {
    if (b < 1024) return `${b} B`;
    if (b < 1048576) return `${(b / 1024).toFixed(1)} KB`;
    return `${(b / 1048576).toFixed(1)} MB`;
  };

  return (
    <div>
      <h2 style={{ marginBottom: "0.25rem" }}>Settings</h2>
      <p className="meta-line" style={{ marginBottom: "1.25rem" }}>Manage API providers, monitor server models, and configure local ML inference.</p>

      {/* tabs */}
      <div style={{ display: "flex", gap: "0.15rem", marginBottom: "1.5rem", borderBottom: "1px solid #E7E5E4", paddingBottom: "0" }}>
        {([["providers", "Providers"], ["server", "Server Models"], ["local", "Local Models"], ["display", "Theme & Display"]] as const).map(([id, label]) => (
          <button key={id} type="button" onClick={() => setTab(id)}
            style={{
              padding: "0.5rem 1rem", border: "none", background: "none",
              fontFamily: "inherit", fontSize: "0.85rem", fontWeight: tab === id ? 600 : 400,
              color: tab === id ? "#1C1917" : "#78716C", cursor: "pointer",
              borderBottom: tab === id ? "2px solid #1C1917" : "2px solid transparent",
              marginBottom: "-1px", transition: "color 0.15s",
            }}>
            {label}
          </button>
        ))}
      </div>

      {/* === PROVIDERS TAB === */}
      {tab === "providers" && (
        <div style={{ maxWidth: "520px" }}>
          <p style={{ fontSize: "0.82rem", color: "#78716C", marginBottom: "1rem" }}>
            API keys are stored in your browser only — never sent to the server for storage.
          </p>

          <div style={{ display: "grid", gap: "0.15rem", marginBottom: "1rem" }}>
            <p style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#A8A29E", marginBottom: "0.25rem" }}>Cloud Providers</p>
            {PROVIDERS.filter(p => !PROVIDER_INFO[p].local).map(p => (
              <div key={p} style={{ marginBottom: "0.6rem" }}>
                <label style={{ fontSize: "0.82rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.2rem" }}>
                  {PROVIDER_INFO[p].label}
                  <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: keys[p] ? "#16A34A" : "#DC2626" }} />
                </label>
                <input type="password" value={keys[p] || ""} onChange={e => setKeys({ ...keys, [p]: e.target.value })}
                  placeholder={PROVIDER_INFO[p].hint} style={{
                    width: "100%", padding: "0.5rem 0.6rem", borderRadius: "0.5rem",
                    border: "1px solid #D6D3D1", fontFamily: "inherit", fontSize: "0.85rem", outline: "none",
                  }} />
              </div>
            ))}
          </div>

          <div style={{ display: "grid", gap: "0.15rem", marginBottom: "1rem" }}>
            <p style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#A8A29E", marginBottom: "0.25rem" }}>Local Providers</p>
            {PROVIDERS.filter(p => PROVIDER_INFO[p].local).map(p => (
              <div key={p} style={{ marginBottom: "0.6rem" }}>
                <label style={{ fontSize: "0.82rem", fontWeight: 600, display: "flex", alignItems: "center", gap: "0.35rem", marginBottom: "0.2rem" }}>
                  {PROVIDER_INFO[p].label}
                  <span style={{ width: "6px", height: "6px", borderRadius: "50%", background: "#16A34A" }} />
                </label>
                <input type="text" value={keys[p] || ""} onChange={e => setKeys({ ...keys, [p]: e.target.value })}
                  placeholder={PROVIDER_INFO[p].hint} style={{
                    width: "100%", padding: "0.5rem 0.6rem", borderRadius: "0.5rem",
                    border: "1px solid #D6D3D1", fontFamily: "inherit", fontSize: "0.85rem", outline: "none",
                  }} />
              </div>
            ))}
          </div>

          <div style={{ borderTop: "1px solid #E7E5E4", paddingTop: "1rem", marginBottom: "1rem" }}>
            <label style={{ fontSize: "0.82rem", fontWeight: 600, display: "block", marginBottom: "0.2rem" }}>Default Jurisdiction</label>
            <select value={selectedJurisdiction} onChange={e => setSelectedJurisdiction(e.target.value)} style={{
              width: "100%", padding: "0.5rem 0.6rem", borderRadius: "0.5rem",
              border: "1px solid #D6D3D1", fontFamily: "inherit", fontSize: "0.85rem", outline: "none",
            }}>
              <option value="">None (general)</option>
              {jurisdictions.map(j => <option key={j.id} value={j.id}>{j.name} ({j.short_name})</option>)}
            </select>
            <p style={{ fontSize: "0.72rem", color: "#A8A29E", marginTop: "0.25rem" }}>Sets a jurisdiction-specific system prompt for AI chat responses.</p>
          </div>

          <button type="button" onClick={saveProviders} style={{
            padding: "0.55rem 1.25rem", borderRadius: "0.5rem", border: "none",
            background: "#1C1917", color: "#FAFAF9", fontFamily: "inherit",
            fontSize: "0.85rem", fontWeight: 600, cursor: "pointer",
          }}>
            Save All
          </button>
        </div>
      )}

      {/* === SERVER MODELS TAB === */}
      {tab === "server" && (
        <div style={{ maxWidth: "640px" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: "1rem" }}>
            <p style={{ fontSize: "0.82rem", color: "#78716C", margin: 0 }}>
              Models running on the backend at <code style={{ fontSize: "0.78rem", background: "#F5F5F4", padding: "0.1rem 0.3rem", borderRadius: "0.2rem" }}>{API}</code>
            </p>
            <button type="button" onClick={fetchServer} disabled={serverLoading} style={{
              padding: "0.35rem 0.7rem", borderRadius: "0.4rem", border: "1px solid #E7E5E4",
              background: "#FFFFFF", color: "#57534E", fontSize: "0.78rem", fontWeight: 500,
              cursor: serverLoading ? "not-allowed" : "pointer", fontFamily: "inherit",
            }}>
              {serverLoading ? "Checking..." : "Refresh"}
            </button>
          </div>

          {serverError && (
            <div style={{ padding: "0.75rem 1rem", background: "#FEF2F2", border: "1px solid #FECACA", borderRadius: "0.5rem", marginBottom: "1rem", fontSize: "0.82rem", color: "#991B1B" }}>
              Backend unreachable: {serverError}
            </div>
          )}

          {serverStatus && (
            <>
              <p style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#A8A29E", marginBottom: "0.5rem" }}>Services</p>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: "0.5rem", marginBottom: "1.25rem" }}>
                {Object.entries(serverStatus.services).map(([name, healthy]) => (
                  <div key={name} className="result-card" style={{ padding: "0.6rem 0.75rem", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: "0.82rem", fontWeight: 500 }}>{name}</span>
                    <span style={{ width: "0.6rem", height: "0.6rem", borderRadius: "50%", background: healthy ? "#16A34A" : "#DC2626", flexShrink: 0 }} />
                  </div>
                ))}
              </div>
            </>
          )}

          {serverMetrics && (
            <>
              <div style={{ display: "flex", gap: "0.75rem", marginBottom: "1.25rem", flexWrap: "wrap" }}>
                <div className="result-card" style={{ padding: "0.6rem 0.75rem", flex: "1 1 120px" }}>
                  <div style={{ fontSize: "0.68rem", fontWeight: 600, textTransform: "uppercase", color: "#A8A29E", marginBottom: "0.15rem" }}>Uptime</div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{formatUptime(serverMetrics.uptime_seconds)}</div>
                </div>
                <div className="result-card" style={{ padding: "0.6rem 0.75rem", flex: "1 1 120px" }}>
                  <div style={{ fontSize: "0.68rem", fontWeight: 600, textTransform: "uppercase", color: "#A8A29E", marginBottom: "0.15rem" }}>Benchmark Runs</div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{serverMetrics.benchmark_runs}</div>
                </div>
                <div className="result-card" style={{ padding: "0.6rem 0.75rem", flex: "1 1 120px" }}>
                  <div style={{ fontSize: "0.68rem", fontWeight: 600, textTransform: "uppercase", color: "#A8A29E", marginBottom: "0.15rem" }}>Conversations</div>
                  <div style={{ fontSize: "1.1rem", fontWeight: 700 }}>{serverMetrics.conversations}</div>
                </div>
              </div>

              <p style={{ fontSize: "0.72rem", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.06em", color: "#A8A29E", marginBottom: "0.5rem" }}>Models Loaded</p>
              {serverMetrics.models_loaded.length === 0 ? (
                <p className="meta-line">No models loaded.</p>
              ) : (
                <div style={{ display: "grid", gap: "0.4rem" }}>
                  {serverMetrics.models_loaded.map(name => (
                    <div key={name} className="result-card" style={{ padding: "0.55rem 0.75rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
                      <span style={{ width: "0.5rem", height: "0.5rem", borderRadius: "50%", background: "#16A34A", flexShrink: 0 }} />
                      <span style={{ fontSize: "0.85rem", fontWeight: 500 }}>{name}</span>
                      <span style={{ marginLeft: "auto", fontSize: "0.68rem", fontWeight: 600, color: "#16A34A", textTransform: "uppercase" }}>Ready</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {!serverStatus && !serverError && !serverLoading && (
            <p className="meta-line">Click &ldquo;Refresh&rdquo; to check backend status.</p>
          )}
        </div>
      )}

      {/* === LOCAL MODELS TAB === */}
      {tab === "local" && (
        <div style={{ maxWidth: "640px" }}>
          <p style={{ fontSize: "0.82rem", color: "#78716C", marginBottom: "0.25rem" }}>
            Download local ML models for offline processing.
          </p>
          <p style={{ fontSize: "0.82rem", color: "#78716C", marginBottom: "1.25rem" }}>
            Models are powered by ONNX Runtime and run entirely in your browser.
          </p>

          <div style={{ display: "grid", gap: "0.6rem", marginBottom: "1.5rem" }}>
            {modelStatus.map(({ model, meta }) => {
              const dl = downloads[model.id];
              const isDownloading = !!dl;
              const isReady = !!meta;
              return (
                <div key={model.id} className="result-card" style={{ padding: "0.75rem 1rem" }}>
                  <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
                    <div>
                      <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.2rem" }}>
                        <span style={{ fontSize: "0.92rem", fontWeight: 600 }}>{model.name}</span>
                        <span style={{ fontSize: "0.72rem", color: "#A8A29E" }}>{model.size}</span>
                        {isReady && (
                          <span style={{ fontSize: "0.62rem", fontWeight: 700, textTransform: "uppercase", padding: "0.1rem 0.35rem", borderRadius: "0.2rem", background: "#F0FDF4", color: "#16A34A" }}>
                            Ready
                          </span>
                        )}
                      </div>
                      <p style={{ fontSize: "0.78rem", color: "#78716C", margin: 0 }}>{model.description}</p>
                      {meta && (
                        <p style={{ fontSize: "0.68rem", color: "#A8A29E", margin: "0.2rem 0 0" }}>
                          {formatBytes(meta.sizeBytes)} cached · downloaded {new Date(meta.downloadedAt).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: "0.35rem", flexShrink: 0 }}>
                      {!isReady && !isDownloading && (
                        <button type="button" onClick={() => handleDownload(model.id)} style={{
                          padding: "0.35rem 0.7rem", borderRadius: "0.4rem", border: "none",
                          background: "#1C1917", color: "#FAFAF9", fontSize: "0.78rem",
                          fontWeight: 600, cursor: "pointer", fontFamily: "inherit",
                        }}>
                          Download
                        </button>
                      )}
                      {isDownloading && (
                        <button type="button" onClick={() => handleCancelDownload(model.id)} style={{
                          padding: "0.35rem 0.7rem", borderRadius: "0.4rem",
                          border: "1px solid #EF4444", background: "transparent",
                          color: "#EF4444", fontSize: "0.78rem", fontWeight: 500,
                          cursor: "pointer", fontFamily: "inherit",
                        }}>
                          Cancel
                        </button>
                      )}
                      {isReady && (
                        <button type="button" onClick={() => handleDeleteModel(model.id)} title="Delete model" style={{
                          padding: "0.35rem 0.5rem", borderRadius: "0.4rem",
                          border: "1px solid #FECACA", background: "transparent",
                          color: "#EF4444", fontSize: "0.9rem", cursor: "pointer", lineHeight: 1,
                        }}>
                          &#x1F5D1;
                        </button>
                      )}
                    </div>
                  </div>
                  {/* download progress */}
                  {isDownloading && (
                    <div style={{ marginTop: "0.5rem" }}>
                      <div style={{ width: "100%", height: "4px", borderRadius: "2px", background: "#E7E5E4", overflow: "hidden" }}>
                        <div style={{ height: "100%", borderRadius: "2px", background: "#1C1917", width: `${Math.round(dl.progress * 100)}%`, transition: "width 0.3s ease" }} />
                      </div>
                      <p style={{ fontSize: "0.68rem", color: "#A8A29E", marginTop: "0.2rem" }}>{Math.round(dl.progress * 100)}% downloaded</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div style={{ display: "flex", gap: "0.5rem", paddingTop: "0.75rem", borderTop: "1px solid #E7E5E4" }}>
            <button type="button" onClick={handleDeleteAll} style={{
              padding: "0.45rem 0.9rem", borderRadius: "0.5rem",
              border: "1px solid #FECACA", background: "transparent",
              color: "#EF4444", fontSize: "0.82rem", fontWeight: 500,
              cursor: "pointer", fontFamily: "inherit",
            }}>
              Delete All Models
            </button>
            <button type="button" onClick={handleClearSiteData} style={{
              padding: "0.45rem 0.9rem", borderRadius: "0.5rem",
              border: "1px solid #FECACA", background: "transparent",
              color: "#EF4444", fontSize: "0.82rem", fontWeight: 500,
              cursor: "pointer", fontFamily: "inherit", marginLeft: "auto",
            }}>
              Clear All Site Data
            </button>
          </div>
        </div>
      )}

      {/* === THEME & DISPLAY TAB === */}
      {tab === "display" && (
        <div style={{ maxWidth: "520px" }}>
          {/* color theme */}
          <div style={{ marginBottom: "1.5rem" }}>
            <label style={{ fontSize: "0.92rem", fontWeight: 700, display: "block", marginBottom: "0.5rem" }}>Color Theme</label>
            <select value={colorTheme} onChange={e => setColorTheme(e.target.value as ColorTheme)} style={{
              width: "100%", maxWidth: "280px", padding: "0.55rem 0.7rem", borderRadius: "0.5rem",
              border: "1px solid #D6D3D1", fontFamily: "inherit", fontSize: "0.88rem", outline: "none",
            }}>
              {COLOR_THEMES.map(t => <option key={t.id} value={t.id}>{t.label}</option>)}
            </select>
          </div>

          <div style={{ borderTop: "1px solid #E7E5E4", paddingTop: "1.25rem", marginBottom: "1.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <label style={{ fontSize: "0.92rem", fontWeight: 700, display: "block" }}>Dark Mode</label>
                <p className="meta-line" style={{ fontSize: "0.78rem", margin: "0.15rem 0 0" }}>
                  {darkMode === "dark" ? "Dark theme enabled" : darkMode === "system" ? "Following system preference" : "Light theme enabled"}
                </p>
              </div>
              <button type="button" onClick={() => setDarkMode(darkMode === "dark" ? "light" : "dark")} style={{
                width: "44px", height: "24px", borderRadius: "12px", border: "none", cursor: "pointer",
                background: darkMode === "dark" ? "#1C1917" : "#D6D3D1", position: "relative", transition: "background 0.2s",
              }}>
                <span style={{
                  position: "absolute", top: "2px",
                  left: darkMode === "dark" ? "22px" : "2px",
                  width: "20px", height: "20px", borderRadius: "50%",
                  background: "#FFFFFF", transition: "left 0.2s",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                }} />
              </button>
            </div>
          </div>

          <div style={{ borderTop: "1px solid #E7E5E4", paddingTop: "1.25rem", marginBottom: "1.5rem" }}>
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <div>
                <label style={{ fontSize: "0.92rem", fontWeight: 700, display: "block" }}>Focus Mode</label>
                <p className="meta-line" style={{ fontSize: "0.78rem", margin: "0.15rem 0 0" }}>
                  {focusMode ? "Zen view — sidebar hidden" : "Standard UI view"}
                </p>
              </div>
              <button type="button" onClick={() => setFocusMode(!focusMode)} style={{
                width: "44px", height: "24px", borderRadius: "12px", border: "none", cursor: "pointer",
                background: focusMode ? "#1C1917" : "#D6D3D1", position: "relative", transition: "background 0.2s",
              }}>
                <span style={{
                  position: "absolute", top: "2px",
                  left: focusMode ? "22px" : "2px",
                  width: "20px", height: "20px", borderRadius: "50%",
                  background: "#FFFFFF", transition: "left 0.2s",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                }} />
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
