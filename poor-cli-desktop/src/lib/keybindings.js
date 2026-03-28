/**
 * Global keyboard shortcuts and vim-style navigation for poor-cli desktop.
 *
 * Shortcuts:
 *   Cmd/Ctrl+P        — command palette
 *   Cmd/Ctrl+B        — toggle sidebar
 *   Cmd/Ctrl+J        — toggle file changes panel
 *   Cmd/Ctrl+Shift+C  — toggle collab panel
 *   Cmd/Ctrl+1-9      — switch to session tab N
 *   Cmd/Ctrl+T        — new session
 *   Cmd/Ctrl+W        — close current session
 *   Cmd/Ctrl+N        — new thread (focus chat)
 *   Cmd/Ctrl+,        — open settings
 *   F2                — switch provider
 *   Escape            — close overlays / blur input
 *
 * Vim navigation (when chat input is NOT focused):
 *   j/k               — scroll chat up/down
 *   g/G               — scroll to top/bottom
 *   /                 — focus chat input with / prefix
 */

import { showView } from './views.js';

let _initialized = false;

export function initKeybindings() {
  if (_initialized) return;
  _initialized = true;
  document.addEventListener('keydown', handleGlobalKey, true);
}

function handleGlobalKey(e) {
  const meta = e.metaKey || e.ctrlKey;
  const shift = e.shiftKey;
  const inputFocused = isInputFocused();

  // Cmd/Ctrl shortcuts (always active)
  if (meta) {
    switch (e.key) {
      case 'b': case 'B':
        e.preventDefault();
        toggleSidebar();
        return;
      case 'j': case 'J':
        if (!shift) {
          e.preventDefault();
          togglePanel('file-changes');
          return;
        }
        break;
      case 'C':
        if (shift) {
          e.preventDefault();
          togglePanel('collab');
          return;
        }
        break;
      case 't': case 'T':
        e.preventDefault();
        showView('chat');
        return;
      case 'n': case 'N':
        e.preventDefault();
        showView('chat');
        focusInput();
        return;
      case ',':
        e.preventDefault();
        showView('settings');
        return;
      case 'w': case 'W':
        e.preventDefault();
        closeCurrentSession();
        return;
    }
    // Cmd+1-9: switch to session tab
    if (e.key >= '1' && e.key <= '9') {
      e.preventDefault();
      switchToTab(parseInt(e.key) - 1);
      return;
    }
  }

  // F-keys
  if (e.key === 'F2') {
    e.preventDefault();
    sendSlash('/provider');
    return;
  }

  // Escape: close overlays or blur input
  if (e.key === 'Escape') {
    closeOverlays();
    blurInput();
    return;
  }

  // vim navigation (only when input is NOT focused)
  if (!inputFocused && !meta) {
    switch (e.key) {
      case 'j':
        scrollChat(60);
        return;
      case 'k':
        scrollChat(-60);
        return;
      case 'g':
        scrollChatToTop();
        return;
      case 'G':
        scrollChatToBottom();
        return;
      case '/':
        e.preventDefault();
        focusInput('/');
        return;
      case ':':
        e.preventDefault();
        focusInput('/');
        return;
    }
  }
}

// ── helpers ──────────────────────────────────────────────────────────

function isInputFocused() {
  const el = document.activeElement;
  return el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.contentEditable === 'true');
}

function toggleSidebar() {
  const sidebar = document.getElementById('sidebar');
  if (sidebar) sidebar.classList.toggle('collapsed');
}

function togglePanel(name) {
  const panel = document.getElementById(`${name}-panel`);
  if (panel) panel.classList.toggle('hidden');
}

function scrollChat(delta) {
  const chat = document.getElementById('messages');
  if (chat) chat.scrollTop += delta;
}

function scrollChatToTop() {
  const chat = document.getElementById('messages');
  if (chat) chat.scrollTop = 0;
}

function scrollChatToBottom() {
  const chat = document.getElementById('messages');
  if (chat) chat.scrollTop = chat.scrollHeight;
}

function focusInput(prefix) {
  const input = document.getElementById('chat-input');
  if (input) {
    input.focus();
    if (prefix) input.value = prefix;
  }
}

function blurInput() {
  const input = document.getElementById('chat-input');
  if (input && document.activeElement === input) input.blur();
}

function closeOverlays() {
  // close palette
  const palette = document.getElementById('palette-overlay');
  if (palette && !palette.classList.contains('hidden')) {
    palette.classList.add('hidden');
  }
  // close modals
  document.querySelectorAll('.modal-overlay').forEach(m => {
    if (!m.classList.contains('hidden')) m.classList.add('hidden');
  });
}

function switchToTab(index) {
  const tabs = document.querySelectorAll('.session-tab');
  if (tabs[index]) tabs[index].click();
}

function closeCurrentSession() {
  const active = document.querySelector('.session-tab.active .session-tab-close');
  if (active) active.click();
}

function sendSlash(command) {
  const input = document.getElementById('chat-input');
  if (input) {
    input.value = command;
    input.dispatchEvent(new Event('input'));
    // trigger send
    const form = input.closest('form');
    if (form) form.dispatchEvent(new Event('submit'));
  }
}
