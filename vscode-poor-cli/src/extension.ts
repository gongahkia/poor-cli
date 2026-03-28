import * as vscode from 'vscode';
import { RpcClient } from './rpc';
import { ChatViewProvider } from './chatView';
import { CompletionProvider } from './completionProvider';

let rpcClient: RpcClient | undefined;

export function activate(context: vscode.ExtensionContext) {
    const config = vscode.workspace.getConfiguration('poor-cli');
    const serverPath = config.get<string>('serverPath', 'poor-cli-server');

    rpcClient = new RpcClient(serverPath, vscode.workspace.workspaceFolders?.[0]?.uri.fsPath);

    // chat webview
    const chatProvider = new ChatViewProvider(context.extensionUri, rpcClient);
    context.subscriptions.push(
        vscode.window.registerWebviewViewProvider('poor-cli.chatView', chatProvider)
    );

    // inline completion
    const completionProvider = new CompletionProvider(rpcClient);
    context.subscriptions.push(
        vscode.languages.registerInlineCompletionItemProvider(
            { pattern: '**' },
            completionProvider
        )
    );

    // commands
    context.subscriptions.push(
        vscode.commands.registerCommand('poor-cli.chat', () => {
            vscode.commands.executeCommand('poor-cli.chatView.focus');
        }),
        vscode.commands.registerCommand('poor-cli.reviewFile', async () => {
            const editor = vscode.window.activeTextEditor;
            if (!editor) return;
            const content = editor.document.getText();
            const file = editor.document.uri.fsPath;
            const resp = await rpcClient?.request('chat', {
                prompt: `Review this file for issues:\n\nFile: ${file}\n\`\`\`\n${content.slice(0, 10000)}\n\`\`\``,
            });
            if (resp?.result) {
                const doc = await vscode.workspace.openTextDocument({
                    content: JSON.stringify(resp.result, null, 2),
                    language: 'json',
                });
                vscode.window.showTextDocument(doc);
            }
        })
    );

    // status bar
    const statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Right, 100);
    statusItem.text = '$(hubot) poor-cli';
    statusItem.command = 'poor-cli.chat';
    statusItem.show();
    context.subscriptions.push(statusItem);

    rpcClient.start().then(ok => {
        if (ok) {
            statusItem.text = '$(hubot) poor-cli ✓';
            vscode.window.showInformationMessage('poor-cli server connected');
        } else {
            statusItem.text = '$(hubot) poor-cli ✗';
        }
    });
}

export function deactivate() {
    rpcClient?.stop();
}
