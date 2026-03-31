// memory management panel with knowledge-graph visualisation
import { rpc } from './rpc.js';
import { addMessage } from './app.js';

const GRAPH_WIDTH = 1000;
const GRAPH_HEIGHT = 360;
const MAX_GRAPH_EDGES = 120;
const STOP_WORDS = new Set([
  'the', 'and', 'for', 'from', 'this', 'that', 'with', 'have', 'into', 'your', 'you', 'our', 'their',
  'them', 'then', 'than', 'were', 'been', 'also', 'only', 'when', 'what', 'where', 'which', 'about',
  'will', 'would', 'should', 'could', 'while', 'after', 'before', 'under', 'over', 'per', 'each',
  'memory', 'value', 'key', 'true', 'false', 'null', 'none',
]);

const memoryState = {
  items: [],
  query: '',
  loadError: '',
};

const memoryUI = {
  searchInput: null,
  graph: null,
  graphStats: null,
  list: null,
};

export async function initMemory() {
  const container = document.getElementById('memory-content');
  if (!container) return;
  container.innerHTML = '';

  const searchInput = document.createElement('input');
  searchInput.type = 'text';
  searchInput.className = 'search-input';
  searchInput.placeholder = 'Search memory or graph nodes...';
  container.appendChild(searchInput);

  const saveForm = document.createElement('div');
  saveForm.className = 'mem-save-form';
  saveForm.innerHTML = `<input type="text" class="mem-input mem-key" id="memory-key-input" placeholder="Key" />`
    + `<input type="text" class="mem-input mem-val" id="memory-val-input" placeholder="Value" />`
    + `<button class="btn btn-sm btn-primary" id="memory-save-btn">Save</button>`;
  container.appendChild(saveForm);

  const graphCard = document.createElement('div');
  graphCard.className = 'item-card mem-graph-card';
  graphCard.innerHTML = `<div class="item-card-header">`
    + `<h3>Knowledge Graph</h3>`
    + `<span class="mem-graph-stats" id="memory-graph-stats"></span>`
    + `</div>`
    + `<div class="memory-graph" id="memory-graph"></div>`;
  container.appendChild(graphCard);

  const list = document.createElement('div');
  list.id = 'memory-list';
  list.className = 'item-list';
  container.appendChild(list);

  memoryUI.searchInput = searchInput;
  memoryUI.graph = graphCard.querySelector('#memory-graph');
  memoryUI.graphStats = graphCard.querySelector('#memory-graph-stats');
  memoryUI.list = list;

  searchInput.addEventListener('input', () => {
    memoryState.query = searchInput.value.trim().toLowerCase();
    renderMemory();
  });
  document.getElementById('memory-save-btn').onclick = saveMemory;

  await refreshMemory();
}

async function refreshMemory() {
  if (!memoryUI.list || !memoryUI.graph) return;
  try {
    const result = await rpc('get_config', {});
    memoryState.items = normaliseMemory(result.memory || result.memories || null);
    memoryState.loadError = '';
  } catch (e) {
    console.warn('[memory] get_config:', e);
    memoryState.items = [];
    memoryState.loadError = 'Memory unavailable — backend not connected';
  }
  renderMemory();
}

function renderMemory() {
  const { items, query, loadError } = memoryState;
  const { list, graph, graphStats } = memoryUI;
  if (!list || !graph || !graphStats) return;

  if (loadError) {
    list.innerHTML = `<div class="view-empty"><p>${esc(loadError)}</p></div>`;
    graph.innerHTML = `<div class="view-empty"><p>${esc(loadError)}</p></div>`;
    graphStats.textContent = '';
    return;
  }

  const filtered = filterItems(items, query);
  renderMemoryList(filtered, list);
  renderKnowledgeGraph(items, filtered, query, graph, graphStats);
}

function renderMemoryList(items, list) {
  list.innerHTML = '';
  if (!memoryState.items.length) {
    list.innerHTML = '<div class="view-empty"><p>No memories stored</p></div>';
    return;
  }
  if (!items.length) {
    list.innerHTML = '<div class="view-empty"><p>No results</p></div>';
    return;
  }
  items.forEach(m => renderMemoryItem(m, list));
}

function renderMemoryItem(m, list) {
  const card = document.createElement('div');
  card.className = 'item-card mem-item-card';
  card.dataset.memoryKey = m.key;
  card.innerHTML = `<div class="item-card-header">`
    + `<h3>${esc(m.key)}</h3>`
    + `<button class="btn btn-sm btn-danger mem-del-btn">Delete</button>`
    + `</div>`
    + `<pre class="mem-value">${esc(m.valueText)}</pre>`;
  card.querySelector('.mem-del-btn').onclick = async () => {
    if (!confirm(`Delete memory "${m.key}"?`)) return;
    try {
      await rpc('set_config', { key_path: `memory.${m.key}`, value: null });
      addMessage(`Memory "${m.key}" deleted.`, 'assistant');
      await refreshMemory();
    } catch (e) {
      addMessage(`Delete failed: ${e}`, 'assistant');
    }
  };
  list.appendChild(card);
}

function renderKnowledgeGraph(allItems, filteredItems, query, graphEl, statsEl) {
  if (!allItems.length) {
    graphEl.innerHTML = '<div class="view-empty"><p>No memory graph yet</p></div>';
    statsEl.textContent = '';
    return;
  }

  const matchedKeys = new Set(filteredItems.map(i => i.key));
  const { nodes, edges, degree } = buildGraph(allItems);
  const positions = computeNodePositions(nodes, degree);

  const lines = edges.map(edge => {
    const p1 = positions.get(edge.from);
    const p2 = positions.get(edge.to);
    if (!p1 || !p2) return '';
    const isMatch = matchedKeys.has(edge.from) && matchedKeys.has(edge.to);
    const classes = ['mem-edge'];
    if (query && !isMatch) classes.push('dim');
    if (query && isMatch) classes.push('match');
    const width = (0.8 + edge.weight * 0.65).toFixed(2);
    return `<line class="${classes.join(' ')}" x1="${p1.x.toFixed(2)}" y1="${p1.y.toFixed(2)}" x2="${p2.x.toFixed(2)}" y2="${p2.y.toFixed(2)}" stroke-width="${width}"></line>`;
  }).join('');

  const maxDegree = Math.max(1, ...Array.from(degree.values()));
  const nodeSvg = nodes.map(node => {
    const p = positions.get(node.key);
    if (!p) return '';
    const d = degree.get(node.key) || 0;
    const base = 18 + Math.min(8, (node.valueText.length || 0) / 120);
    const radius = Math.min(30, Math.max(base, 18 + (d / maxDegree) * 8));
    const nodeMatch = !query || matchedKeys.has(node.key);
    const classes = ['mem-node'];
    if (query && !nodeMatch) classes.push('dim');
    if (nodeMatch) classes.push('match');
    const label = truncate(node.key, 16);
    const tooltip = `${node.key}\n${truncate(node.valueText.replace(/\s+/g, ' '), 160)}`;
    return `<g class="${classes.join(' ')}" data-key="${escAttr(node.key)}" transform="translate(${p.x.toFixed(2)},${p.y.toFixed(2)})">`
      + `<circle r="${radius.toFixed(2)}"></circle>`
      + `<text y="4">${esc(label)}</text>`
      + `<title>${esc(tooltip)}</title>`
      + `</g>`;
  }).join('');

  graphEl.innerHTML = `<svg class="memory-graph-svg" viewBox="0 0 ${GRAPH_WIDTH} ${GRAPH_HEIGHT}" preserveAspectRatio="xMidYMid meet">`
    + lines
    + nodeSvg
    + `</svg>`;

  statsEl.textContent = `${filteredItems.length}/${allItems.length} nodes | ${edges.length} links`;

  graphEl.querySelectorAll('.mem-node').forEach(node => {
    node.addEventListener('click', () => focusMemoryNode(node.dataset.key || ''));
  });
}

function focusMemoryNode(key) {
  if (!key || !memoryUI.list) return;
  let cards = Array.from(memoryUI.list.querySelectorAll('.mem-item-card'));
  let target = cards.find(c => c.dataset.memoryKey === key);
  if (!target && memoryUI.searchInput) {
    memoryState.query = key.toLowerCase();
    memoryUI.searchInput.value = key;
    renderMemory();
    cards = Array.from(memoryUI.list.querySelectorAll('.mem-item-card'));
    target = cards.find(c => c.dataset.memoryKey === key);
  }
  if (!target) return;
  cards.forEach(c => c.classList.remove('selected'));
  target.classList.add('selected');
  target.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function buildGraph(items) {
  const nodes = items.map(item => ({
    key: item.key,
    valueText: item.valueText,
    tokens: tokenise(`${item.key} ${item.valueText}`),
  }));
  const allEdges = [];
  for (let i = 0; i < nodes.length; i += 1) {
    for (let j = i + 1; j < nodes.length; j += 1) {
      const shared = sharedTokenCount(nodes[i].tokens, nodes[j].tokens);
      if (shared > 0) {
        allEdges.push({
          from: nodes[i].key,
          to: nodes[j].key,
          weight: Math.min(4, shared),
        });
      }
    }
  }
  allEdges.sort((a, b) => b.weight - a.weight);
  const edges = allEdges.slice(0, MAX_GRAPH_EDGES);
  const degree = new Map(nodes.map(n => [n.key, 0]));
  edges.forEach(edge => {
    degree.set(edge.from, (degree.get(edge.from) || 0) + 1);
    degree.set(edge.to, (degree.get(edge.to) || 0) + 1);
  });
  return { nodes, edges, degree };
}

function computeNodePositions(nodes, degreeMap) {
  const positions = new Map();
  if (!nodes.length) return positions;
  const sorted = [...nodes].sort((a, b) => {
    const d = (degreeMap.get(b.key) || 0) - (degreeMap.get(a.key) || 0);
    if (d !== 0) return d;
    return a.key.localeCompare(b.key);
  });
  const centerX = GRAPH_WIDTH / 2;
  const centerY = GRAPH_HEIGHT / 2;
  const count = sorted.length;
  const baseRadius = count <= 8 ? 95 : count <= 20 ? 130 : count <= 36 ? 150 : 162;
  const maxDegree = Math.max(1, ...Array.from(degreeMap.values()));
  sorted.forEach((node, idx) => {
    const theta = (Math.PI * 2 * idx) / count - Math.PI / 2;
    const pull = ((degreeMap.get(node.key) || 0) / maxDegree) * 38;
    const jitter = ((idx % 3) - 1) * 8;
    const r = Math.max(50, baseRadius - pull + jitter);
    positions.set(node.key, {
      x: centerX + Math.cos(theta) * r,
      y: centerY + Math.sin(theta) * r,
    });
  });
  return positions;
}

function filterItems(items, query) {
  if (!query) return items;
  return items.filter(item => item.searchBlob.includes(query));
}

function normaliseMemory(mem) {
  if (!mem) return [];
  const rawItems = Array.isArray(mem)
    ? mem.map(m => ({ key: m.key || m.name || m.id || '', value: m.value ?? m.content ?? '' }))
    : Object.entries(mem).map(([key, value]) => ({ key, value }));
  return rawItems
    .map(item => {
      const key = String(item.key || '').trim();
      const valueText = stringifyValue(item.value);
      return {
        key,
        value: item.value,
        valueText,
        searchBlob: `${key} ${valueText}`.toLowerCase(),
      };
    })
    .filter(item => item.key.length > 0);
}

function tokenise(text) {
  const parts = String(text || '').toLowerCase().match(/[a-z0-9_]+/g) || [];
  const filtered = parts.filter(t => t.length >= 3 && !STOP_WORDS.has(t));
  return new Set(filtered);
}

function sharedTokenCount(a, b) {
  let count = 0;
  const small = a.size <= b.size ? a : b;
  const large = a.size <= b.size ? b : a;
  small.forEach(token => { if (large.has(token)) count += 1; });
  return count;
}

async function saveMemory() {
  const keyEl = document.getElementById('memory-key-input');
  const valEl = document.getElementById('memory-val-input');
  const key = keyEl?.value.trim() || '';
  const val = valEl?.value.trim() || '';
  if (!key || !val) return;
  try {
    await rpc('set_config', { key_path: `memory.${key}`, value: val });
    keyEl.value = '';
    valEl.value = '';
    await refreshMemory();
    addMessage(`Memory "${key}" saved.`, 'assistant');
  } catch (e) {
    addMessage(`Save failed: ${e}`, 'assistant');
  }
}

function stringifyValue(value) {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value ?? '');
  }
}

function truncate(text, max) {
  const s = String(text || '');
  return s.length <= max ? s : `${s.slice(0, Math.max(0, max - 3))}...`;
}

function escAttr(s) { return esc(String(s || '')).replace(/"/g, '&quot;'); }
function esc(s) { return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
