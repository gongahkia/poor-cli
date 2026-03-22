import type { QueryPlan } from "./planner.js";

const CONTEXT_TTL = 300000; // WHY: 5 minutes — after this, context is stale

export class ConversationContext {
  private lastQuery: string | null = null;
  private lastPlan: QueryPlan | null = null;
  private lastParams: Record<string, unknown> = {};
  private lastTimestamp = 0;

  update(query: string, plan: QueryPlan, params: Readonly<Record<string, unknown>>): void {
    this.lastQuery = query;
    this.lastPlan = plan;
    this.lastParams = { ...params };
    this.lastTimestamp = Date.now();
  }

  resolve(query: string): Record<string, unknown> {
    if (this.isExpired()) {
      return {};
    }

    // Merge current params with previous for follow-up queries
    const isFollowUp = /^(how about|what about|and |for |show me )/i.test(query.trim());
    if (isFollowUp && this.lastParams !== null) {
      return { ...this.lastParams };
    }

    return {};
  }

  getLastQuery(): string | null {
    if (this.isExpired()) return null;
    return this.lastQuery;
  }

  getLastPlan(): QueryPlan | null {
    if (this.isExpired()) return null;
    return this.lastPlan;
  }

  private isExpired(): boolean {
    return Date.now() - this.lastTimestamp > CONTEXT_TTL;
  }
}
