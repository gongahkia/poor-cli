import Link from "next/link";
import { askResearch, getResearchConversation, getResearchConfig } from "../../lib/api-server";

type SourceType = "statute" | "glossary" | "case_law" | "treaty";

type CitationItem = {
  citation: string;
  type: string;
  in_context: boolean;
  exists_in_index: boolean;
  position: [number, number];
};

type AskResponse = {
  answer: string;
  sources: Array<{
    source_id: string;
    source_type: string;
    text_snippet: string;
    metadata: Record<string, unknown>;
    relevance_score: number;
  }>;
  citations: {
    citations: CitationItem[];
    total_citations: number;
    verified_citations: number;
    hallucinated_citations: CitationItem[];
    citation_rate: number;
  };
  conversation_id: string;
};

type ConversationTurn = {
  role: string;
  content: string;
  sources?: Array<{
    source_id: string;
    source_type: string;
    text_snippet: string;
    metadata: Record<string, unknown>;
    relevance_score: number;
  }>;
  citations?: {
    citations?: CitationItem[];
    total_citations?: number;
    verified_citations?: number;
    hallucinated_citations?: CitationItem[];
    citation_rate?: number;
  };
  created_at?: string;
};

type ConversationResponse = {
  conversation_id: string;
  turns: ConversationTurn[];
};

type ConfigResponse = {
  provider: string;
  model: string;
  available_sources: string[];
  max_context_chunks: number;
};

const defaultSources: SourceType[] = ["statute", "glossary"];

function isSourceType(value: string): value is SourceType {
  return value === "statute" || value === "glossary" || value === "case_law" || value === "treaty";
}

function normalizeSources(raw: string | string[] | undefined): SourceType[] {
  if (Array.isArray(raw)) {
    const values = raw.filter((item): item is SourceType => isSourceType(item));
    return values.length > 0 ? values : defaultSources;
  }
  if (typeof raw === "string" && isSourceType(raw)) {
    return [raw];
  }
  return defaultSources;
}

function citationHref(citation: string): string | null {
  const orsMatch = citation.match(/^ORS\s+([0-9A-Z]+\.[0-9]+)/i);
  if (orsMatch) {
    return `/statutes/section/${encodeURIComponent(orsMatch[1])}`;
  }

  const glossaryMatch = citation.match(/: "([^"]+)"$/);
  if (glossaryMatch) {
    return `/glossary/${encodeURIComponent(glossaryMatch[1])}`;
  }

  const treatyMatch = citation.match(/^Rome Statute Art\.?\s+([0-9A-Za-z.\-]+)/i);
  if (treatyMatch) {
    return `/rome-statute/article/${encodeURIComponent(treatyMatch[1])}`;
  }

  return null;
}

async function askQuestion(
  question: string,
  sources: SourceType[],
  topK: number,
  conversationId: string | null,
): Promise<{ result: AskResponse | null; error: string | null }> {
  const res = await askResearch(question, sources, topK, conversationId ?? undefined);
  if (res?.error) return { result: null, error: res.error };
  return { result: res as AskResponse, error: null };
}

export default async function ResearchPage({
  searchParams,
}: {
  searchParams?: {
    question?: string;
    conversation_id?: string;
    sources?: string | string[];
    top_k?: string;
    run?: "0" | "1";
  };
}) {
  const question = (searchParams?.question ?? "").trim();
  const conversationIdInput = (searchParams?.conversation_id ?? "").trim();
  const topK = Math.min(12, Math.max(1, Number(searchParams?.top_k ?? "8") || 8));
  const selectedSources = normalizeSources(searchParams?.sources);
  const shouldRun = searchParams?.run === "1";

  const askResult =
    shouldRun && question
      ? await askQuestion(question, selectedSources, topK, conversationIdInput || null)
      : { result: null as AskResponse | null, error: null as string | null };

  const activeConversationId = askResult.result?.conversation_id ?? (conversationIdInput || null);
  const [conversation, config]: [ConversationResponse | null, ConfigResponse | null] = await Promise.all([
    activeConversationId
      ? (getResearchConversation(activeConversationId) as Promise<ConversationResponse | null>)
      : Promise.resolve(null),
    getResearchConfig() as Promise<ConfigResponse | null>,
  ]);

  const availableSources = (config?.available_sources ?? ["statute", "glossary", "case_law", "treaty"]).filter(
    (source: string): source is SourceType => isSourceType(source),
  );
  const turns = conversation?.turns ?? [];
  const latestAssistant = [...turns].reverse().find((turn) => turn.role === "assistant") ?? null;
  const latestSources = askResult.result?.sources ?? latestAssistant?.sources ?? [];
  const latestCitations = askResult.result?.citations ?? latestAssistant?.citations ?? null;

  return (
    <section className="research-grid">
      <div>
        <h2>Legal Research Assistant</h2>
        <p>Ask legal questions grounded in statutes, glossary definitions, case law, and Rome Statute treaty text.</p>

        <form method="get" action="/research" className="ner-form">
          <input type="hidden" name="run" value="1" />
          {activeConversationId ? <input type="hidden" name="conversation_id" value={activeConversationId} /> : null}

          <label htmlFor="question">Question</label>
          <textarea
            id="question"
            name="question"
            rows={5}
            defaultValue={question}
            placeholder="What constitutes genocide under the Rome Statute?"
          />

          <label htmlFor="top_k">Context chunks</label>
          <input id="top_k" name="top_k" type="number" min={1} max={12} defaultValue={topK} />

          <div className="chip-row">
            {availableSources.includes("statute") ? (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  name="sources"
                  value="statute"
                  defaultChecked={selectedSources.includes("statute")}
                />
                Statutes
              </label>
            ) : null}
            {availableSources.includes("glossary") ? (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  name="sources"
                  value="glossary"
                  defaultChecked={selectedSources.includes("glossary")}
                />
                Glossary
              </label>
            ) : null}
            {availableSources.includes("case_law") ? (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  name="sources"
                  value="case_law"
                  defaultChecked={selectedSources.includes("case_law")}
                />
                Case law
              </label>
            ) : null}
            {availableSources.includes("treaty") ? (
              <label className="checkbox-row">
                <input
                  type="checkbox"
                  name="sources"
                  value="treaty"
                  defaultChecked={selectedSources.includes("treaty")}
                />
                Rome Statute
              </label>
            ) : null}
          </div>

          <div className="chip-row">
            <button type="submit">Ask</button>
            <Link href="/research" className="chip">
              New Conversation
            </Link>
          </div>
        </form>

        {askResult.error ? (
          <article className="result-card">
            <h3>Request failed</h3>
            <p>{askResult.error}</p>
          </article>
        ) : null}

        <div className="chat-thread">
          {turns.length === 0 ? (
            <p>Submit a question to begin a conversation.</p>
          ) : (
            turns.map((turn, index) => (
              <article
                key={`${turn.role}-${index}-${turn.created_at ?? ""}`}
                className={`chat-message ${turn.role === "user" ? "chat-user" : "chat-assistant"}`}
              >
                <p className="meta-line">{turn.role === "user" ? "You" : "Junas"}</p>
                <p>{turn.content}</p>
              </article>
            ))
          )}
        </div>
      </div>

      <aside>
        <h3>Conversation</h3>
        <ul className="chapter-list">
          <li>conversation_id: {activeConversationId ?? "-"}</li>
          <li>turns: {turns.length}</li>
          <li>llm: {config ? `${config.provider} / ${config.model}` : "-"}</li>
        </ul>

        <h3>Citation Report</h3>
        {latestCitations ? (
          <>
            <ul className="chapter-list">
              <li>total: {latestCitations.total_citations ?? 0}</li>
              <li>verified: {latestCitations.verified_citations ?? 0}</li>
              <li>hallucinated: {(latestCitations.hallucinated_citations ?? []).length}</li>
            </ul>

            <ul className="chapter-list">
              {(latestCitations.citations ?? []).map((item, index) => {
                const href = citationHref(item.citation);
                const statusClass =
                  item.exists_in_index && item.in_context
                    ? "citation-ok"
                    : item.exists_in_index
                      ? "citation-warn"
                      : "citation-bad";

                return (
                  <li key={`${item.citation}-${index}`} className={statusClass}>
                    {href ? <Link href={href}>{item.citation}</Link> : item.citation}
                  </li>
                );
              })}
            </ul>
          </>
        ) : (
          <p>No citations yet.</p>
        )}

        <h3>Retrieved Sources</h3>
        {latestSources.length === 0 ? (
          <p>No source chunks yet.</p>
        ) : (
          <ul className="results-list">
            {latestSources.map((source) => (
              <li key={`${source.source_type}-${source.source_id}`} className="result-card">
                <div className="result-header">
                  <strong>{source.source_id}</strong>
                  <span className="badge">{source.source_type}</span>
                </div>
                <p>{source.text_snippet.slice(0, 220)}...</p>
                <p className="meta-line">score: {source.relevance_score.toFixed(4)}</p>
              </li>
            ))}
          </ul>
        )}
      </aside>
    </section>
  );
}
