import * as cp from "child_process";
import { createMessageConnection, StreamMessageReader, StreamMessageWriter, MessageConnection } from "vscode-jsonrpc/node";

export class RpcClient {
  private process: cp.ChildProcess | undefined;
  private connection: MessageConnection | undefined;
  private cmd: string;

  constructor(serverCommand: string) {
    this.cmd = serverCommand;
  }

  async start(): Promise<void> {
    const parts = this.cmd.split(/\s+/);
    this.process = cp.spawn(parts[0], parts.slice(1), { stdio: ["pipe", "pipe", "pipe"] });
    if (!this.process.stdout || !this.process.stdin) {
      throw new Error("Failed to attach stdio to server process");
    }
    this.connection = createMessageConnection(
      new StreamMessageReader(this.process.stdout),
      new StreamMessageWriter(this.process.stdin),
    );
    this.connection.listen();
    await this.connection.sendRequest("initialize", {
      clientName: "vscode-poor-cli",
      capabilities: { streaming: true },
    });
  }

  async request(method: string, params: Record<string, unknown>): Promise<any> {
    if (!this.connection) throw new Error("RPC client not started");
    return this.connection.sendRequest(method, params);
  }

  onNotification(method: string, handler: (params: any) => void): void {
    this.connection?.onNotification(method, handler);
  }

  stop(): void {
    this.connection?.dispose();
    this.process?.kill();
    this.process = undefined;
    this.connection = undefined;
  }
}
