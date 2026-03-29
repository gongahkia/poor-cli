// tools & MCP view
import { rpc } from './rpc.js';

export async function initTools() {
  const content = document.getElementById('tools-content');
  content.innerHTML = '<p>Loading...</p>';
  try {
    const [tools, mcp] = await Promise.all([
      rpc('get_tools', {}).catch(() => null),
      rpc('get_mcp_status', {}).catch(() => null),
    ]);
    let html = '';
    // tools
    const toolList = tools?.tools || tools || [];
    if (Array.isArray(toolList) && toolList.length) {
      html += '<h3>Tools</h3>';
      toolList.forEach(t => {
        html += `<div class="item-card"><h4>${esc(t.name || 'Untitled')}</h4><p>${esc(t.description || '')}</p></div>`;
      });
    } else {
      html += '<h3>Tools</h3><p style="color:var(--text-muted)">No tools available</p>';
    }
    // MCP
    html += '<h3 style="margin-top:16px">MCP Servers</h3>';
    if (mcp && (mcp.servers || mcp.connections)) {
      const servers = mcp.servers || mcp.connections || [];
      if (!servers.length) {
        html += '<p style="color:var(--text-muted)">No MCP servers configured</p>';
      } else {
        servers.forEach(s => {
          html += `<div class="item-card"><h4>${esc(s.name || s.url || '?')}</h4><span class="badge">${esc(s.status || 'unknown')}</span></div>`;
        });
      }
    } else {
      html += '<p style="color:var(--text-muted)">MCP status unavailable</p>';
    }
    content.innerHTML = html;
  } catch (_) {
    content.innerHTML = '<p style="color:var(--text-muted)">Tools unavailable — backend not connected</p>';
  }
}

function esc(s) { return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }
