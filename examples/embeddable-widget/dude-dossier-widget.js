const TEMPLATE = document.createElement("template");

TEMPLATE.innerHTML = `
  <style>
    :host {
      --dude-widget-accent: #16213e;
      --dude-widget-accent-contrast: #ffffff;
      --dude-widget-border: #d8e0ec;
      --dude-widget-muted: #64748b;
      --dude-widget-surface: #ffffff;
      --dude-widget-text: #111827;
      display: block;
      color: var(--dude-widget-text);
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }

    .shell {
      border: 1px solid var(--dude-widget-border);
      border-radius: 8px;
      background: var(--dude-widget-surface);
      padding: 16px;
      max-width: 680px;
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
      border: 1px solid var(--dude-widget-border);
      border-radius: 6px;
      color: var(--dude-widget-text);
      font: inherit;
      padding: 10px 12px;
    }

    button {
      border: 0;
      border-radius: 6px;
      background: var(--dude-widget-accent);
      color: var(--dude-widget-accent-contrast);
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
      color: var(--dude-widget-muted);
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
      border-top: 1px solid var(--dude-widget-border);
      display: grid;
      gap: 3px;
      padding-top: 8px;
    }

    .row span {
      color: var(--dude-widget-muted);
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
      <strong data-brand>Dude diligence</strong>
      <span class="badge" data-mode>Public data</span>
    </div>
    <form>
      <input data-input autocomplete="off" placeholder="Company name or UEN" />
      <button type="submit" data-submit>Check</button>
    </form>
    <div class="status" data-status>Enter a company name or UEN to run a public dossier check.</div>
    <div class="result" data-result hidden></div>
  </section>
`;

const MODULES = new Set(["acra", "bca", "cea", "gebiz", "boa", "hsa", "hlb"]);
const SECTOR_HINTS = new Set([
  "construction",
  "real_estate",
  "architecture",
  "healthcare",
  "hospitality",
  "procurement",
]);

const splitList = (value, allowed) =>
  (value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter((item) => allowed.has(item));

const looksLikeUen = (value) => /^[0-9A-Z]{9,10}$/i.test(value.replace(/\s+/g, ""));

const text = (value) => {
  if (value === null || value === undefined || value === "") {
    return "Not available";
  }
  return String(value);
};

class DudeDossierWidget extends HTMLElement {
  static observedAttributes = [
    "api-token",
    "brand-name",
    "gateway-url",
    "identifier",
    "modules",
    "sector-hints",
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
    if (this.getAttribute("identifier")?.trim()) {
      void this.run();
    }
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
    const identifier = this.#input.value.trim();
    if (identifier === "") {
      this.#setStatus("Enter a company name or UEN to run a public dossier check.");
      return;
    }

    this.#abortController?.abort();
    this.#abortController = new AbortController();
    this.#submit.disabled = true;
    this.#setStatus("Checking public registry sources...");
    this.#result.hidden = true;
    this.#result.replaceChildren();

    try {
      const dossier = await this.#fetchDossier(identifier, this.#abortController.signal);
      this.#renderDossier(dossier);
      this.dispatchEvent(new CustomEvent("dude-dossier-complete", {
        bubbles: true,
        detail: { dossier },
      }));
    } catch (error) {
      if (error.name === "AbortError") {
        return;
      }
      const message = error instanceof Error ? error.message : String(error);
      this.#setStatus(message, true);
      this.dispatchEvent(new CustomEvent("dude-dossier-error", {
        bubbles: true,
        detail: { error },
      }));
    } finally {
      this.#submit.disabled = false;
    }
  }

  #handleSubmit = (event) => {
    event.preventDefault();
    void this.run();
  };

  #syncAttributes() {
    const identifier = this.getAttribute("identifier");
    if (identifier !== null && document.activeElement !== this.#input) {
      this.#input.value = identifier;
    }
    this.#brand.textContent = this.getAttribute("brand-name")?.trim() || "Dude diligence";

    const theme = this.getAttribute("theme")?.trim();
    if (theme === "compact") {
      this.style.setProperty("--dude-widget-border", "#cbd5e1");
    }
  }

  async #fetchDossier(identifier, signal) {
    const gatewayUrl = (this.getAttribute("gateway-url") || window.location.origin).replace(/\/+$/, "");
    const payload = looksLikeUen(identifier)
      ? { uen: identifier.toUpperCase() }
      : { entityName: identifier };
    const modules = splitList(this.getAttribute("modules"), MODULES);
    const sectorHints = splitList(this.getAttribute("sector-hints"), SECTOR_HINTS);
    if (modules.length > 0) {
      payload.modules = modules;
    }
    if (sectorHints.length > 0) {
      payload.sectorHints = sectorHints;
    }

    const headers = new Headers({ "Content-Type": "application/json" });
    if (this.authToken !== "") {
      headers.set("Authorization", `Bearer ${this.authToken}`);
    }

    const response = await fetch(`${gatewayUrl}/api/v1/sg_business_dossier`, {
      body: JSON.stringify(payload),
      headers,
      method: "POST",
      signal,
    });
    const bodyText = await response.text();
    const body = bodyText ? JSON.parse(bodyText) : {};

    if (!response.ok) {
      throw new Error(body?.error?.message || body?.message || `Dude gateway returned ${response.status}.`);
    }

    return body?.data?.record ?? body;
  }

  #renderDossier(dossier) {
    const summary = Array.isArray(dossier.summary) ? dossier.summary : [];
    const provenance = Array.isArray(dossier.provenance) ? dossier.provenance : [];
    const freshness = Array.isArray(dossier.freshness) ? dossier.freshness : [];
    const gaps = Array.isArray(dossier.gaps) ? dossier.gaps : [];
    const limits = Array.isArray(dossier.limits) ? dossier.limits : [];

    const title = document.createElement("strong");
    title.textContent = text(dossier.title);

    const summaryList = document.createElement("div");
    summaryList.className = "summary";
    for (const item of summary.slice(0, 6)) {
      const row = document.createElement("div");
      row.className = "row";
      const label = document.createElement("span");
      label.textContent = text(item.label);
      const value = document.createElement("strong");
      value.textContent = text(item.value);
      row.append(label, value);
      summaryList.append(row);
    }

    const badges = document.createElement("div");
    badges.className = "badges";
    for (const source of provenance.slice(0, 8)) {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = `${text(source.source)}: ${text(source.recordCount)} records`;
      badges.append(badge);
    }

    const freshnessText = document.createElement("div");
    freshnessText.className = "freshness";
    freshnessText.textContent = freshness.length > 0
      ? `Freshness: ${freshness.map((item) => `${item.source} observed ${item.observedAt}`).join("; ")}`
      : "Freshness: not returned by gateway.";

    const limitsText = document.createElement("div");
    limitsText.className = "limits";
    const limitMessages = [...gaps, ...limits].map((item) => item.message).filter(Boolean);
    limitsText.textContent = limitMessages.length > 0
      ? `Gaps and limits: ${limitMessages.join(" ")}`
      : "No gaps or limits reported by the gateway.";

    this.#result.replaceChildren(title, summaryList, badges, freshnessText, limitsText);
    this.#result.hidden = false;
    this.#setStatus("Dossier check complete.");
  }

  #setStatus(message, isError = false) {
    this.#status.textContent = message;
    this.#status.classList.toggle("error", isError);
  }
}

customElements.define("dude-dossier-widget", DudeDossierWidget);
