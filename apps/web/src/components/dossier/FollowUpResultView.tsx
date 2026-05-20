import { useMemo, useState, type ReactNode } from "react";
import { Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  formatNextCheckInputLabel,
  formatNextCheckInputValue,
  getNextCheckInputEntries,
} from "@/lib/next-checks";

type SummaryItem = {
  readonly label: string;
  readonly value: unknown;
  readonly source?: string | null;
};

type EvidenceGap = {
  readonly code: string;
  readonly message: string;
};

type BriefLimit = {
  readonly code: string;
  readonly message: string;
};

type BriefFreshnessItem = {
  readonly source: string;
  readonly observedAt: string;
  readonly upstreamTimestamp?: string | null;
};

type BriefProvenanceItem = {
  readonly source: string;
  readonly tool: string;
  readonly coverage: string;
  readonly authRequired: boolean;
  readonly recordCount: number;
  readonly sourceUrl?: string;
};

type RiskFlag = {
  readonly code: string;
  readonly severity: string;
  readonly message: string;
  readonly source: string;
};

type BriefArtifactLike = {
  readonly title: string;
  readonly summary: readonly SummaryItem[];
  readonly evidence: readonly SummaryItem[];
  readonly records: Record<string, unknown>;
  readonly gaps: readonly EvidenceGap[];
  readonly provenance: readonly BriefProvenanceItem[];
  readonly freshness: readonly BriefFreshnessItem[];
  readonly limits: readonly BriefLimit[];
  readonly riskFlags?: readonly RiskFlag[];
};

type GraphNode = {
  readonly id: string;
  readonly label: string;
  readonly kind: string;
  readonly source?: string;
};

type GraphEdge = {
  readonly from: string;
  readonly to: string;
  readonly kind: string;
  readonly evidence?: string;
  readonly confidence?: string;
};

type RelationshipGraph = {
  readonly nodes: readonly GraphNode[];
  readonly edges: readonly GraphEdge[];
};

type LayoutNode = GraphNode & {
  readonly x: number;
  readonly y: number;
};

const isRecord = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);

const isSummaryItem = (value: unknown): value is SummaryItem =>
  isRecord(value) && typeof value["label"] === "string" && "value" in value;

const asRecordArray = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value) ? value.filter(isRecord) : [];

const asText = (value: unknown): string | null =>
  typeof value === "string" && value.trim() !== "" ? value.trim() : null;

const toJson = (value: unknown): string => JSON.stringify(value, null, 2);

const pluralize = (count: number, singular: string, plural = `${singular}s`): string =>
  `${count} ${count === 1 ? singular : plural}`;

const truncate = (value: string, max = 72): string =>
  value.length <= max ? value : `${value.slice(0, Math.max(0, max - 1)).trimEnd()}...`;

const formatGroupLabel = (key: string): string => formatNextCheckInputLabel(key).replace(/\bUrl\b/g, "URL");

const formatDateTime = (value: string): string => {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    month: "short",
    year: "numeric",
  });
};

const formatPrimitiveValue = (value: unknown): string => {
  if (value === null || value === undefined || value === "") return "Not supplied";
  if (typeof value === "string") {
    return /^\d{4}-\d{2}-\d{2}T/.test(value) ? formatDateTime(value) : value;
  }
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
};

const formatReadableValue = (value: unknown): string => {
  if (Array.isArray(value)) {
    if (value.length === 0) return "None";
    if (value.every((item) => item === null || ["string", "number", "boolean"].includes(typeof item))) {
      return value.map(formatPrimitiveValue).join(", ");
    }
    return pluralize(value.length, "record");
  }

  if (isRecord(value)) {
    const title = asText(value["title"]) ?? asText(value["name"]) ?? asText(value["caption"]) ?? asText(value["id"]);
    const fieldCount = Object.keys(value).length;
    return title === null ? `${fieldCount} fields` : `${title} (${pluralize(fieldCount, "field")})`;
  }

  return formatPrimitiveValue(value);
};

const formatFieldValue = (key: string, value: unknown): string => {
  if (key === "triage" && isRecord(value)) {
    const keywords = Array.isArray(value["matchedKeywords"])
      ? value["matchedKeywords"].filter((item): item is string => typeof item === "string")
      : [];
    const noticeType = asText(value["officialNoticeType"]);
    const requiresReview = value["requiresAnalystReview"] === true ? "requires analyst review" : null;
    return [noticeType, keywords.length === 0 ? null : `matched ${keywords.join(", ")}`, requiresReview]
      .filter((item): item is string => item !== null)
      .join("; ") || formatReadableValue(value);
  }

  if (key === "properties" && isRecord(value)) {
    const names = Array.isArray(value["name"]) ? value["name"].filter((item): item is string => typeof item === "string") : [];
    const countries = Array.isArray(value["country"]) ? value["country"].filter((item): item is string => typeof item === "string") : [];
    return [names[0], countries.length === 0 ? null : countries.join(", ")]
      .filter((item): item is string => item !== null && item !== undefined)
      .join("; ") || formatReadableValue(value);
  }

  return formatReadableValue(value);
};

const getBriefArtifact = (value: unknown): BriefArtifactLike | null => {
  if (!isRecord(value) || typeof value["title"] !== "string" || !isRecord(value["records"])) return null;
  return {
    title: value["title"],
    summary: Array.isArray(value["summary"]) ? value["summary"].filter(isSummaryItem) : [],
    evidence: Array.isArray(value["evidence"]) ? value["evidence"].filter(isSummaryItem) : [],
    records: value["records"],
    gaps: Array.isArray(value["gaps"]) ? value["gaps"].filter((item): item is EvidenceGap =>
      isRecord(item) && typeof item["code"] === "string" && typeof item["message"] === "string") : [],
    provenance: Array.isArray(value["provenance"]) ? value["provenance"].filter((item): item is BriefProvenanceItem =>
      isRecord(item)
      && typeof item["source"] === "string"
      && typeof item["tool"] === "string"
      && typeof item["coverage"] === "string"
      && typeof item["authRequired"] === "boolean"
      && typeof item["recordCount"] === "number") : [],
    freshness: Array.isArray(value["freshness"]) ? value["freshness"].filter((item): item is BriefFreshnessItem =>
      isRecord(item) && typeof item["source"] === "string" && typeof item["observedAt"] === "string") : [],
    limits: Array.isArray(value["limits"]) ? value["limits"].filter((item): item is BriefLimit =>
      isRecord(item) && typeof item["code"] === "string" && typeof item["message"] === "string") : [],
    riskFlags: Array.isArray(value["riskFlags"]) ? value["riskFlags"].filter((item): item is RiskFlag =>
      isRecord(item)
      && typeof item["code"] === "string"
      && typeof item["severity"] === "string"
      && typeof item["message"] === "string"
      && typeof item["source"] === "string") : [],
  };
};

const getRelationshipGraph = (records: Record<string, unknown>): RelationshipGraph | null => {
  const graph = records["graph"];
  if (!isRecord(graph) || !Array.isArray(graph["nodes"]) || !Array.isArray(graph["edges"])) return null;

  const nodes = graph["nodes"].filter((node): node is GraphNode =>
    isRecord(node)
    && typeof node["id"] === "string"
    && typeof node["label"] === "string"
    && typeof node["kind"] === "string");
  const edges = graph["edges"].filter((edge): edge is GraphEdge =>
    isRecord(edge)
    && typeof edge["from"] === "string"
    && typeof edge["to"] === "string"
    && typeof edge["kind"] === "string");

  return { edges, nodes };
};

function JsonCopyButton({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      if (typeof navigator === "undefined" || navigator.clipboard === undefined) {
        throw new Error("Clipboard unavailable.");
      }
      await navigator.clipboard.writeText(toJson(value));
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };

  return (
    <Button
      className="w-fit"
      onClick={() => void handleCopy()}
      size="sm"
      type="button"
      variant="outline"
    >
      <Copy aria-hidden="true" className="mr-2 h-4 w-4" />
      {copied ? "Copied" : label}
    </Button>
  );
}

function SectionFrame({
  action,
  children,
  title,
}: {
  action?: ReactNode;
  children: ReactNode;
  title: string;
}) {
  return (
    <section className="rounded-md border border-border bg-background p-3">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs font-medium uppercase text-muted-foreground">{title}</p>
        {action}
      </div>
      <div className="mt-3">{children}</div>
    </section>
  );
}

function SummaryGrid({
  emptyText,
  items,
  title,
}: {
  emptyText: string;
  items: readonly SummaryItem[];
  title: string;
}) {
  if (items.length === 0) {
    return (
      <SectionFrame title={title}>
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      </SectionFrame>
    );
  }

  return (
    <SectionFrame title={title}>
      <dl className="grid gap-2 sm:grid-cols-2">
        {items.map((item) => (
          <div className="min-w-0 rounded-md border border-border bg-muted/20 p-3" key={`${item.label}-${String(item.value)}`}>
            <dt className="text-xs font-medium uppercase text-muted-foreground">{item.label}</dt>
            <dd className="mt-1 break-words text-sm font-semibold text-foreground">{formatReadableValue(item.value)}</dd>
            {item.source === null || item.source === undefined || item.source === "" ? null : (
              <dd className="mt-1 text-xs text-muted-foreground">{item.source}</dd>
            )}
          </div>
        ))}
      </dl>
    </SectionFrame>
  );
}

export function FollowUpInputView({ input }: { input: Record<string, unknown> }) {
  const entries = getNextCheckInputEntries(input);
  return (
    <SectionFrame
      action={<JsonCopyButton label="Copy input JSON" value={input} />}
      title="Input"
    >
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No suggested input was supplied.</p>
      ) : (
        <dl className="grid gap-2 sm:grid-cols-2">
          {entries.map(([key, value]) => (
            <div className="min-w-0" key={key}>
              <dt className="text-xs font-semibold uppercase text-muted-foreground">
                {formatNextCheckInputLabel(key)}
              </dt>
              <dd className="mt-1 break-words text-sm leading-6 text-foreground">
                {key === "records" && isRecord(value)
                  ? `Dossier records (${pluralize(Object.keys(value).length, "group")})`
                  : formatNextCheckInputValue(value)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </SectionFrame>
  );
}

function layoutGraphNodes(nodes: readonly GraphNode[]): { readonly height: number; readonly nodes: readonly LayoutNode[]; readonly width: number } {
  const width = 760;
  const primary = nodes.filter((node) => node.kind !== "address");
  const secondary = nodes.filter((node) => node.kind === "address");
  const maxRows = Math.max(primary.length || nodes.length, secondary.length, 1);
  const height = Math.max(220, Math.min(560, 72 + maxRows * 78));
  const distributeY = (count: number, index: number): number => {
    if (count <= 1) return height / 2;
    const top = 56;
    const bottom = height - 56;
    return top + ((bottom - top) * index) / (count - 1);
  };

  if (secondary.length > 0 && primary.length > 0) {
    return {
      height,
      width,
      nodes: [
        ...primary.map((node, index) => ({ ...node, x: 155, y: distributeY(primary.length, index) })),
        ...secondary.map((node, index) => ({ ...node, x: 585, y: distributeY(secondary.length, index) })),
      ],
    };
  }

  const centerX = width / 2;
  const centerY = height / 2;
  const radius = Math.min(250, Math.max(82, nodes.length * 25));
  return {
    height,
    width,
    nodes: nodes.map((node, index) => {
      const angle = nodes.length <= 1 ? 0 : (-Math.PI / 2) + ((2 * Math.PI * index) / nodes.length);
      return {
        ...node,
        x: centerX + Math.cos(angle) * radius,
        y: centerY + Math.sin(angle) * Math.min(radius, height / 2 - 56),
      };
    }),
  };
}

function nodeToneClassName(kind: string): string {
  if (kind === "address") return "fill-amber-50 stroke-amber-200";
  if (kind === "person") return "fill-sky-50 stroke-sky-200";
  if (kind === "company") return "fill-slate-50 stroke-slate-300";
  return "fill-background stroke-border";
}

function RelationshipGraphView({ graph }: { graph: RelationshipGraph }) {
  const layout = useMemo(() => layoutGraphNodes(graph.nodes.slice(0, 24)), [graph.nodes]);
  const nodeById = new Map(layout.nodes.map((node) => [node.id, node]));
  const visibleEdges = graph.edges
    .map((edge) => ({ edge, from: nodeById.get(edge.from), to: nodeById.get(edge.to) }))
    .filter((item): item is { edge: GraphEdge; from: LayoutNode; to: LayoutNode } =>
      item.from !== undefined && item.to !== undefined);

  return (
    <SectionFrame
      action={<JsonCopyButton label="Copy graph JSON" value={graph} />}
      title="Relationship diagram"
    >
      {graph.nodes.length === 0 ? (
        <p className="text-sm text-muted-foreground">No graph nodes were returned.</p>
      ) : (
        <div className="space-y-3">
          <div className="overflow-x-auto rounded-md border border-border bg-muted/20">
            <svg
              aria-label="Relationship graph diagram"
              className="block min-w-[720px]"
              role="img"
              viewBox={`0 0 ${layout.width} ${layout.height}`}
            >
              <defs>
                <marker id="follow-up-graph-arrow" markerHeight="8" markerWidth="8" orient="auto" refX="7" refY="3.5">
                  <path className="fill-muted-foreground" d="M0,0 L7,3.5 L0,7 Z" />
                </marker>
              </defs>
              {visibleEdges.map(({ edge, from, to }, index) => {
                const dx = to.x - from.x;
                const dy = to.y - from.y;
                const length = Math.max(Math.sqrt(dx * dx + dy * dy), 1);
                const startX = from.x + (dx / length) * 92;
                const startY = from.y + (dy / length) * 28;
                const endX = to.x - (dx / length) * 92;
                const endY = to.y - (dy / length) * 28;
                return (
                  <g key={`${edge.from}-${edge.to}-${edge.kind}-${index}`}>
                    <line
                      className="stroke-muted-foreground/60"
                      markerEnd="url(#follow-up-graph-arrow)"
                      strokeDasharray={edge.confidence === "heuristic" ? "5 5" : undefined}
                      strokeWidth="1.5"
                      x1={startX}
                      x2={endX}
                      y1={startY}
                      y2={endY}
                    >
                      <title>{`${edge.kind}${edge.confidence === undefined ? "" : ` (${edge.confidence})`}`}</title>
                    </line>
                  </g>
                );
              })}
              {layout.nodes.map((node) => (
                <g key={node.id} transform={`translate(${node.x - 88} ${node.y - 27})`}>
                  <rect
                    className={nodeToneClassName(node.kind)}
                    height="54"
                    rx="8"
                    width="176"
                  />
                  <text className="fill-muted-foreground" fontSize="10" fontWeight="700" x="12" y="18">
                    {node.kind.toUpperCase()}
                  </text>
                  <text className="fill-foreground" fontSize="12" fontWeight="700" x="12" y="36">
                    {truncate(node.label, 24)}
                  </text>
                  <title>{`${node.label}${node.source === undefined ? "" : ` (${node.source})`}`}</title>
                </g>
              ))}
            </svg>
          </div>
          <div className="grid gap-2">
            <p className="text-xs font-medium uppercase text-muted-foreground">
              Edges ({graph.edges.length})
            </p>
            {graph.edges.length === 0 ? (
              <p className="text-sm text-muted-foreground">No graph edges were returned.</p>
            ) : (
              graph.edges.slice(0, 8).map((edge, index) => {
                const from = graph.nodes.find((node) => node.id === edge.from)?.label ?? edge.from;
                const to = graph.nodes.find((node) => node.id === edge.to)?.label ?? edge.to;
                return (
                  <article className="rounded-md border border-border bg-muted/20 p-3" key={`${edge.from}-${edge.to}-${index}`}>
                    <p className="text-sm font-medium text-foreground">{from}{" -> "}{to}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {formatGroupLabel(edge.kind)}
                      {edge.confidence === undefined ? "" : ` - ${formatGroupLabel(edge.confidence)}`}
                    </p>
                    {edge.evidence === undefined ? null : (
                      <p className="mt-2 text-xs leading-5 text-muted-foreground">{edge.evidence}</p>
                    )}
                  </article>
                );
              })
            )}
          </div>
        </div>
      )}
    </SectionFrame>
  );
}

const recordTitleKeys = ["title", "name", "caption", "company_name", "companyNumber", "company_number", "id"];
const recordUrlKeys = ["url", "link", "opencorporates_url", "sourceUrl"];
const detailPriority = [
  "company_number",
  "jurisdiction_code",
  "current_status",
  "agency",
  "feedId",
  "publishedAt",
  "confidence",
  "triage",
  "score",
  "schema",
  "id",
  "source",
  "sourceRegistry",
];

function getRecordTitle(record: Record<string, unknown>, fallback: string): string {
  for (const key of recordTitleKeys) {
    const value = asText(record[key]);
    if (value !== null) return value;
  }
  return fallback;
}

function getRecordUrl(record: Record<string, unknown>): string | null {
  for (const key of recordUrlKeys) {
    const value = asText(record[key]);
    if (value !== null && /^https?:\/\//i.test(value)) return value;
  }
  return null;
}

function recordDetailEntries(record: Record<string, unknown>): [string, unknown][] {
  const excluded = new Set([...recordTitleKeys, ...recordUrlKeys, "description"]);
  return Object.entries(record)
    .filter(([key, value]) => !excluded.has(key) && value !== null && value !== undefined && value !== "")
    .sort(([left], [right]) => {
      const leftIndex = detailPriority.indexOf(left);
      const rightIndex = detailPriority.indexOf(right);
      if (leftIndex === -1 && rightIndex === -1) return left.localeCompare(right);
      if (leftIndex === -1) return 1;
      if (rightIndex === -1) return -1;
      return leftIndex - rightIndex;
    })
    .slice(0, 6);
}

function RecordList({
  label,
  value,
}: {
  label: string;
  value: unknown;
}) {
  const records = asRecordArray(value);
  const count = Array.isArray(value) ? value.length : records.length;
  return (
    <section className="space-y-2">
      <div className="flex min-w-0 items-center justify-between gap-2">
        <h4 className="text-sm font-semibold text-foreground">{formatGroupLabel(label)}</h4>
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-xs text-muted-foreground">
          {pluralize(count, "record")}
        </span>
      </div>
      {records.length === 0 ? (
        <p className="rounded-md border border-border bg-muted/20 p-3 text-sm text-muted-foreground">
          No {formatGroupLabel(label).toLowerCase()} returned.
        </p>
      ) : (
        <div className="grid gap-2">
          {records.slice(0, 6).map((record, index) => {
            const title = getRecordTitle(record, `Record ${index + 1}`);
            const url = getRecordUrl(record);
            const detailEntries = recordDetailEntries(record);
            return (
              <article className="rounded-md border border-border bg-muted/20 p-3" key={`${label}-${index}-${title}`}>
                <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                  <h5 className="break-words text-sm font-semibold text-foreground">{title}</h5>
                  {url === null ? null : (
                    <a
                      className="w-fit shrink-0 text-xs font-medium text-primary underline underline-offset-4"
                      href={url}
                      rel="noreferrer"
                      target="_blank"
                    >
                      Source
                    </a>
                  )}
                </div>
                {asText(record["description"]) === null ? null : (
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">{truncate(asText(record["description"])!, 180)}</p>
                )}
                {detailEntries.length === 0 ? null : (
                  <dl className="mt-3 grid gap-2 sm:grid-cols-2">
                    {detailEntries.map(([key, detailValue]) => (
                      <div className="min-w-0" key={key}>
                        <dt className="text-[11px] font-semibold uppercase text-muted-foreground">{formatGroupLabel(key)}</dt>
                        <dd className="mt-0.5 break-words text-xs leading-5 text-muted-foreground">
                          {formatFieldValue(key, detailValue)}
                        </dd>
                      </div>
                    ))}
                  </dl>
                )}
              </article>
            );
          })}
          {records.length > 6 ? (
            <p className="text-xs text-muted-foreground">
              Showing 6 of {records.length}. Use copy JSON for the full result.
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}

function ObjectRecordView({
  label,
  value,
}: {
  label: string;
  value: Record<string, unknown>;
}) {
  const entries = Object.entries(value);
  return (
    <section className="space-y-2">
      <h4 className="text-sm font-semibold text-foreground">{formatGroupLabel(label)}</h4>
      {entries.length === 0 ? (
        <p className="text-sm text-muted-foreground">No fields returned.</p>
      ) : (
        <dl className="grid gap-2 sm:grid-cols-2">
          {entries.map(([key, item]) => (
            <div className="min-w-0" key={key}>
              <dt className="text-[11px] font-semibold uppercase text-muted-foreground">{formatGroupLabel(key)}</dt>
              <dd className="mt-0.5 break-words text-xs leading-5 text-muted-foreground">
                {formatFieldValue(key, item)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function RecordsView({ records }: { records: Record<string, unknown> }) {
  const entries = Object.entries(records).filter(([key]) => key !== "graph");
  if (entries.length === 0) return null;

  return (
    <SectionFrame title="Records">
      <div className="grid gap-4">
        {entries.map(([key, value]) => {
          if (Array.isArray(value)) return <RecordList key={key} label={key} value={value} />;
          if (isRecord(value)) return <ObjectRecordView key={key} label={key} value={value} />;
          return (
            <div key={key}>
              <p className="text-sm font-semibold text-foreground">{formatGroupLabel(key)}</p>
              <p className="mt-1 text-sm text-muted-foreground">{formatReadableValue(value)}</p>
            </div>
          );
        })}
      </div>
    </SectionFrame>
  );
}

function DetailList({
  emptyText,
  items,
  renderItem,
  title,
}: {
  emptyText: string;
  items: readonly unknown[];
  renderItem: (item: unknown, index: number) => ReactNode;
  title: string;
}) {
  return (
    <SectionFrame title={title}>
      {items.length === 0 ? (
        <p className="text-sm text-muted-foreground">{emptyText}</p>
      ) : (
        <div className="grid gap-2">{items.map(renderItem)}</div>
      )}
    </SectionFrame>
  );
}

function BriefArtifactView({ artifact }: { artifact: BriefArtifactLike }) {
  const graph = getRelationshipGraph(artifact.records);

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-semibold text-foreground">{artifact.title}</p>
        <p className="mt-1 text-sm leading-6 text-muted-foreground">
          Source-backed follow-up output. Treat supplemental matches as analyst-review evidence only.
        </p>
      </div>
      <SummaryGrid emptyText="No summary metrics returned." items={artifact.summary} title="Summary" />
      {graph === null ? null : <RelationshipGraphView graph={graph} />}
      <SummaryGrid emptyText="No evidence metrics returned." items={artifact.evidence} title="Evidence" />
      <RecordsView records={artifact.records} />
      <DetailList
        emptyText="No gaps returned."
        items={artifact.gaps}
        renderItem={(item, index) => {
          const gap = item as EvidenceGap;
          return (
            <article className="rounded-md border border-border bg-muted/20 p-3" key={`${gap.code}-${index}`}>
              <p className="text-sm font-semibold text-foreground">{gap.code}</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{gap.message}</p>
            </article>
          );
        }}
        title="Gaps"
      />
      <DetailList
        emptyText="No limits returned."
        items={artifact.limits}
        renderItem={(item, index) => {
          const limit = item as BriefLimit;
          return (
            <article className="rounded-md border border-border bg-muted/20 p-3" key={`${limit.code}-${index}`}>
              <p className="text-sm font-semibold text-foreground">{limit.code}</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{limit.message}</p>
            </article>
          );
        }}
        title="Limits"
      />
      {artifact.riskFlags === undefined || artifact.riskFlags.length === 0 ? null : (
        <DetailList
          emptyText="No risk flags returned."
          items={artifact.riskFlags}
          renderItem={(item, index) => {
            const flag = item as RiskFlag;
            return (
              <article className="rounded-md border border-border bg-muted/20 p-3" key={`${flag.code}-${index}`}>
                <div className="flex min-w-0 items-center justify-between gap-2">
                  <p className="text-sm font-semibold text-foreground">{flag.code}</p>
                  <span className="shrink-0 rounded-full border border-border bg-background px-2 py-0.5 text-xs text-muted-foreground">
                    {flag.severity}
                  </span>
                </div>
                <p className="mt-1 text-xs leading-5 text-muted-foreground">{flag.message}</p>
                <p className="mt-1 text-xs text-muted-foreground">{flag.source}</p>
              </article>
            );
          }}
          title="Risk flags"
        />
      )}
      <DetailList
        emptyText="No provenance returned."
        items={artifact.provenance}
        renderItem={(item, index) => {
          const provenance = item as BriefProvenanceItem;
          return (
            <article className="rounded-md border border-border bg-muted/20 p-3" key={`${provenance.source}-${index}`}>
              <div className="flex min-w-0 flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                <p className="text-sm font-semibold text-foreground">{provenance.source}</p>
                <span className="w-fit shrink-0 rounded-full bg-background px-2 py-0.5 text-xs text-muted-foreground">
                  {pluralize(provenance.recordCount, "record")}
                </span>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{provenance.coverage}</p>
              <p className="mt-1 font-mono text-xs text-muted-foreground">{provenance.tool}</p>
              {provenance.sourceUrl === undefined ? null : (
                <a className="mt-2 inline-flex text-xs font-medium text-primary underline underline-offset-4" href={provenance.sourceUrl} rel="noreferrer" target="_blank">
                  Source documentation
                </a>
              )}
            </article>
          );
        }}
        title="Provenance"
      />
      <DetailList
        emptyText="No freshness timestamps returned."
        items={artifact.freshness}
        renderItem={(item, index) => {
          const freshness = item as BriefFreshnessItem;
          return (
            <article className="rounded-md border border-border bg-muted/20 p-3" key={`${freshness.source}-${index}`}>
              <p className="text-sm font-semibold text-foreground">{freshness.source}</p>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">
                Observed {formatDateTime(freshness.observedAt)}
                {freshness.upstreamTimestamp === null || freshness.upstreamTimestamp === undefined
                  ? ""
                  : `; upstream ${formatDateTime(freshness.upstreamTimestamp)}`}
              </p>
            </article>
          );
        }}
        title="Freshness"
      />
    </div>
  );
}

function GenericResultView({ result }: { result: unknown }) {
  if (isRecord(result)) {
    return (
      <SectionFrame title="Result">
        <ObjectRecordView label="payload" value={result} />
      </SectionFrame>
    );
  }

  return (
    <SectionFrame title="Result">
      <p className="break-words text-sm text-muted-foreground">{formatReadableValue(result)}</p>
    </SectionFrame>
  );
}

export function FollowUpResultView({ result }: { result: unknown }) {
  const artifact = getBriefArtifact(result);

  return (
    <section className="space-y-3">
      <div className="flex min-w-0 flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs font-medium uppercase text-muted-foreground">Result</p>
        <JsonCopyButton label="Copy result JSON" value={result} />
      </div>
      {artifact === null ? <GenericResultView result={result} /> : <BriefArtifactView artifact={artifact} />}
      <details className="rounded-md border border-border bg-muted/20 p-3">
        <summary className="cursor-pointer text-sm font-medium text-foreground">Raw JSON</summary>
        <pre className="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-words text-xs leading-5 text-muted-foreground">
          {toJson(result)}
        </pre>
      </details>
    </section>
  );
}
