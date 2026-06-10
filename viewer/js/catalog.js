import { fn } from './state.js';

export function initCatalog() {
  const searchBtn = document.getElementById('catalog-search-btn');
  const query = document.getElementById('catalog-query');
  if (!searchBtn || !query) return;
  searchBtn.addEventListener('click', searchCatalog);
  query.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      searchCatalog();
    }
  });
}

function resultRoot() {
  return document.getElementById('catalog-results');
}

function setCatalogMessage(text) {
  const root = resultRoot();
  if (!root) return;
  root.innerHTML = '';
  const row = document.createElement('div');
  row.className = 'catalog-card';
  const span = document.createElement('span');
  span.textContent = text;
  row.appendChild(span);
  root.appendChild(row);
}

function dims(item) {
  const d = item.dimensions_m || {};
  return `${d.width || '?'} x ${d.depth || '?'} x ${d.height || '?'}m`;
}

function price(item) {
  if (item.price === null || item.price === undefined) return '';
  return `${item.currency || 'SGD'} ${item.price}`;
}

async function searchCatalog() {
  const query = document.getElementById('catalog-query')?.value?.trim();
  if (!query) {
    setCatalogMessage('Enter a search term.');
    return;
  }
  const refresh = document.getElementById('catalog-refresh')?.checked ? '1' : '0';
  setCatalogMessage('Searching...');
  try {
    const res = await fetch(`/api/catalog/ikea/search?${new URLSearchParams({ q: query, refresh })}`);
    const body = await res.json();
    if (!res.ok || body.ok === false) throw new Error(body.error || `HTTP ${res.status}`);
    renderResults(body.items || []);
  } catch (err) {
    console.error('catalog search failed', err);
    setCatalogMessage(err.message || String(err));
  }
}

function renderResults(items) {
  const root = resultRoot();
  if (!root) return;
  root.innerHTML = '';
  if (!items.length) {
    setCatalogMessage('No IKEA items found.');
    return;
  }
  for (const item of items) {
    const card = document.createElement('div');
    card.className = 'catalog-card';
    const title = document.createElement('strong');
    title.textContent = item.name || item.id;
    const meta = document.createElement('span');
    meta.textContent = [item.category, dims(item), price(item)].filter(Boolean).join(' · ');
    const place = document.createElement('button');
    place.type = 'button';
    place.textContent = 'Place';
    place.addEventListener('click', () => placeItem(item.id, place));
    card.appendChild(title);
    card.appendChild(meta);
    card.appendChild(place);
    root.appendChild(card);
  }
}

async function placeItem(itemId, button) {
  const prev = button.textContent;
  button.textContent = 'Placing...';
  button.disabled = true;
  try {
    const res = await fetch(`/api/catalog/ikea/items/${encodeURIComponent(itemId)}/layout-item`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ x: 0, z: 0 }),
    });
    const body = await res.json();
    if (!res.ok || body.ok === false) throw new Error(body.error || `HTTP ${res.status}`);
    if (!fn.addLayoutItem(body.layout_item)) throw new Error('Could not place item.');
    button.textContent = 'Placed';
  } catch (err) {
    console.error('catalog place failed', err);
    button.textContent = err.message || 'Error';
  } finally {
    setTimeout(() => {
      button.disabled = false;
      button.textContent = prev;
    }, 1200);
  }
}
