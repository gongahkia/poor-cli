import * as cp from 'child_process';
import * as readline from 'readline';

interface JsonRpcMessage {
    jsonrpc: '2.0';
    id?: number;
    method?: string;
    params?: any;
    result?: any;
    error?: any;
}

type PendingRequest = {
    resolve: (msg: JsonRpcMessage) => void;
    reject: (err: Error) => void;
};

export class RpcClient {
    private proc: cp.ChildProcess | undefined;
    private nextId = 1;
    private pending = new Map<number, PendingRequest>();
    private buffer = '';

    constructor(
        private serverPath: string,
        private cwd?: string,
    ) {}

    async start(): Promise<boolean> {
        try {
            this.proc = cp.spawn(this.serverPath, [], {
                cwd: this.cwd,
                stdio: ['pipe', 'pipe', 'pipe'],
            });

            if (!this.proc.stdout) return false;

            this.proc.stdout.on('data', (chunk: Buffer) => {
                this.buffer += chunk.toString();
                this.processBuffer();
            });

            this.proc.on('exit', (code) => {
                for (const [, pending] of this.pending) {
                    pending.reject(new Error(`server exited with code ${code}`));
                }
                this.pending.clear();
            });

            // initialize
            const resp = await this.request('initialize', {
                clientCapabilities: { streaming: false },
                permissionMode: 'auto-safe',
            });
            return resp?.result != null;
        } catch {
            return false;
        }
    }

    stop(): void {
        this.proc?.kill();
        this.proc = undefined;
    }

    async request(method: string, params: any = {}): Promise<JsonRpcMessage> {
        const id = this.nextId++;
        const msg: JsonRpcMessage = { jsonrpc: '2.0', id, method, params };
        return new Promise((resolve, reject) => {
            this.pending.set(id, { resolve, reject });
            this.send(msg);
            setTimeout(() => {
                if (this.pending.has(id)) {
                    this.pending.delete(id);
                    reject(new Error(`request ${method} timed out`));
                }
            }, 30000);
        });
    }

    private send(msg: JsonRpcMessage): void {
        if (!this.proc?.stdin) return;
        const body = JSON.stringify(msg);
        const header = `Content-Length: ${Buffer.byteLength(body)}\r\n\r\n`;
        this.proc.stdin.write(header + body);
    }

    private processBuffer(): void {
        while (true) {
            const headerEnd = this.buffer.indexOf('\r\n\r\n');
            if (headerEnd === -1) break;
            const header = this.buffer.slice(0, headerEnd);
            const match = header.match(/Content-Length:\s*(\d+)/i);
            if (!match) {
                this.buffer = this.buffer.slice(headerEnd + 4);
                continue;
            }
            const len = parseInt(match[1], 10);
            const bodyStart = headerEnd + 4;
            if (this.buffer.length < bodyStart + len) break;
            const body = this.buffer.slice(bodyStart, bodyStart + len);
            this.buffer = this.buffer.slice(bodyStart + len);
            try {
                const msg: JsonRpcMessage = JSON.parse(body);
                if (msg.id != null && this.pending.has(msg.id)) {
                    const p = this.pending.get(msg.id)!;
                    this.pending.delete(msg.id);
                    p.resolve(msg);
                }
            } catch {}
        }
    }
}
