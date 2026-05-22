import { readFileSync } from "node:fs";

export const SERVER_NAME = "swee-sg";
export const SERVER_VERSION = "0.1.0";
export const SERVER_TITLE = "Swee SG";
export const SERVER_DESCRIPTION =
  "Swee SG is a policy-governed MCP and REST gateway for Singapore public-data tools, Shield audit trails, and Pulse city signals.";
export const SERVER_WEBSITE_URL = "https://github.com/gongahkia/swee-sg";
export const SERVER_INSTRUCTIONS = [
  "Use Swee Shield audit and policy metadata before trusting tool calls.",
  "Use Swee Pulse tools for Singapore mobility and weather live-ops snapshots.",
  "Treat public-data gaps as source limits, not inferred facts.",
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
