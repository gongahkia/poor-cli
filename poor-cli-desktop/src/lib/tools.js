// tools view — available tool documentation
import { rpc } from './rpc.js';

export async function initTools() {
  const content = document.getElementById('tools-content');
  content.innerHTML = '<p class="view-empty-text">Loading...</p>';
  try {
    const result = await rpc('get_tools', {}).catch(e => { console.warn('[tools] get_tools:', e); return null; });
    const toolList = result?.tools || result || [];
    if (!Array.isArray(toolList) || !toolList.length) {
      content.innerHTML = '<div class="view-empty"><p>No tools available</p></div>';
      return;
    }
    // group by category
    const groups = {};
    toolList.forEach(t => {
      const cat = t.category || t.source || 'Built-in';
      if (!groups[cat]) groups[cat] = [];
      groups[cat].push(t);
    });
    // search
    const search = document.createElement('input');
    search.type = 'text';
    search.className = 'search-input';
    search.placeholder = 'Search tools...';
    content.innerHTML = '';
    content.appendChild(search);
    const countEl = document.createElement('div');
    countEl.className = 'tools-count';
    countEl.textContent = `${toolList.length} tools available`;
    content.appendChild(countEl);
    const listEl = document.createElement('div');
    listEl.id = 'tools-list';
    content.appendChild(listEl);
    function render(filter) {
      listEl.innerHTML = '';
      let shown = 0;
      for (const [cat, tools] of Object.entries(groups)) {
        const filtered = filter ? tools.filter(t => (t.name || '').toLowerCase().includes(filter) || (t.description || '').toLowerCase().includes(filter)) : tools;
        if (!filtered.length) continue;
        const section = document.createElement('div');
        section.className = 'tools-section';
        section.innerHTML = `<div class="tools-section-header"><h3>${esc(cat)}</h3><span class="tools-section-count">${filtered.length}</span></div>`;
        const grid = document.createElement('div');
        grid.className = 'tools-grid';
        filtered.forEach(t => {
          const card = document.createElement('div');
          card.className = 'tool-card';
          let params = '';
          const schema = t.inputSchema || t.parameters || t.schema;
          if (schema?.properties) {
            const props = Object.entries(schema.properties);
            const required = schema.required || [];
            params = props.map(([k, v]) => {
              const req = required.includes(k);
              return `<span class="tool-param${req ? ' tool-param-req' : ''}" title="${esc(v.description || '')}">${esc(k)}${req ? '*' : ''}</span>`;
            }).join('');
          }
          card.innerHTML = `<div class="tool-name">${esc(t.name || 'Untitled')}</div>`
            + `<div class="tool-desc">${esc(t.description || '')}</div>`
            + (params ? `<div class="tool-params">${params}</div>` : '');
          grid.appendChild(card);
        });
        section.appendChild(grid);
        listEl.appendChild(section);
        shown += filtered.length;
      }
      countEl.textContent = filter ? `${shown} of ${toolList.length} tools` : `${toolList.length} tools available`;
    }
    render('');
    search.addEventListener('input', () => render(search.value.toLowerCase().trim()));
  } catch (e) {
    console.warn('[tools] initTools:', e);
    content.innerHTML = '<div class="view-empty"><p>Tools unavailable — backend not connected</p></div>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
