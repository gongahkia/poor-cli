import * as vscode from "vscode";
import { RpcClient } from "./rpc";

export class ChatPanel {
  private static instance: ChatPanel | undefined;
  private panel: vscode.WebviewPanel;
  private client: RpcClient;

  static createOrShow(extensionUri: vscode.Uri, client: RpcClient): ChatPanel {
    if (ChatPanel.instance) {
      ChatPanel.instance.panel.reveal();
      return ChatPanel.instance;
    }
    const panel = vscode.window.createWebviewPanel("poor-cli.chat", "poor-cli Chat", vscode.ViewColumn.Beside, {
      enableScripts: true,
      retainContextWhenHidden: true,
    });
    ChatPanel.instance = new ChatPanel(panel, client);
    return ChatPanel.instance;
  }

  private constructor(panel: vscode.WebviewPanel, client: RpcClient) {
    this.panel = panel;
    this.client = client;
    this.panel.webview.html = this.getHtml();
    this.panel.onDidDispose(() => { ChatPanel.instance = undefined; });
    this.panel.webview.onDidReceiveMessage(async (msg) => {
      if (msg.type === "send") {
        this.appendMessage("user", msg.text);
        try {
          const result = await this.client.request("poor-cli/chat", { message: msg.text });
          this.appendMessage("assistant", result?.text ?? JSON.stringify(result));
        } catch (err: any) {
          this.appendMessage("error", err?.message ?? String(err));
        }
      }
    });
    this.client.onNotification("streamingChunk", (params: any) => {
      this.panel.webview.postMessage({ type: "chunk", text: params?.chunk ?? "" });
    });
  }

  appendMessage(role: string, text: string): void {
    this.panel.webview.postMessage({ type: "message", role, text });
  }

  private getHtml(): string {
    return `<!DOCTYPE html>
<html>
<head>
<style>
  body { font-family: var(--vscode-font-family); background: var(--vscode-editor-background); color: var(--vscode-editor-foreground); margin: 0; padding: 8px; display: flex; flex-direction: column; height: 100vh; }
  #messages { flex: 1; overflow-y: auto; padding-bottom: 8px; }
  .msg { margin: 4px 0; padding: 6px 10px; border-radius: 6px; white-space: pre-wrap; word-wrap: break-word; }
  .msg.user { background: var(--vscode-input-background); }
  .msg.assistant { background: var(--vscode-textBlockQuote-background); }
  .msg.error { color: var(--vscode-errorForeground); }
  #input-row { display: flex; gap: 4px; }
  #input { flex: 1; padding: 6px; background: var(--vscode-input-background); color: var(--vscode-input-foreground); border: 1px solid var(--vscode-input-border); border-radius: 4px; }
  button { padding: 6px 12px; background: var(--vscode-button-background); color: var(--vscode-button-foreground); border: none; border-radius: 4px; cursor: pointer; }
</style>
</head>
<body>
  <div id="messages"></div>
  <div id="input-row">
    <input id="input" placeholder="Ask poor-cli..." />
    <button onclick="send()">Send</button>
  </div>
  <script>
    const vscode = acquireVsCodeApi();
    const messages = document.getElementById("messages");
    function addMsg(role, text) {
      const div = document.createElement("div");
      div.className = "msg " + role;
      div.textContent = (role === "user" ? "You: " : role === "error" ? "Error: " : "") + text;
      messages.appendChild(div);
      messages.scrollTop = messages.scrollHeight;
    }
    function send() {
      const input = document.getElementById("input");
      const text = input.value.trim();
      if (!text) return;
      vscode.postMessage({ type: "send", text });
      input.value = "";
    }
    document.getElementById("input").addEventListener("keydown", e => { if (e.key === "Enter") send(); });
    window.addEventListener("message", e => {
      const msg = e.data;
      if (msg.type === "message") addMsg(msg.role, msg.text);
      if (msg.type === "chunk") {
        let last = messages.lastElementChild;
        if (!last || !last.classList.contains("assistant")) {
          last = document.createElement("div");
          last.className = "msg assistant";
          messages.appendChild(last);
        }
        last.textContent += msg.text;
        messages.scrollTop = messages.scrollHeight;
      }
    });
  </script>
</body>
</html>`;
  }
}
