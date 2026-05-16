import { readFileSync } from "node:fs";

export const SERVER_NAME = "dude";
export const SERVER_VERSION = "0.1.0";
export const SERVER_TITLE = "Dude MCP";
export const SERVER_DESCRIPTION =
  "Dude MCP is Dude's backend runtime for bounded Singapore public-data and due-diligence workflows across official datasets, registries, maps, and realtime signals.";
export const SERVER_WEBSITE_URL = "https://github.com/gongahkia/dude";
export const SERVER_INSTRUCTIONS = [
  "Prefer sg_query for bounded natural-language workflows, then drop to direct sg_* tools when you have exact identifiers.",
  "Use sg://recipes, sg://playbooks, and sg://workflows for discovery before inventing new multi-step flows.",
  "Dude MCP is read-mostly. Ops tools mutate only local cache, config, or keystore state.",
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
