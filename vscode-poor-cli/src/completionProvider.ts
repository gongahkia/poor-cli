import * as vscode from 'vscode';
import { RpcClient } from './rpc';

export class CompletionProvider implements vscode.InlineCompletionItemProvider {
    private debounceTimer: NodeJS.Timeout | undefined;

    constructor(private rpc: RpcClient) {}

    async provideInlineCompletionItems(
        document: vscode.TextDocument,
        position: vscode.Position,
        context: vscode.InlineCompletionContext,
        token: vscode.CancellationToken,
    ): Promise<vscode.InlineCompletionItem[]> {
        // debounce
        if (this.debounceTimer) clearTimeout(this.debounceTimer);

        return new Promise((resolve) => {
            this.debounceTimer = setTimeout(async () => {
                if (token.isCancellationRequested) {
                    resolve([]);
                    return;
                }

                const offset = document.offsetAt(position);
                const fullText = document.getText();
                const prefix = fullText.slice(Math.max(0, offset - 4000), offset);
                const suffix = fullText.slice(offset, offset + 4000);

                try {
                    const resp = await this.rpc.request('poor-cli/getCompletion', {
                        filePath: document.uri.fsPath,
                        line: position.line,
                        column: position.character,
                        prefix,
                        suffix,
                        language: document.languageId,
                    });

                    const text = resp?.result?.completion?.text;
                    if (!text || token.isCancellationRequested) {
                        resolve([]);
                        return;
                    }

                    resolve([new vscode.InlineCompletionItem(text, new vscode.Range(position, position))]);
                } catch {
                    resolve([]);
                }
            }, 300);
        });
    }
}
