import * as vscode from 'vscode';
import { RpcClient } from './rpc';

export class ChatViewProvider implements vscode.WebviewViewProvider {
    constructor(
        private extensionUri: vscode.Uri,
        private rpc: RpcClient,
    ) {}

    resolveWebviewView(webviewView: vscode.WebviewView): void {
        webviewView.webview.options = {
            enableScripts: true,
            localResourceRoots: [this.extensionUri],
        };
        webviewView.webview.html = this.getHtml();

        webviewView.webview.onDidReceiveMessage(async (msg) => {
            if (msg.type === 'chat') {
                const resp = await this.rpc.request('chat', {
                    prompt: msg.text,
                    contextFiles: msg.contextFiles || [],
                });
                webviewView.webview.postMessage({
                    type: 'response',
                    text: resp?.result?.response || resp?.error?.message || 'no response',
                });
            }
        });
    }

    private getHtml(): string {
        return `<!DOCTYPE html>
<html>
<head>
<style>
body { font-family: var(--vscode-font-family); padding: 8px; margin: 0; }
#messages { overflow-y: auto; flex: 1; }
.msg { margin: 4px 0; padding: 6px 8px; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; }
.user { background: var(--vscode-input-background); }
.assistant { background: var(--vscode-editor-background); border: 1px solid var(--vscode-panel-border); }
#input-row { display: flex; gap: 4px; margin-top: 8px; }
#prompt { flex: 1; padding: 6px; border: 1px solid var(--vscode-input-border); background: var(--vscode-input-background); color: var(--vscode-input-foreground); border-radius: 4px; }
button { padding: 6px 12px; cursor: pointer; border-radius: 4px; border: none; background: var(--vscode-button-background); color: var(--vscode-button-foreground); }
</style>
</head>
<body>
<div id="messages"></div>
<div id="input-row">
    <input id="prompt" placeholder="Ask poor-cli..." />
    <button id="send">Send</button>
</div>
<script>
const vscode = acquireVsCodeApi();
const messages = document.getElementById('messages');
const prompt = document.getElementById('prompt');
const send = document.getElementById('send');

function addMsg(role, text) {
    const div = document.createElement('div');
    div.className = 'msg ' + role;
    div.textContent = text;
    messages.appendChild(div);
    messages.scrollTop = messages.scrollHeight;
}

send.onclick = () => {
    const text = prompt.value.trim();
    if (!text) return;
    addMsg('user', text);
    vscode.postMessage({ type: 'chat', text });
    prompt.value = '';
};

prompt.onkeydown = (e) => { if (e.key === 'Enter') send.click(); };

window.addEventListener('message', (e) => {
    if (e.data.type === 'response') addMsg('assistant', e.data.text);
});
</script>
</body>
</html>`;
    }
}
