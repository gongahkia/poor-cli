(() => {
  const AREA_NAMES = [
    "Ang Mo Kio",
    "Bedok",
    "Bishan",
    "Boon Lay",
    "Bukit Batok",
    "Bukit Merah",
    "Bukit Panjang",
    "Bukit Timah",
    "Changi",
    "Choa Chu Kang",
    "Clementi",
    "Downtown Core",
    "Geylang",
    "Hougang",
    "Jurong East",
    "Jurong West",
    "Kallang",
    "Mandai",
    "Marine Parade",
    "Orchard",
    "Pasir Ris",
    "Paya Lebar",
    "Punggol",
    "Queenstown",
    "Sembawang",
    "Sengkang",
    "Serangoon",
    "Tampines",
    "Toa Payoh",
    "Woodlands",
    "Yishun",
  ];
  const AREA_PATTERN = new RegExp(`\\b(${AREA_NAMES.map((area) => area.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|")})\\b`, "gi");
  const SKIP_TAGS = new Set(["A", "BUTTON", "INPUT", "TEXTAREA", "SELECT", "SCRIPT", "STYLE", "NOSCRIPT"]);
  const DEFAULT_GATEWAY_URL = "http://localhost:3000";
  const DEFAULT_WEB_APP_URL = "http://localhost:5173";
  const overlayId = "swee-pulse-overlay-popover";

  const style = document.createElement("style");
  style.textContent = `
    .swee-pulse-marker {
      background: #ecfdf3;
      border: 1px solid #bbf7d0;
      border-radius: 5px;
      color: #111827;
      cursor: pointer;
      display: inline-flex;
      font: inherit;
      gap: 4px;
      line-height: inherit;
      padding: 0 4px;
    }

    .swee-pulse-marker:hover,
    .swee-pulse-marker:focus {
      background: #dcfce7;
      outline: 2px solid #16a34a;
      outline-offset: 1px;
    }

    #${overlayId} {
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
      color: #0f172a;
      font: 13px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: min(380px, calc(100vw - 32px));
      padding: 12px;
      position: fixed;
      z-index: 2147483647;
    }

    #${overlayId} strong {
      display: block;
      font-size: 14px;
      margin-bottom: 4px;
    }

    #${overlayId} a {
      color: #047857;
      display: inline-block;
      font-weight: 600;
      margin-top: 8px;
      text-decoration: none;
    }
  `;
  document.documentElement.append(style);

  const escapeHtml = (value) =>
    String(value).replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      "\"": "&quot;",
      "'": "&#39;",
    })[char]);

  const shouldSkip = (node) => {
    const parent = node.parentElement;
    if (parent === null) return true;
    if (parent.closest("[data-swee-pulse-overlay]") !== null) return true;
    return parent.closest(Array.from(SKIP_TAGS).join(",")) !== null;
  };

  const createMarker = (area) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "swee-pulse-marker";
    button.dataset.sweePulseOverlay = "true";
    button.dataset.area = area;
    button.textContent = area;
    button.title = "Open Swee Pulse preview";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void openPreview(button, area);
    });
    return button;
  };

  const replaceTextNode = (node) => {
    const text = node.nodeValue ?? "";
    AREA_PATTERN.lastIndex = 0;
    const matches = [...text.matchAll(AREA_PATTERN)];
    if (matches.length === 0) return;

    const fragment = document.createDocumentFragment();
    let cursor = 0;
    for (const match of matches) {
      const start = match.index ?? 0;
      const value = match[0];
      if (start > cursor) {
        fragment.append(document.createTextNode(text.slice(cursor, start)));
      }
      fragment.append(createMarker(value));
      cursor = start + value.length;
    }
    if (cursor < text.length) {
      fragment.append(document.createTextNode(text.slice(cursor)));
    }
    node.parentNode?.replaceChild(fragment, node);
  };

  const scan = () => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, {
      acceptNode(node) {
        if (shouldSkip(node)) return NodeFilter.FILTER_REJECT;
        AREA_PATTERN.lastIndex = 0;
        return AREA_PATTERN.test(node.nodeValue ?? "") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
      },
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(replaceTextNode);
  };

  const getSettings = () =>
    new Promise((resolve) => {
      chrome.storage.sync.get({
        gatewayUrl: DEFAULT_GATEWAY_URL,
        webAppUrl: DEFAULT_WEB_APP_URL,
      }, (items) => {
        resolve({
          gatewayUrl: String(items.gatewayUrl || DEFAULT_GATEWAY_URL).replace(/\/+$/, ""),
          webAppUrl: String(items.webAppUrl || DEFAULT_WEB_APP_URL).replace(/\/+$/, ""),
        });
      });
    });

  const readSnapshot = (payload) => {
    if (payload && typeof payload === "object" && payload.data?.snapshot) {
      return payload.data.snapshot;
    }
    if (payload && typeof payload === "object" && payload.snapshot) {
      return payload.snapshot;
    }
    if (payload && typeof payload === "object" && payload.data?.record) {
      return payload.data.record;
    }
    return payload;
  };

  const placePopover = (anchor, popover) => {
    const rect = anchor.getBoundingClientRect();
    const top = Math.min(window.innerHeight - popover.offsetHeight - 12, rect.bottom + 8);
    const left = Math.min(window.innerWidth - popover.offsetWidth - 12, rect.left);
    popover.style.top = `${Math.max(12, top)}px`;
    popover.style.left = `${Math.max(12, left)}px`;
  };

  const renderPopover = (anchor, html) => {
    document.getElementById(overlayId)?.remove();
    const popover = document.createElement("aside");
    popover.id = overlayId;
    popover.dataset.sweePulseOverlay = "true";
    popover.innerHTML = html;
    document.body.append(popover);
    placePopover(anchor, popover);
  };

  async function openPreview(anchor, area) {
    renderPopover(anchor, `<strong>Swee Pulse</strong><p>Loading ${escapeHtml(area)}...</p>`);
    try {
      const { gatewayUrl, webAppUrl } = await getSettings();
      const url = new URL(`${gatewayUrl}/api/v1/pulse/snapshot`);
      url.searchParams.set("focus", "all");
      url.searchParams.set("area", area);
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Gateway returned ${response.status}`);
      }
      const snapshot = readSnapshot(await response.json());
      const signals = Array.isArray(snapshot?.signals) ? snapshot.signals : [];
      const sourceHealth = Array.isArray(snapshot?.sourceHealth) ? snapshot.sourceHealth : [];
      const watchSignals = signals.filter((signal) => signal.severity !== "info");
      const headline = watchSignals[0] ?? signals[0];
      const sourceSummary = sourceHealth.length === 0
        ? "No source-health rows returned"
        : `${sourceHealth.filter((source) => source.status === "ready").length}/${sourceHealth.length} sources ready`;
      renderPopover(anchor, `
        <strong>${escapeHtml(area)} Pulse</strong>
        <p>${escapeHtml(headline?.title ?? "No area-specific signal returned")}</p>
        <p>${escapeHtml(headline?.summary ?? "Open Swee SG for the full source-backed snapshot.")}</p>
        <p>Source health: ${escapeHtml(sourceSummary)}</p>
        <a href="${webAppUrl}/?area=${encodeURIComponent(area)}" target="_blank" rel="noreferrer">Open Swee SG</a>
      `);
    } catch (error) {
      renderPopover(anchor, `
        <strong>Swee Pulse unavailable</strong>
        <p>${escapeHtml(error instanceof Error ? error.message : "Unable to load Pulse preview.")}</p>
        <p>No page data was sent before this click.</p>
      `);
    }
  }

  document.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("[data-swee-pulse-overlay]") !== null) {
      return;
    }
    document.getElementById(overlayId)?.remove();
  });

  if (document.body !== null) {
    scan();
  }
})();
