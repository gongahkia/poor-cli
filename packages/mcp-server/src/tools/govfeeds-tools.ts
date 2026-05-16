import { formatResponse, GovFeedCatalogSchema, GovFeedItemsSchema, resolveOutputFormat } from "@dude/shared";
import type { OutputFormat, ToolResult } from "@dude/shared";
import { getGovFeedCatalog, getGovFeedItems } from "../apis/govfeeds/client.js";
import { assertFamilyEnabled, assertStreamEnabled } from "./surface-gates.js";
import type { RegisteredToolDefinition } from "./tool-definition.js";

const GOV_FEED_FAMILY_ID = "government_rss_feeds";

export const handleGovFeedCatalog = async (
  params: Readonly<{ family?: "all" | "nea" | "weather" | "sfa" | "mpa" | "nhb" | "ura" | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  assertFamilyEnabled(GOV_FEED_FAMILY_ID, "sg_gov_feed_catalog");
  const records = getGovFeedCatalog(params.family);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: formatResponse(records as unknown as Record<string, unknown>[], format) }],
    structuredContent: {
      records,
      limits: {
        families: ["all", "nea", "weather", "sfa", "mpa", "nhb", "ura"],
      },
      rollback: {
        familyId: GOV_FEED_FAMILY_ID,
        familyEnvVar: "SG_APIS_DISABLED_FAMILIES",
      },
    },
  };
};

export const handleGovFeedItems = async (
  params: Readonly<{ feedId: string; limit?: number | undefined; keyword?: string | undefined; format?: OutputFormat | undefined }>,
): Promise<ToolResult> => {
  assertFamilyEnabled(GOV_FEED_FAMILY_ID, "sg_gov_feed_items");
  assertStreamEnabled(params.feedId, "sg_gov_feed_items");

  const result = await getGovFeedItems(params);
  const format = resolveOutputFormat(params.format);
  return {
    content: [{ type: "text", text: formatResponse(result.records as unknown as Record<string, unknown>[], format) }],
    structuredContent: {
      feed: result.feed,
      records: result.records,
      freshness: {
        observedAt: result.observedAt,
        sourceTimestamp: result.records[0]?.publishedAt ?? null,
      },
      provenance: {
        source: "official-feed",
        sourceAgency: result.feed.sourceAgency,
        sourceUrl: result.feed.sourceUrl,
        channelTitle: result.channelTitle,
        cached: result.cached,
      },
      limits: {
        defaultLimit: 20,
        maxLimit: 100,
        supportedFilters: ["keyword"],
      },
      rollback: {
        familyId: GOV_FEED_FAMILY_ID,
        familyEnvVar: "SG_APIS_DISABLED_FAMILIES",
        streamId: result.feed.id,
        streamEnvVar: "SG_APIS_DISABLED_STREAMS",
      },
    },
  };
};

export const govFeedToolDefinitions: readonly RegisteredToolDefinition[] = [
  {
    name: "sg_gov_feed_catalog",
    description: "List direct non-data.gov.sg official Singapore feeds available in this MCP server (NEA, weather.gov.sg, SFA, MPA, NHB, URA).",
    surface: "canonical",
    inputSchema: GovFeedCatalogSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = GovFeedCatalogSchema.parse(input);
      return handleGovFeedCatalog(parsed);
    },
  },
  {
    name: "sg_gov_feed_items",
    description: "Read official feed items (RSS and official listing pages) with stream-level rollback controls.",
    surface: "canonical",
    inputSchema: GovFeedItemsSchema.shape,
    handler: async (input: unknown): Promise<ToolResult> => {
      const parsed = GovFeedItemsSchema.parse(input);
      return handleGovFeedItems(parsed);
    },
  },
];
