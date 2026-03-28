/**
 * Mission Control — multi-session grid overview for poor-cli desktop.
 *
 * Shows all active sessions as cards with live status, last message preview,
 * and quick actions (switch, fork, destroy).
 */

import { rpc } from './rpc.js';

let _refreshTimer = null;

export function initMissionControl() {
    const container = document.getElementById('mission-control-view');
    if (!container) return;
    refreshMissionControl();
    // auto-refresh every 5s when visible
    if (_refreshTimer) clearInterval(_refreshTimer);
    _refreshTimer = setInterval(() => {
        if (container.offsetParent !== null) refreshMissionControl();
    }, 5000);
}

export async function refreshMissionControl() {
    const container = document.getElementById('mission-control-view');
    if (!container) return;

    try {
        const result = await rpc('poor-cli/listMuxSessions', {});
        const sessions = result.sessions || [];
        const agents = await rpc('poor-cli/listAgents', { statuses: ['running', 'queued'] })
            .then(r => r.agents || []).catch(() => []);

        container.innerHTML = renderGrid(sessions, agents);
        bindActions(container);
    } catch (err) {
        container.innerHTML = `<div class="mc-empty">Failed to load sessions: ${err.message}</div>`;
    }
}

function renderGrid(sessions, agents) {
    if (sessions.length === 0 && agents.length === 0) {
        return '<div class="mc-empty">No active sessions or agents.</div>';
    }

    let html = '<div class="mc-grid">';

    // session cards
    for (const s of sessions) {
        const isDefault = s.isDefault ? ' mc-card-active' : '';
        const statusDot = s.status === 'active'
            ? '<span class="mc-dot mc-dot-active"></span>'
            : '<span class="mc-dot mc-dot-idle"></span>';
        html += `
        <div class="mc-card${isDefault}" data-session-id="${s.sessionId}">
            <div class="mc-card-header">
                ${statusDot}
                <span class="mc-card-title">${escHtml(s.label)}</span>
                ${s.branchName ? `<span class="mc-card-branch">${escHtml(s.branchName)}</span>` : ''}
            </div>
            <div class="mc-card-body">
                <div class="mc-card-meta">${escHtml(s.workingDirectory)}</div>
                <div class="mc-card-time">${relativeTime(s.createdAt)}</div>
            </div>
            <div class="mc-card-actions">
                <button class="mc-btn mc-btn-switch" data-action="switch" data-id="${s.sessionId}">Switch</button>
                <button class="mc-btn mc-btn-fork" data-action="fork" data-id="${s.sessionId}">Fork</button>
                <button class="mc-btn mc-btn-destroy" data-action="destroy" data-id="${s.sessionId}">×</button>
            </div>
        </div>`;
    }

    // agent cards
    for (const a of agents) {
        const statusClass = a.status === 'running' ? 'mc-dot-active' : 'mc-dot-idle';
        html += `
        <div class="mc-card mc-card-agent">
            <div class="mc-card-header">
                <span class="mc-dot ${statusClass}"></span>
                <span class="mc-card-title">Agent: ${escHtml(a.agentId)}</span>
            </div>
            <div class="mc-card-body">
                <div class="mc-card-meta">${escHtml(a.prompt.slice(0, 80))}</div>
                <div class="mc-card-time">${a.status} | ${escHtml(a.branchName)}</div>
            </div>
            <div class="mc-card-actions">
                <button class="mc-btn mc-btn-logs" data-action="agent-logs" data-id="${a.agentId}">Logs</button>
                ${a.status === 'running'
                    ? `<button class="mc-btn mc-btn-destroy" data-action="agent-cancel" data-id="${a.agentId}">Cancel</button>`
                    : ''}
            </div>
        </div>`;
    }

    html += '</div>';
    return html;
}

function bindActions(container) {
    container.querySelectorAll('[data-action]').forEach(btn => {
        btn.onclick = async () => {
            const action = btn.dataset.action;
            const id = btn.dataset.id;
            try {
                if (action === 'switch') {
                    await rpc('poor-cli/switchSession', { sessionId: id });
                } else if (action === 'fork') {
                    await rpc('poor-cli/forkSession', { sourceSessionId: id, copyHistory: true });
                } else if (action === 'destroy') {
                    if (confirm(`Destroy session ${id}?`)) {
                        await rpc('poor-cli/destroySession', { sessionId: id });
                    }
                } else if (action === 'agent-logs') {
                    const result = await rpc('poor-cli/getAgentLogs', { agentId: id, tail: 50 });
                    alert(result.logs || 'No logs');
                } else if (action === 'agent-cancel') {
                    await rpc('poor-cli/cancelAgent', { agentId: id });
                }
                refreshMissionControl();
            } catch (err) {
                console.error(`action ${action} failed:`, err);
            }
        };
    });
}

function escHtml(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function relativeTime(iso) {
    if (!iso) return '';
    const diff = Date.now() - new Date(iso).getTime();
    const mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    return `${Math.floor(hrs / 24)}d ago`;
}
