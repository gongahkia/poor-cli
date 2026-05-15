import { useEffect, useState } from "react";

import { getGatewayJson, type GatewayHealth } from "@/lib/api/client";

type StatusState =
  | { status: "loading" }
  | { status: "online"; health: GatewayHealth }
  | { status: "offline"; message: string };

export function GatewayStatus() {
  const [state, setState] = useState<StatusState>({ status: "loading" });

  useEffect(() => {
    const controller = new AbortController();
    void getGatewayJson<GatewayHealth>("/api/v1/health", {}, { signal: controller.signal })
      .then((health) => {
        if (!controller.signal.aborted) {
          setState({ status: "online", health });
        }
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setState({
            status: "offline",
            message: error instanceof Error ? error.message : "Gateway unavailable.",
          });
        }
      });

    return () => controller.abort();
  }, []);

  if (state.status === "loading") {
    return <p className="text-xs text-muted-foreground">Checking gateway status...</p>;
  }

  if (state.status === "offline") {
    return <p className="text-xs text-destructive">Gateway offline: {state.message}</p>;
  }

  const tinyfishConfigured = state.health.services?.tinyfish?.configured === true;
  const tinyfishStatus = tinyfishConfigured ? "TinyFish key loaded" : "TinyFish key missing";

  return (
    <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
      <span className="rounded-md bg-muted px-2 py-1">Gateway online</span>
      <span className="rounded-md bg-muted px-2 py-1">ACRA route ready</span>
      <span className="rounded-md bg-muted px-2 py-1">{tinyfishStatus}</span>
    </div>
  );
}
