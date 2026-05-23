const TEMPLATE = document.createElement("template");

TEMPLATE.innerHTML = `
  <style>
    :host {
      --swee-widget-accent: #0f766e;
      --swee-widget-accent-contrast: #ffffff;
      --swee-widget-border: #d8e0ec;
      --swee-widget-muted: #64748b;
      --swee-widget-surface: #ffffff;
      --swee-widget-text: #111827;
      display: block;
      color: var(--swee-widget-text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .shell {
      border: 1px solid var(--swee-widget-border);
      border-radius: 8px;
      background: var(--swee-widget-surface);
      padding: 16px;
      max-width: 720px;
    }

    .brand {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 12px;
    }

    .brand strong {
      font-size: 15px;
      letter-spacing: 0;
    }

    form {
      display: grid;
      grid-template-columns: minmax(0, 1fr) auto;
      gap: 8px;
    }

    input {
      min-width: 0;
      border: 1px solid var(--swee-widget-border);
      border-radius: 6px;
      color: var(--swee-widget-text);
      font: inherit;
      padding: 10px 12px;
    }

    button {
      border: 0;
      border-radius: 6px;
      background: var(--swee-widget-accent);
      color: var(--swee-widget-accent-contrast);
      cursor: pointer;
      font: inherit;
      font-weight: 700;
      padding: 10px 14px;
      white-space: nowrap;
    }

    button:disabled {
      cursor: wait;
      opacity: 0.68;
    }

    .status,
    .limits,
    .freshness {
      color: var(--swee-widget-muted);
      font-size: 13px;
      line-height: 1.45;
      margin-top: 10px;
    }

    .error {
      color: #b42318;
    }

    .result {
      display: grid;
      gap: 12px;
      margin-top: 14px;
    }

    .summary {
      display: grid;
      gap: 8px;
    }

    .row {
      border-top: 1px solid var(--swee-widget-border);
      display: grid;
      gap: 3px;
      padding-top: 8px;
    }

    .row span {
      color: var(--swee-widget-muted);
      font-size: 12px;
      text-transform: uppercase;
    }

    .row strong {
      font-size: 14px;
      overflow-wrap: anywhere;
    }

    .badges {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
    }

    .badge {
      background: #eef2f7;
      border-radius: 999px;
      color: #334155;
      font-size: 12px;
      padding: 4px 8px;
    }

    @media (max-width: 520px) {
      .shell {
        padding: 12px;
      }

      form {
        grid-template-columns: 1fr;
      }

      button {
        width: 100%;
      }
    }
  </style>
  <section class="shell">
    <div class="brand">
      <strong data-brand>Swee Pulse</strong>
      <span class="badge" data-mode>Source backed</span>
    </div>
    <form>
      <input data-input autocomplete="off" placeholder="Optional area, e.g. Bedok" />
      <button type="submit" data-submit>Refresh</button>
    </form>
    <div class="status" data-status>Load source-backed Pulse signals for Singapore.</div>
    <div class="result" data-result hidden></div>
  </section>
`;

const FOCUS_VALUES = new Set(["all", "mobility", "weather"]);

const normalizeFocus = (value) => {
  const focus = String(value || "all").trim().toLowerCase();
  return FOCUS_VALUES.has(focus) ? focus : "all";
};

const text = (value) => {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }
  return String(value);
};

class SweePulseWidget extends HTMLElement {
  static observedAttributes = [
    "api-token",
    "area",
    "brand-name",
    "focus",
    "gateway-url",
    "theme",
  ];

  #input;
  #status;
  #submit;
  #result;
  #brand;
  #abortController = null;

  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.shadowRoot.appendChild(TEMPLATE.content.cloneNode(true));
    this.#input = this.shadowRoot.querySelector("[data-input]");
    this.#status = this.shadowRoot.querySelector("[data-status]");
    this.#submit = this.shadowRoot.querySelector("[data-submit]");
    this.#result = this.shadowRoot.querySelector("[data-result]");
    this.#brand = this.shadowRoot.querySelector("[data-brand]");
  }

  connectedCallback() {
    this.shadowRoot.querySelector("form").addEventListener("submit", this.#handleSubmit);
    this.#syncAttributes();
    void this.run();
  }

  disconnectedCallback() {
    this.shadowRoot.querySelector("form").removeEventListener("submit", this.#handleSubmit);
    this.#abortController?.abort();
  }

  attributeChangedCallback() {
    this.#syncAttributes();
  }

  set authToken(value) {
    if (typeof value === "string" && value.trim() !== "") {
      this.setAttribute("api-token", value);
    } else {
      this.removeAttribute("api-token");
    }
  }

  get authToken() {
    return this.getAttribute("api-token") ?? "";
  }

  async run() {
    this.#abortController?.abort();
    this.#abortController = new AbortController();
    this.#submit.disabled = true;
    this.#setStatus("Loading Pulse signals...");
    this.#result.hidden = true;
    this.#result.replaceChildren();

    try {
      const snapshot = await this.#fetchPulse(this.#abortController.signal);
      this.#renderPulse(snapshot);
      this.dispatchEvent(new CustomEvent("swee-pulse-complete", {
        bubbles: true,
        detail: { snapshot },
      }));
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      this.#setStatus(message, true);
      this.dispatchEvent(new CustomEvent("swee-pulse-error", {
        bubbles: true,
        detail: { error },
      }));
    } finally {
      this.#submit.disabled = false;
    }
  }

  #handleSubmit = (event) => {
    event.preventDefault();
    this.setAttribute("area", this.#input.value.trim());
    void this.run();
  };

  #syncAttributes() {
    const area = this.getAttribute("area");
    if (area !== null && document.activeElement !== this.#input) {
      this.#input.value = area;
    }
    this.#brand.textContent = this.getAttribute("brand-name")?.trim() || "Swee Pulse";

    const theme = this.getAttribute("theme")?.trim();
    if (theme === "compact") {
      this.style.setProperty("--swee-widget-border", "#cbd5e1");
    }
  }

  async #fetchPulse(signal) {
    const gatewayUrl = (this.getAttribute("gateway-url") || window.location.origin).replace(/\/+$/, "");
    const url = new URL(`${gatewayUrl}/api/v1/pulse/snapshot`);
    url.searchParams.set("focus", normalizeFocus(this.getAttribute("focus")));
    const area = this.#input.value.trim();
    if (area !== "") {
      url.searchParams.set("area", area);
    }

    const headers = new Headers();
    if (this.authToken !== "") {
      headers.set("Authorization", `Bearer ${this.authToken}`);
    }

    const response = await fetch(url, {
      headers,
      method: "GET",
      signal,
    });
    const bodyText = await response.text();
    const body = bodyText ? JSON.parse(bodyText) : {};

    if (!response.ok) {
      throw new Error(body?.error?.message || body?.message || `Swee SG gateway returned ${response.status}.`);
    }

    return body?.data?.snapshot ?? body?.snapshot ?? body?.data?.record ?? body;
  }

  #renderPulse(snapshot) {
    const signals = Array.isArray(snapshot.signals) ? snapshot.signals : [];
    const sourceHealth = Array.isArray(snapshot.sourceHealth) ? snapshot.sourceHealth : [];
    const gaps = Array.isArray(snapshot.gaps) ? snapshot.gaps : [];

    const title = document.createElement("strong");
    title.textContent = `Pulse snapshot: ${text(snapshot.focus ?? "all")}`;

    const summaryList = document.createElement("div");
    summaryList.className = "summary";
    for (const signal of signals.slice(0, 6)) {
      const row = document.createElement("div");
      row.className = "row";
      const label = document.createElement("span");
      label.textContent = `${text(signal.category)} / ${text(signal.severity)}`;
      const value = document.createElement("strong");
      value.textContent = `${text(signal.title)} - ${text(signal.summary)}`;
      row.append(label, value);
      summaryList.append(row);
    }

    const badges = document.createElement("div");
    badges.className = "badges";
    for (const source of sourceHealth.slice(0, 8)) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = `${text(source.source)}: ${text(source.status)} (${text(source.recordCount ?? source.rows ?? 0)} rows)`;
      badges.append(badge);
    }

    const freshnessText = document.createElement("div");
    freshnessText.className = "freshness";
    freshnessText.textContent = sourceHealth.length > 0
      ? `Sources: ${sourceHealth.map((source) => `${source.source} observed ${source.observedAt ?? "unknown"}`).join("; ")}`
      : "Sources: not returned by gateway.";

    const limitsText = document.createElement("div");
    limitsText.className = "limits";
    const gapMessages = gaps.map((item) => item.message).filter(Boolean);
    limitsText.textContent = gapMessages.length > 0
      ? `Gaps: ${gapMessages.join(" ")}`
      : "No Pulse gaps reported by the gateway.";

    this.#result.replaceChildren(title, summaryList, badges, freshnessText, limitsText);
    this.#result.hidden = false;
    this.#setStatus("Pulse snapshot loaded.");
  }

  #setStatus(message, isError = false) {
    this.#status.textContent = message;
    this.#status.classList.toggle("error", isError);
  }
}

customElements.define("swee-pulse-widget", SweePulseWidget);
