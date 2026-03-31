import * as vscode from "vscode";
import { RpcClient } from "./rpc";
import { ChatPanel } from "./chat";

let client: RpcClient | undefined;

export async function activate(context: vscode.ExtensionContext) {
  const config = vscode.workspace.getConfiguration("poor-cli");
  const serverCmd = config.get<string>("serverCommand", "poor-cli-server --stdio");
  client = new RpcClient(serverCmd);
  try {
    await client.start();
  } catch (err) {
    vscode.window.showErrorMessage(`poor-cli server failed to start: ${err}`);
    return;
  }
  context.subscriptions.push(
    vscode.commands.registerCommand("poor-cli.chat", () => {
      ChatPanel.createOrShow(context.extensionUri, client!);
    }),
    vscode.commands.registerCommand("poor-cli.review", async () => {
      const editor = vscode.window.activeTextEditor;
      if (!editor) {
        vscode.window.showWarningMessage("No active file to review.");
        return;
      }
      const filePath = editor.document.uri.fsPath;
      vscode.window.withProgress(
        { location: vscode.ProgressLocation.Notification, title: "poor-cli: reviewing..." },
        async () => {
          const result = await client!.request("poor-cli/chat", {
            message: `Review the file ${filePath} for issues and improvements.`,
          });
          const panel = ChatPanel.createOrShow(context.extensionUri, client!);
          panel.appendMessage("assistant", result?.text ?? JSON.stringify(result));
        },
      );
    }),
    vscode.commands.registerCommand("poor-cli.switchProvider", async () => {
      const providers = ["gemini", "openai", "anthropic", "ollama", "openrouter"];
      const pick = await vscode.window.showQuickPick(providers, { placeHolder: "Select AI provider" });
      if (pick) {
        await client!.request("switchProvider", { provider: pick });
        vscode.window.showInformationMessage(`Switched to ${pick}`);
      }
    }),
    { dispose: () => client?.stop() },
  );
}

export function deactivate() {
  client?.stop();
}
