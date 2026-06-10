import { readFileSync } from "node:fs";

export const SERVER_NAME = "swee-sg";
export const SERVER_VERSION = "0.1.0";
export const SERVER_TITLE = "Swee SG MCP";
export const SERVER_DESCRIPTION =
  "Swee SG MCP is the policy-governed runtime for Singapore public-data source adapters, Swee Pulse city signals, and Swee Shield audit, approval, and Splunk investigation workflows.";
export const SERVER_WEBSITE_URL = "https://github.com/gongahkia/swee-sg";
export const SERVER_INSTRUCTIONS = [
  "Prefer swee_pulse_snapshot for app-level city signals, then drop to direct sg_* source adapters when you have exact structured inputs.",
  "Prefer swee_shield_splunk_investigation_pack before ad hoc Splunk searches; use swee_shield_policy_simulate for token-free SPL risk checks.",
  "Use sg://recipes, sg://playbooks, and sg://workflows for discovery before inventing new multi-step flows.",
  "Swee SG is read-mostly. Ops tools mutate only local cache, config, keystore, or Shield audit state.",
].join(" ");

let cachedIconDataUri: string | undefined;

const getIconDataUri = (): string => {
  if (cachedIconDataUri !== undefined) {
    return cachedIconDataUri;
  }

  const iconBuffer = readFileSync(new URL("../assets/icon.svg", import.meta.url));
  cachedIconDataUri = `data:image/svg+xml;base64,${iconBuffer.toString("base64")}`;
  return cachedIconDataUri;
};

export const buildServerIcons = (baseUrl?: URL) => {
  return [
    {
      src: baseUrl === undefined ? getIconDataUri() : new URL("/icon.svg", baseUrl).href,
      mimeType: "image/svg+xml",
      sizes: ["128x128"],
    },
  ];
};
