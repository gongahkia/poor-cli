<script lang="ts">
  import {
    Bot,
    Box,
    ChevronLeft,
    ChevronRight,
    Download,
    Eraser,
    Eye,
    Grid3X3,
    Image,
    Loader2,
    Lock,
    Maximize,
    Moon,
    MousePointer2,
    Ruler,
    Save,
    Search,
    Send,
    Sun,
    Trash2,
    Upload,
    Wand2,
  } from '@lucide/svelte';
  import SceneCanvas from './lib/SceneCanvas.svelte';
  import {
    applyPlan,
    catalogLayoutItem,
    confirmTool,
    dispatchTool,
    downloadPlanReport,
    getChatStatus,
    getToolCatalog,
    searchCatalog,
    sendChat,
    syncLayout,
    vectorizeFloorPlan,
  } from './lib/api';
  import { FURNITURE, createFurniture, createWallBetween, layoutToSvg, normalizeLayout, roomLayout, sampleLayouts } from './lib/layout';
  import {
    appendTranscript,
    downloadBlob,
    exportProjectPackage,
    fileToDataUrl,
    importProjectPackage,
    listProjects,
    loadActiveProject,
    readSettings,
    saveProject,
    writeSettings,
  } from './lib/storage';
  import type {
    CatalogItem,
    ChatAction,
    ChatHistoryMessage,
    ChatStatus,
    LayoutData,
    LayoutItem,
    ProjectRecord,
    StoredKeys,
    ToolSpec,
  } from './lib/types';
  import { emptyLayout, withIds } from './lib/types';
  import { onMount } from 'svelte';

  type Mode = 'select' | 'draw_wall' | 'measure';

  const settingsDefaults = {
    provider: '',
    model: '',
    plannerMode: 'auto',
    standardsProfile: 'apartment_compact',
    disableWebSearch: false,
    showGrid: true,
    snap: true,
    collisions: true,
    gridSize: 0.25,
    shadows: true,
    wireframe: false,
    light: false,
  };

  let project: ProjectRecord = {
    id: 'loading',
    title: 'Untitled Haus Project',
    journey: 'blank',
    updatedAt: new Date().toISOString(),
    layout: emptyLayout(),
    transcript: [],
  };
  let projects: ProjectRecord[] = [];
  let status: ChatStatus | null = null;
  let settings = readSettings(settingsDefaults);
  let selectedId = '';
  let mode: Mode = 'select';
  let actionsOpen = false;
  let toolsOpen = false;
  let customModelEntry = false;
  let chatText = '';
  let chatHistory: ChatHistoryMessage[] = [];
  let sending = false;
  let statusLine = '';
  let errorLine = '';
  let attachmentInput: HTMLInputElement;
  let floorplanInput: HTMLInputElement;
  let jsonInput: HTMLInputElement;
  let glbInput: HTMLInputElement;
  let projectInput: HTMLInputElement;
  let sceneCanvas: any;
  let attachments: Array<{ name: string; mime_type: string; data_url: string }> = [];
  let apiKeys: StoredKeys = JSON.parse(localStorage.getItem('haus.api_keys') || '{}');
  let catalogQuery = '';
  let catalogRefresh = false;
  let catalogItems: CatalogItem[] = [];
  let catalogNote = '';
  let scalePx = '';
  let scaleM = '';
  let wallHeight = '2.6';
  let floorplanClean = true;
  let manualWidth = 3.6;
  let manualDepth = 3.2;
  let manualHeight = 2.6;
  let measureText = '';
  let webllmEngine: any = null;
  let webllmModel = '';
  let toolSpecs: ToolSpec[] = [];
  let webllmCacheBusy = false;
  let webllmCacheModel = '';
  let webllmCacheStatus = 'Not checked.';
  let webllmStorageStatus = 'Storage estimate unavailable.';
  let webllmCacheScopes = '';

  $: layout = project.layout;
  $: selectedItem = layout.items.find((item) => item.id === selectedId);
  $: providerSpecs = status?.providers || [];
  $: selectedProvider = settings.provider || preferredProvider();
  $: providerSpec = providerSpecs.find((provider) => provider.id === selectedProvider);
  $: modelPlaceholder = status?.default_models?.[selectedProvider] || 'provider default';
  $: localProvider = providerSpec?.requires_api_key === false;
  $: canUseProvider = Boolean(selectedProvider && (localProvider || apiKeys[selectedProvider] || status?.providers_with_env_keys?.includes(selectedProvider)));
  $: modelOptions = providerSpec?.models || [];
  $: selectedModelSpec = modelOptions.find((model) => model.id === settings.model);
  $: modelSelectValue = customModelEntry || Boolean(settings.model && modelOptions.length && !selectedModelSpec) ? '__custom__' : settings.model || '';
  $: allowCustomModel = providerSpec?.allow_custom_models !== false;
  $: showCustomModelInput = allowCustomModel && (!modelOptions.length || customModelEntry || Boolean(settings.model && modelOptions.length && !selectedModelSpec));
  $: browserRuntimeProvider = Boolean(providerSpec?.capabilities?.includes('browser_runtime'));
  $: plannerModes = Array.isArray(status?.capabilities?.planner_modes) ? status.capabilities.planner_modes as string[] : ['auto', 'deterministic', 'llm_reviewed', 'llm_structured'];
  $: standardsProfiles = Array.isArray(status?.capabilities?.standards_profiles) ? status.capabilities.standards_profiles as string[] : ['apartment_compact'];
  $: chatLoadingText = statusLine || 'Planning with tools...';
  $: if (toolsOpen && selectedProvider === 'webllm' && currentWebllmModel() !== webllmCacheModel && !webllmCacheBusy) {
    void refreshWebllmCache();
  }

  onMount(async () => {
    project = await loadActiveProject();
    projects = await listProjects();
    await refreshStatus();
    if (!settings.provider) {
      settings = { ...settings, provider: preferredProvider() };
      persistSettings();
    }
  });

  function persistSettings() {
    writeSettings(settings);
  }

  function selectProvider(value: string) {
    settings = { ...settings, provider: value, model: '' };
    customModelEntry = false;
    webllmCacheModel = '';
    persistSettings();
  }

  function selectModel(value: string) {
    customModelEntry = value === '__custom__';
    settings = { ...settings, model: value === '__custom__' ? '' : value };
    webllmCacheModel = '';
    persistSettings();
  }

  function setCustomModel(value: string) {
    customModelEntry = true;
    settings = { ...settings, model: value.trim() };
    webllmCacheModel = '';
    persistSettings();
  }

  async function saveCurrent(next: ProjectRecord = project) {
    project = await saveProject(next);
    projects = await listProjects();
  }

  function setLayout(layoutData: LayoutData) {
    project = { ...project, layout: withIds(layoutData) };
    void saveCurrent(project);
  }

  function updateItems(items: LayoutItem[]) {
    setLayout({ ...layout, items, _stamp: Date.now() });
  }

  function updateSelected(patch: Partial<LayoutItem>) {
    if (!selectedItem) return;
    updateItems(layout.items.map((item) => item.id === selectedId ? { ...item, ...patch } : item));
  }

  function addItem(item: LayoutItem) {
    updateItems([...layout.items, item]);
    selectedId = item.id || '';
  }

  function deleteSelected() {
    if (!selectedId) return;
    updateItems(layout.items.filter((item) => item.id !== selectedId));
    selectedId = '';
  }

  function preferredProvider() {
    const readyLocal = providerSpecs.find((provider) => provider.requires_api_key === false && provider.command_available !== false);
    if (readyLocal) return readyLocal.id;
    const envProvider = providerSpecs.find((provider) => status?.providers_with_env_keys?.includes(provider.id));
    return envProvider?.id || status?.supported_providers?.[0] || '';
  }

  async function refreshStatus() {
    try {
      status = await getChatStatus();
      errorLine = '';
    } catch (error) {
      errorLine = `API unavailable: ${(error as Error).message}`;
    }
  }

  async function newProject() {
    const next: ProjectRecord = {
      id: crypto.randomUUID?.() || `project-${Date.now().toString(16)}`,
      title: 'Untitled Haus Project',
      journey: 'blank',
      updatedAt: new Date().toISOString(),
      layout: emptyLayout(),
      transcript: [],
      assets: {},
    };
    await saveCurrent(next);
    selectedId = '';
    chatHistory = [];
  }

  async function openProject(id: string) {
    const found = projects.find((item) => item.id === id);
    if (!found) return;
    project = found;
    localStorage.setItem('haus.active_project_id', found.id);
    selectedId = '';
    chatHistory = found.transcript
      .filter((entry) => entry.role === 'user' || entry.role === 'assistant')
      .map((entry) => ({ role: entry.role as 'user' | 'assistant', content: entry.text }));
  }

  async function titleChanged(value: string) {
    await saveCurrent({ ...project, title: value || 'Untitled Haus Project' });
  }

  async function importJsonFile(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text());
      setLayout(normalizeLayout(parsed.layout || parsed));
      statusLine = `Loaded ${file.name}`;
    } catch (error) {
      errorLine = `JSON import failed: ${(error as Error).message}`;
    } finally {
      (event.currentTarget as HTMLInputElement).value = '';
    }
  }

  async function importProjectFile(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    try {
      project = await importProjectPackage(file);
      projects = await listProjects();
      selectedId = '';
      statusLine = `Imported ${project.title}`;
    } catch (error) {
      errorLine = `Project import failed: ${(error as Error).message}`;
    } finally {
      (event.currentTarget as HTMLInputElement).value = '';
    }
  }

  async function importGlbFile(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    try {
      await sceneCanvas?.loadGlb(file);
      statusLine = `Loaded ${file.name}`;
    } catch (error) {
      errorLine = `GLB import failed: ${(error as Error).message}`;
    } finally {
      (event.currentTarget as HTMLInputElement).value = '';
    }
  }

  async function runVectorize(event: Event) {
    const file = (event.currentTarget as HTMLInputElement).files?.[0];
    if (!file) return;
    statusLine = 'Vectorizing floor plan...';
    try {
      const result = await vectorizeFloorPlan(file, scalePx, scaleM, wallHeight, floorplanClean);
      setLayout(normalizeLayout(result.layout));
      const warnings = Array.isArray(result.warnings) && result.warnings.length > 0 ? ` ${result.warnings.join(' ')}` : '';
      statusLine = `Vectorized ${file.name}.${warnings}`;
    } catch (error) {
      errorLine = `Vectorization failed: ${(error as Error).message}`;
    } finally {
      (event.currentTarget as HTMLInputElement).value = '';
    }
  }

  async function addAttachment(event: Event) {
    const files = Array.from((event.currentTarget as HTMLInputElement).files || []);
    for (const file of files.slice(0, 3 - attachments.length)) {
      if (!file.type.startsWith('image/')) continue;
      attachments = [...attachments, { name: file.name, mime_type: file.type, data_url: await fileToDataUrl(file) }];
    }
    (event.currentTarget as HTMLInputElement).value = '';
  }

  function exportJson() {
    downloadBlob(new Blob([JSON.stringify(layout, null, 2)], { type: 'application/json' }), 'haus-layout.json');
  }

  function exportSvg() {
    downloadBlob(new Blob([layoutToSvg(layout)], { type: 'image/svg+xml' }), 'haus-layout.svg');
  }

  function applySample(value: string) {
    const sample = sampleLayouts()[value];
    if (sample) setLayout(sample);
  }

  async function buildManualRoom() {
    setLayout(roomLayout(manualWidth, manualDepth, manualHeight));
    statusLine = 'Manual room created.';
  }

  async function placeCatalog(itemId: string) {
    try {
      const response = await catalogLayoutItem(itemId);
      addItem(normalizeLayout({ version: 1, items: [response.layout_item as LayoutItem] }).items[0]);
      statusLine = 'Catalog item placed.';
    } catch (error) {
      errorLine = `Catalog place failed: ${(error as Error).message}`;
    }
  }

  async function runCatalogSearch() {
    if (!catalogQuery.trim()) return;
    catalogNote = 'Searching...';
    try {
      const response = await searchCatalog(catalogQuery, catalogRefresh);
      catalogItems = response.items || [];
      catalogNote = response.catalog?.fallback_used ? 'Live catalog unavailable; showing cached/seed items.' : `${catalogItems.length} catalog results`;
    } catch (error) {
      catalogNote = `Catalog failed: ${(error as Error).message}`;
    }
  }

  function saveKey() {
    if (!selectedProvider) return;
    const input = document.getElementById('provider-key') as HTMLInputElement | null;
    if (!input) return;
    const value = input.value.trim();
    if (value) apiKeys = { ...apiKeys, [selectedProvider]: value };
    else {
      const next = { ...apiKeys };
      delete next[selectedProvider];
      apiKeys = next;
    }
    localStorage.setItem('haus.api_keys', JSON.stringify(apiKeys));
    input.value = '';
  }

  function transcript(role: 'user' | 'assistant' | 'tool' | 'error', text: string) {
    project = appendTranscript(project, { role, text });
    void saveCurrent(project);
  }

  function chatPayload(message: string) {
    return {
      message,
      history: chatHistory,
      provider: selectedProvider,
      model: settings.model,
      api_key: apiKeys[selectedProvider] || '',
      planner_mode: settings.plannerMode,
      standards_profile: settings.standardsProfile,
      web_search_disabled: settings.disableWebSearch,
      attachments,
      project_context: {
        title: project.title,
        journey: project.journey,
        layout,
        selected_item_id: selectedId,
      },
    };
  }

  async function ensureScratchLayout() {
    await syncLayout(layout);
  }

  async function sendMessage() {
    const text = chatText.trim() || (attachments.length ? 'Use the attached image reference for this layout.' : '');
    if (!text || sending) return;
    sending = true;
    errorLine = '';
    chatText = '';
    const transcriptText = attachments.length ? `${text}\nAttached ${attachments.length} image reference${attachments.length === 1 ? '' : 's'}: ${attachments.map((item) => item.name).join(', ')}` : text;
    transcript('user', transcriptText);
    const payload = chatPayload(text);
    attachments = [];
    try {
      await ensureScratchLayout();
      const response = selectedProvider === 'webllm' ? await sendWebllm(payload) : await sendChat(payload);
      handleChatResponse(response);
    } catch (error) {
      const message = `Request failed: ${(error as Error).message}`;
      transcript('error', message);
      errorLine = message;
    } finally {
      sending = false;
    }
  }

  function handleChatResponse(response: any) {
    const text = response.response || response.result || '';
    if (text) transcript('assistant', text);
    chatHistory = Array.isArray(response.history)
      ? response.history
      : [...chatHistory, { role: 'assistant', content: text }];
    if (Array.isArray(response.actions)) {
      for (const action of response.actions as ChatAction[]) {
        transcript('tool', `${action.tool}: ${action.result}`);
        const resultJson = action.result_json;
        if (resultJson?.requires_confirmation) continue;
      }
    }
    if (response.request_id) statusLine = `Last request: ${response.request_id}`;
  }

  async function getWebllmEngine(model: string) {
    if (!navigator.gpu) throw new Error('WebLLM requires a WebGPU-capable browser.');
    if (webllmEngine && webllmModel === model) return webllmEngine;
    if (webllmEngine) await unloadWebllmEngine();
    statusLine = `Loading WebLLM ${model}...`;
    const webllm = await import('@mlc-ai/web-llm');
    webllmEngine = await webllm.CreateMLCEngine(model, {
      initProgressCallback: (progress: { text?: string; progress?: number }) => {
        statusLine = `${progress.text || 'Loading WebLLM'} ${Math.round((progress.progress || 0) * 100)}%`;
      },
    });
    webllmModel = model;
    return webllmEngine;
  }

  function currentWebllmModel() {
    return String(settings.model || status?.default_models?.webllm || 'Llama-3.1-8B-Instruct-q4f32_1-MLC');
  }

  function formatBytes(value?: number) {
    if (!Number.isFinite(value || NaN)) return 'unknown';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = Number(value);
    let unit = 0;
    while (size >= 1024 && unit < units.length - 1) {
      size /= 1024;
      unit += 1;
    }
    return `${size.toFixed(unit === 0 ? 0 : 1)} ${units[unit]}`;
  }

  async function refreshWebllmCache() {
    webllmCacheBusy = true;
    webllmCacheModel = currentWebllmModel();
    try {
      const estimate = await navigator.storage?.estimate?.();
      webllmStorageStatus = estimate ? `Site storage: ${formatBytes(estimate.usage)} / ${formatBytes(estimate.quota)}` : 'Storage estimate unavailable.';
      const cacheNames = 'caches' in window ? (await caches.keys()).filter((name) => name.startsWith('webllm/')) : [];
      let entryCount = 0;
      for (const name of cacheNames) {
        const cache = await caches.open(name);
        entryCount += (await cache.keys()).length;
      }
      webllmCacheScopes = cacheNames.length ? `${cacheNames.join(', ')} · ${entryCount} cached request${entryCount === 1 ? '' : 's'}` : 'No WebLLM CacheStorage scopes found.';
      const webllm = await import('@mlc-ai/web-llm');
      const cached = await webllm.hasModelInCache(webllmCacheModel);
      webllmCacheStatus = `${webllmCacheModel}: ${cached ? 'cached' : 'not cached'}`;
    } catch (error) {
      webllmCacheStatus = `Cache check failed: ${(error as Error).message}`;
    } finally {
      webllmCacheBusy = false;
    }
  }

  async function unloadWebllmEngine() {
    if (!webllmEngine) return;
    await webllmEngine.unload();
    webllmEngine = null;
    webllmModel = '';
    statusLine = 'WebLLM engine unloaded.';
  }

  async function loadCurrentWebllmModel() {
    webllmCacheBusy = true;
    try {
      const model = currentWebllmModel();
      await getWebllmEngine(model);
      statusLine = `Loaded WebLLM ${model}.`;
    } catch (error) {
      errorLine = `WebLLM load failed: ${(error as Error).message}`;
    } finally {
      webllmCacheBusy = false;
      await refreshWebllmCache();
    }
  }

  async function deleteCurrentWebllmCache() {
    if (!confirm(`Delete cached WebLLM files for ${currentWebllmModel()}?`)) return;
    webllmCacheBusy = true;
    try {
      const model = currentWebllmModel();
      await unloadWebllmEngine();
      const webllm = await import('@mlc-ai/web-llm');
      await webllm.deleteModelAllInfoInCache(model);
      statusLine = `Deleted WebLLM cache for ${model}.`;
    } catch (error) {
      errorLine = `WebLLM cache delete failed: ${(error as Error).message}`;
    } finally {
      webllmCacheBusy = false;
      await refreshWebllmCache();
    }
  }

  async function deleteAllWebllmCache() {
    if (!confirm('Delete all cached WebLLM files for this site?')) return;
    webllmCacheBusy = true;
    try {
      await unloadWebllmEngine();
      if ('caches' in window) {
        const names = (await caches.keys()).filter((name) => name.startsWith('webllm/'));
        await Promise.all(names.map((name) => caches.delete(name)));
      }
      statusLine = 'Deleted all WebLLM CacheStorage files.';
    } catch (error) {
      errorLine = `WebLLM cache delete failed: ${(error as Error).message}`;
    } finally {
      webllmCacheBusy = false;
      await refreshWebllmCache();
    }
  }

  function webllmMessages(payload: Record<string, unknown>): any[] {
    return [
      {
        role: 'system',
        content: [
          'You are running in-browser for Haus Planner.',
          'Use Haus tools for layout edits, validation, catalog, web references, and measurements.',
          'If native tools fail, return strict JSON {"tool_calls":[{"name":"tool","arguments":{}}],"response":""}.',
          `Project context: ${JSON.stringify(payload.project_context).slice(0, 9000)}`,
        ].join('\n'),
      },
      ...chatHistory.slice(-16).map((msg) => ({ role: msg.role, content: typeof msg.content === 'string' ? msg.content : JSON.stringify(msg.content) })),
      { role: 'user', content: String(payload.message || '') },
    ];
  }

  function jsonObject(text: string) {
    const source = String(text || '').trim().replace(/^```(?:json)?/i, '').replace(/```$/i, '').trim();
    for (let i = 0; i < source.length; i += 1) {
      if (source[i] !== '{') continue;
      let depth = 0;
      let quoted = false;
      let escaped = false;
      for (let j = i; j < source.length; j += 1) {
        const ch = source[j];
        if (quoted) {
          if (escaped) escaped = false;
          else if (ch === '\\') escaped = true;
          else if (ch === '"') quoted = false;
          continue;
        }
        if (ch === '"') quoted = true;
        else if (ch === '{') depth += 1;
        else if (ch === '}') {
          depth -= 1;
          if (depth === 0) {
            try { return JSON.parse(source.slice(i, j + 1)); } catch { break; }
          }
        }
      }
    }
    return null;
  }

  async function sendWebllm(payload: Record<string, unknown>) {
    const model = String(payload.model || status?.default_models?.webllm || 'Llama-3.1-8B-Instruct-q4f32_1-MLC');
    const engine = await getWebllmEngine(model);
    if (!toolSpecs.length) toolSpecs = await getToolCatalog();
    const messages = webllmMessages(payload);
    const actions: ChatAction[] = [];
    let responseText = '';
    for (let step = 0; step < 10; step += 1) {
      statusLine = step === 0 ? 'Planning with WebLLM tools...' : `Running WebLLM tool step ${step + 1}...`;
      const completion = await engine.chat.completions.create({
        messages,
        tools: toolSpecs.map((tool) => ({ type: 'function', function: { name: tool.name, description: tool.description || '', parameters: tool.parameters || { type: 'object', properties: {} } } })),
        temperature: 0.2,
        stream: false,
      });
      const message = completion.choices?.[0]?.message || {};
      const nativeCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
      const fallback = jsonObject(message.content || '');
      const fallbackCalls = Array.isArray(fallback?.tool_calls) ? fallback.tool_calls : [];
      const calls = nativeCalls.length ? nativeCalls.map((call: any) => ({
        id: call.id,
        name: call.function?.name,
        args: typeof call.function?.arguments === 'string' ? JSON.parse(call.function.arguments || '{}') : call.function?.arguments || {},
        native: true,
      })) : fallbackCalls.map((call: any, index: number) => ({ id: `json-${index}`, name: call.name || call.tool, args: call.arguments || call.args || {}, native: false }));
      if (!calls.length) {
        responseText = fallback?.response || fallback?.answer || message.content || '';
        break;
      }
      messages.push(nativeCalls.length ? { role: 'assistant', content: message.content || null, tool_calls: message.tool_calls } : { role: 'assistant', content: message.content || '' });
      const fallbackResults = [];
      for (const call of calls) {
        const result = await dispatchTool(call.name, call.args || {}, Boolean(payload.web_search_disabled));
        actions.push(...(result.actions || []));
        if (call.native) messages.push({ role: 'tool', tool_call_id: call.id, content: result.result || result.response || '' });
        else fallbackResults.push(`${call.name} -> ${result.result || result.response || ''}`);
      }
      if (fallbackResults.length) messages.push({ role: 'user', content: `Haus tool results:\n${fallbackResults.join('\n')}` });
    }
    return { response: responseText || 'WebLLM completed without a final answer.', history: chatHistory, actions, provider: 'webllm', model, request_id: 'webllm-browser' };
  }

  async function confirmAction(token: string) {
    try {
      await ensureScratchLayout();
      handleChatResponse(await confirmTool(token));
    } catch (error) {
      errorLine = `Confirm failed: ${(error as Error).message}`;
    }
  }

  async function applyPendingPlan(plan: Record<string, unknown>) {
    try {
      const response = await applyPlan(String(plan.id));
      if (Array.isArray(response.actions)) {
        for (const action of response.actions as ChatAction[]) transcript('tool', `${action.tool}: ${action.result}`);
      }
      await refreshStatus();
    } catch (error) {
      errorLine = `Apply plan failed: ${(error as Error).message}`;
    }
  }

  async function exportPlan(plan: Record<string, unknown>) {
    try {
      downloadBlob(new Blob([await downloadPlanReport(String(plan.id))], { type: 'text/markdown' }), `haus-concept-${plan.id}.md`);
    } catch (error) {
      errorLine = `Report failed: ${(error as Error).message}`;
    }
  }

  function moveSelected(id: string, x: number, z: number) {
    updateItems(layout.items.map((item) => item.id === id ? { ...item, pos: [x, item.pos[1], z] as [number, number, number] } : item));
  }

  function addWall(a: { x: number; z: number }, b: { x: number; z: number }) {
    addItem(createWallBetween(a, b, Number(wallHeight) || 2.6));
  }

  function exportProject() {
    void exportProjectPackage(project);
  }

  function localStatusText() {
    if (!selectedProvider) return 'Deterministic planner available.';
    if (providerSpec?.requires_api_key === false && providerSpec.command_available === false) return `${providerSpec.label} command not found.`;
    if (providerSpec?.requires_api_key === false) return `${providerSpec.label} available locally.`;
    if (apiKeys[selectedProvider] || status?.providers_with_env_keys?.includes(selectedProvider)) return `${providerSpec?.label || selectedProvider} configured.`;
    return 'Add a key or use deterministic planner prompts.';
  }
</script>

<div class:light={settings.light} class="app-shell">
  <aside id="chat-panel">
    <header class="chat-header">
      <div>
        <strong>Haus Planner</strong>
        <span>{project.title}</span>
      </div>
    </header>

    <div class="provider-grid">
      <select value={settings.provider} on:change={(event) => selectProvider((event.currentTarget as HTMLSelectElement).value)} id="chat-provider">
        {#each providerSpecs as provider}
          <option value={provider.id}>{provider.label}</option>
        {/each}
      </select>
      <select value={modelSelectValue} on:change={(event) => selectModel((event.currentTarget as HTMLSelectElement).value)} id="chat-model-select">
        <option value="">Auto ({modelPlaceholder})</option>
        {#each modelOptions as model}
          <option value={model.id} title={model.notes || model.id}>{model.label}</option>
        {/each}
        {#if allowCustomModel}
          <option value="__custom__">Custom model...</option>
        {/if}
      </select>
      {#if showCustomModelInput}
        <input value={settings.model} on:change={(event) => setCustomModel((event.currentTarget as HTMLInputElement).value)} id="chat-model" class="custom-model-input" placeholder="custom model id" />
      {/if}
      <select bind:value={settings.plannerMode} on:change={persistSettings} id="chat-planner-mode">
        {#each plannerModes as plannerMode}
          <option value={plannerMode}>{plannerMode.replace('_', ' ')}</option>
        {/each}
      </select>
      <select bind:value={settings.standardsProfile} on:change={persistSettings} id="chat-standards-profile">
        {#each standardsProfiles as profile}
          <option value={profile}>{profile.replace(/_/g, ' ')}</option>
        {/each}
      </select>
    </div>

    <form class="key-row" on:submit|preventDefault={saveKey}>
      <input id="provider-key" type="password" autocomplete="off" placeholder={localProvider ? 'No key required' : 'provider key'} disabled={localProvider} />
      <button type="submit">Save</button>
    </form>
    <label class="check-row"><input type="checkbox" bind:checked={settings.disableWebSearch} on:change={persistSettings} />Disable web search</label>
    <p class="status-text">{localStatusText()}</p>

    <div id="chat-messages">
      {#if project.transcript.length === 0}
        <div class="chat-msg chat-assistant">Upload a floor plan, create a manual room, or ask for a plan.</div>
      {/if}
      {#each project.transcript as msg}
        <div class={`chat-msg chat-${msg.role}`}>{msg.text}</div>
      {/each}
      {#if sending}
        <div class="chat-msg chat-loading"><Loader2 size={14} />{chatLoadingText}</div>
      {/if}
    </div>

    {#if attachments.length}
      <div class="attachments">
        {#each attachments as attachment}
          <span>{attachment.name}</span>
        {/each}
      </div>
    {/if}

    <div class="quick-prompts">
      <button type="button" on:click={() => chatText = 'Start with manual room dimensions'}>Start with manual room dimensions</button>
      <button type="button" on:click={() => chatText = 'Tell me what measurements are missing'}>Tell me what measurements are missing</button>
      <button type="button" on:click={() => chatText = 'Draft a concept plan for this layout'}>Draft a concept plan</button>
    </div>

    <footer class="chat-input-row">
      <input bind:this={attachmentInput} type="file" id="chat-image-input" accept="image/*" multiple hidden on:change={addAttachment} />
      <button type="button" on:click={() => attachmentInput.click()} title="Attach image"><Image size={18} /></button>
      <textarea bind:value={chatText} id="chat-input" rows="1" placeholder="Describe changes..." on:keydown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void sendMessage(); } }}></textarea>
      <button type="button" id="chat-send" on:click={sendMessage} disabled={sending || !canUseProvider && selectedProvider !== ''}><Send size={18} />Send</button>
    </footer>
  </aside>

  <button id="actions-toggle" type="button" on:click={() => actionsOpen = !actionsOpen}>
    {#if actionsOpen}<ChevronLeft size={18} />{:else}<ChevronRight size={18} />{/if}
    <span>Actions</span>
  </button>
  <nav id="toolbar" class:open={actionsOpen}>
    <button type="button" on:click={() => floorplanInput.click()}><Upload size={18} />Upload Plan</button>
    <button type="button" on:click={() => glbInput.click()}><Box size={18} />Load GLB</button>
    <select on:change={(event) => applySample((event.currentTarget as HTMLSelectElement).value)} aria-label="Sample layouts">
      <option value="">Sample layouts...</option>
      <option value="blank">Blank Project</option>
      <option value="compact">Compact Living</option>
      <option value="bedroom">Bedroom</option>
    </select>
    <button type="button" on:click={deleteSelected}><Trash2 size={18} />Delete</button>
    <button type="button" class:active={mode === 'draw_wall'} on:click={() => mode = mode === 'draw_wall' ? 'select' : 'draw_wall'}><Wand2 size={18} />Draw Wall</button>
    <button type="button" class:active={mode === 'measure'} on:click={() => mode = mode === 'measure' ? 'select' : 'measure'}><Ruler size={18} />Measure</button>
    <button type="button" on:click={() => sceneCanvas?.frame()}><Maximize size={18} />Frame</button>
    <button type="button" on:click={() => sceneCanvas?.screenshot()}><Image size={18} />Screenshot</button>
    <button type="button" on:click={() => sceneCanvas?.exportGlb()}><Download size={18} />Export GLB</button>
    <button type="button" on:click={exportJson}><Download size={18} />Export JSON</button>
    <button type="button" on:click={exportSvg}><Download size={18} />Export SVG</button>
    <button type="button" on:click={() => jsonInput.click()}><Upload size={18} />Load JSON</button>
    <button type="button" on:click={exportProject}><Save size={18} />Save Project</button>
    <button type="button" on:click={() => projectInput.click()}><Upload size={18} />Load Project</button>
    <button type="button" on:click={() => { settings.light = !settings.light; persistSettings(); }}>
      {#if settings.light}<Sun size={18} />{:else}<Moon size={18} />{/if}
      <span>{settings.light ? 'Dark' : 'Light'}</span>
    </button>
  </nav>

  <main id="workspace">
    <SceneCanvas
      bind:this={sceneCanvas}
      {layout}
      {selectedId}
      {mode}
      showGrid={settings.showGrid}
      wireframe={settings.wireframe}
      shadows={settings.shadows}
      gridSize={settings.snap ? settings.gridSize : 0.01}
      lightMode={settings.light}
      on:select={(event) => selectedId = event.detail}
      on:move={(event) => moveSelected(event.detail.id, event.detail.x, event.detail.z)}
      on:wall={(event) => addWall(event.detail.a, event.detail.b)}
      on:measure={(event) => measureText = `${event.detail.distance.toFixed(2)}m`}
      on:glb={(event) => updateItems([...layout.items, ...event.detail])}
    />
    <div class="hud">
      <span>{layout.items.length} items</span>
      {#if mode !== 'select'}<span>{mode.replace('_', ' ')}</span>{/if}
      {#if measureText}<span>{measureText}</span>{/if}
      {#if statusLine}<span>{statusLine}</span>{/if}
      {#if errorLine}<span class="err">{errorLine}</span>{/if}
    </div>
  </main>

  <button id="tools-toggle" type="button" on:click={() => toolsOpen = !toolsOpen}>
    {#if toolsOpen}<ChevronRight size={18} />{:else}<ChevronLeft size={18} />{/if}
    <span>Tools</span>
  </button>
  <aside id="sidebar" class:open={toolsOpen}>
    <section>
      <h3>Grid & Snap</h3>
      <label class="toggle-row">Show grid<input type="checkbox" bind:checked={settings.showGrid} on:change={persistSettings} /></label>
      <label class="toggle-row">Snap to grid<input type="checkbox" bind:checked={settings.snap} on:change={persistSettings} /></label>
      <label class="toggle-row">Collisions<input type="checkbox" bind:checked={settings.collisions} on:change={persistSettings} /></label>
      <label class="toggle-row">Grid size<input type="range" min="0.05" max="1" step="0.05" bind:value={settings.gridSize} on:change={persistSettings} /><span>{Number(settings.gridSize).toFixed(2)}m</span></label>
    </section>

    <section>
      <h3>View</h3>
      <label class="toggle-row">Wireframe<input type="checkbox" bind:checked={settings.wireframe} on:change={persistSettings} /></label>
      <label class="toggle-row">Shadows<input type="checkbox" bind:checked={settings.shadows} on:change={persistSettings} /></label>
    </section>

    {#if browserRuntimeProvider}
    <section>
      <h3>WebLLM Cache</h3>
      <p>{webllmCacheStatus}</p>
      <p>{webllmStorageStatus}</p>
      <p>{webllmCacheScopes}</p>
      <div class="button-grid">
        <button type="button" on:click={loadCurrentWebllmModel} disabled={webllmCacheBusy}><Bot size={16} />Load</button>
        <button type="button" on:click={refreshWebllmCache} disabled={webllmCacheBusy}>{#if webllmCacheBusy}<Loader2 size={16} />{:else}<Search size={16} />{/if}Refresh</button>
        <button type="button" on:click={unloadWebllmEngine} disabled={webllmCacheBusy || !webllmEngine}><Eraser size={16} />Unload</button>
      </div>
      <button type="button" class="danger-btn" on:click={deleteCurrentWebllmCache} disabled={webllmCacheBusy}><Trash2 size={16} />Delete Current Cache</button>
      <button type="button" class="danger-btn" on:click={deleteAllWebllmCache} disabled={webllmCacheBusy}><Trash2 size={16} />Delete All WebLLM</button>
    </section>
    {/if}

    <section>
      <h3>Project</h3>
      <input value={project.title} on:change={(event) => titleChanged((event.currentTarget as HTMLInputElement).value)} />
      <select value={project.id} on:change={(event) => openProject((event.currentTarget as HTMLSelectElement).value)}>
        {#each projects as item}
          <option value={item.id}>{item.title}</option>
        {/each}
      </select>
      <div class="button-grid">
        <button type="button" on:click={newProject}>Blank</button>
        <button type="button" on:click={exportProject}>Export</button>
      </div>
      <p>Autosaved {new Date(project.updatedAt).toLocaleTimeString()}</p>
    </section>

    <section>
      <h3>Manual Room</h3>
      <label class="field">Width <input type="number" bind:value={manualWidth} min="0.5" step="0.05" /> m</label>
      <label class="field">Depth <input type="number" bind:value={manualDepth} min="0.5" step="0.05" /> m</label>
      <label class="field">Height <input type="number" bind:value={manualHeight} min="1.8" step="0.05" /> m</label>
      <button type="button" on:click={buildManualRoom}>Build Room</button>
    </section>

    <section>
      <h3>Upload Floor Plan</h3>
      <button type="button" on:click={() => floorplanInput.click()}>Choose file</button>
      <label class="field">Known px <input type="number" bind:value={scalePx} placeholder="240" /> px</label>
      <label class="field">Known m <input type="number" bind:value={scaleM} placeholder="3.0" /> m</label>
      <label class="field">Wall h <input type="number" bind:value={wallHeight} min="1.8" max="8" step="0.1" /> m</label>
      <label class="toggle-row">Clean image<input type="checkbox" bind:checked={floorplanClean} /></label>
    </section>

    <section>
      <h3>Add Furniture</h3>
      <div class="button-grid">
        {#each Object.entries(FURNITURE) as [key, item]}
          <button type="button" on:click={() => addItem(createFurniture(key))}>{item.label}</button>
        {/each}
      </div>
    </section>

    <section>
      <h3>IKEA Catalog</h3>
      <div class="search-row">
        <input bind:value={catalogQuery} placeholder="sofa, desk, BILLY..." on:keydown={(event) => { if (event.key === 'Enter') void runCatalogSearch(); }} />
        <button type="button" on:click={runCatalogSearch}><Search size={16} /></button>
      </div>
      <label class="toggle-row">Live refresh<input type="checkbox" bind:checked={catalogRefresh} /></label>
      {#if catalogNote}<p>{catalogNote}</p>{/if}
      <div class="catalog-list">
        {#each catalogItems as item}
          <article>
            <strong>{item.name}</strong>
            <span>{item.category || 'catalog'} {item.price ? `· ${item.price}` : ''}</span>
            <button type="button" on:click={() => placeCatalog(item.id)}>Place</button>
          </article>
        {/each}
      </div>
    </section>

    <section>
      <h3>Selected</h3>
      {#if selectedItem}
        <strong>{selectedItem.name || selectedItem.type}</strong>
        <label class="field">X <input type="number" value={selectedItem.pos[0]} step="0.05" on:change={(event) => updateSelected({ pos: [Number((event.currentTarget as HTMLInputElement).value), selectedItem!.pos[1], selectedItem!.pos[2]] })} /></label>
        <label class="field">Z <input type="number" value={selectedItem.pos[2]} step="0.05" on:change={(event) => updateSelected({ pos: [selectedItem!.pos[0], selectedItem!.pos[1], Number((event.currentTarget as HTMLInputElement).value)] })} /></label>
        <label class="field">Rot <input type="number" value={Math.round((selectedItem.rot || 0) * 180 / Math.PI)} step="5" on:change={(event) => updateSelected({ rot: Number((event.currentTarget as HTMLInputElement).value) * Math.PI / 180 })} /> deg</label>
        <label class="toggle-row">Locked<input type="checkbox" checked={Boolean(selectedItem.locked)} on:change={(event) => updateSelected({ locked: (event.currentTarget as HTMLInputElement).checked })} /></label>
      {:else}
        <p>No selection.</p>
      {/if}
    </section>
  </aside>

  <input bind:this={floorplanInput} type="file" accept="image/png,image/jpeg,image/webp" hidden on:change={runVectorize} />
  <input bind:this={jsonInput} type="file" accept="application/json,.json" hidden on:change={importJsonFile} />
  <input bind:this={glbInput} type="file" accept=".glb,model/gltf-binary" hidden on:change={importGlbFile} />
  <input bind:this={projectInput} type="file" accept=".json,.gz,.haus.json,.haus.json.gz" hidden on:change={importProjectFile} />
</div>
