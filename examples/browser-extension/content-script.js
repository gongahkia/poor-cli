(() => {
  const UEN_PATTERN = /(?:\b\d{8,9}[A-Za-z]\b|\b[A-Za-z]\d{2}[A-Za-z]{2}\d{4}[A-Za-z]\b)/g;
  const SKIP_TAGS = new Set(["A", "BUTTON", "INPUT", "TEXTAREA", "SELECT", "SCRIPT", "STYLE", "NOSCRIPT"]);
  const DEFAULT_GATEWAY_URL = "http://localhost:8787";
  const DEFAULT_WEB_APP_URL = "http://localhost:5173";
  const overlayId = "dude-uen-overlay-popover";

  const style = document.createElement("style");
  style.textContent = `
    .dude-uen-marker {
      background: #eef2ff;
      border: 1px solid #c7d2fe;
      border-radius: 5px;
      color: #111827;
      cursor: pointer;
      display: inline-flex;
      font: inherit;
      gap: 4px;
      line-height: inherit;
      padding: 0 4px;
    }

    .dude-uen-marker:hover,
    .dude-uen-marker:focus {
      background: #e0e7ff;
      outline: 2px solid #6366f1;
      outline-offset: 1px;
    }

    #${overlayId} {
      background: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      box-shadow: 0 18px 50px rgba(15, 23, 42, 0.18);
      color: #0f172a;
      font: 13px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      max-width: min(360px, calc(100vw - 32px));
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
      color: #4338ca;
      display: inline-block;
      font-weight: 600;
      margin-top: 8px;
      text-decoration: none;
    }
  `;
  document.documentElement.append(style);

  const shouldSkip = (node) => {
    const parent = node.parentElement;
    if (parent === null) return true;
    if (parent.closest("[data-dude-uen-overlay]") !== null) return true;
    return parent.closest(Array.from(SKIP_TAGS).join(",")) !== null;
  };

  const createMarker = (uen) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "dude-uen-marker";
    button.dataset.dudeUenOverlay = "true";
    button.dataset.uen = uen.toUpperCase();
    button.textContent = uen;
    button.title = "Open Dude dossier preview";
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      void openPreview(button, uen.toUpperCase());
    });
    return button;
  };

  const replaceTextNode = (node) => {
    const text = node.nodeValue ?? "";
    UEN_PATTERN.lastIndex = 0;
    const matches = [...text.matchAll(UEN_PATTERN)];
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
        UEN_PATTERN.lastIndex = 0;
        return UEN_PATTERN.test(node.nodeValue ?? "") ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
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

  const readRecord = (payload) => {
    if (payload && typeof payload === "object" && payload.data?.record) {
      return payload.data.record;
    }
    return payload;
  };

  const summaryValue = (record, label) => {
    const entry = Array.isArray(record?.summary)
      ? record.summary.find((item) => String(item.label).toLowerCase() === label.toLowerCase())
      : null;
    return entry?.value == null || entry.value === "" ? null : String(entry.value);
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
    popover.dataset.dudeUenOverlay = "true";
    popover.innerHTML = html;
    document.body.append(popover);
    placePopover(anchor, popover);
  };

  async function openPreview(anchor, uen) {
    renderPopover(anchor, `<strong>Dude dossier</strong><p>Loading ${uen}...</p>`);
    try {
      const { gatewayUrl, webAppUrl } = await getSettings();
      const response = await fetch(`${gatewayUrl}/api/v1/sg_business_dossier`, {
        body: JSON.stringify({ uen }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      });
      if (!response.ok) {
        throw new Error(`Gateway returned ${response.status}`);
      }
      const record = readRecord(await response.json());
      const entity = summaryValue(record, "Entity") ?? "No entity name returned";
      const status = summaryValue(record, "Entity status") ?? "Status unavailable";
      const matched = record?.records?.resolution?.matchedModules?.join(", ") || "none";
      renderPopover(anchor, `
        <strong>${entity}</strong>
        <p>UEN ${uen}</p>
        <p>Status: ${status}</p>
        <p>Matched modules: ${matched}</p>
        <a href="${webAppUrl}/c/${encodeURIComponent(uen)}" target="_blank" rel="noreferrer">Open full dossier</a>
      `);
    } catch (error) {
      renderPopover(anchor, `
        <strong>Dude dossier unavailable</strong>
        <p>${error instanceof Error ? error.message : "Unable to load dossier preview."}</p>
        <p>No page data was sent before this click.</p>
      `);
    }
  }

  document.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.closest("[data-dude-uen-overlay]") !== null) {
      return;
    }
    document.getElementById(overlayId)?.remove();
  });

  if (document.body !== null) {
    scan();
  }
})();
