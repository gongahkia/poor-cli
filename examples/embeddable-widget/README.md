# Embeddable Dossier Widget

This example provides a zero-build web component and an iframe wrapper for embedding a bounded Dude business-dossier search in a client portal, intranet, or CMS page.

## Success Definition

- A host page can embed a company name or UEN search without adopting the React app.
- The widget calls the existing REST gateway endpoint `POST /api/v1/sg_business_dossier`.
- API, auth, origin, and white-label theming behavior are documented.
- The smoke check verifies the example files expose the expected integration contract.

## Web Component

```html
<script src="/widgets/dude-dossier-widget.js"></script>

<dude-dossier-widget
  gateway-url="https://dude.example"
  brand-name="Client diligence"
  modules="acra,gebiz"
  sector-hints="procurement"
></dude-dossier-widget>
```

Attributes:

| Attribute | Purpose |
| --- | --- |
| `gateway-url` | REST gateway origin. Defaults to the embedding page origin. |
| `identifier` | Optional initial company name or UEN. If present, the widget runs on load. |
| `modules` | Optional comma-separated module list: `acra,bca,cea,gebiz,boa,hsa,hlb`. |
| `sector-hints` | Optional comma-separated sector hints: `construction,real_estate,architecture,healthcare,hospitality,procurement`. |
| `brand-name` | White-label heading shown above the search box. |
| `theme` | Reserved theme selector. `compact` is currently supported. |
| `api-token` | Optional browser-visible bearer token. Use only short-lived, origin-scoped, least-privilege tokens. |

Events:

| Event | Detail |
| --- | --- |
| `dude-dossier-complete` | `{ dossier }` after a successful check. |
| `dude-dossier-error` | `{ error }` after a failed request. |

## Iframe Wrapper

Use `widget-frame.html` when the host cannot load custom elements directly:

```html
<iframe
  title="Dude dossier search"
  src="https://dude.example/widgets/widget-frame.html?gatewayUrl=https%3A%2F%2Fdude.example&brandName=Client%20diligence&modules=acra"
  width="720"
  height="420"
  loading="lazy"
></iframe>
```

The iframe wrapper accepts these query parameters: `gatewayUrl`, `brandName`, `identifier`, `modules`, `sectorHints`, and `theme`.

## Auth And Origins

For public or self-hosted gateways with no browser auth, no token is required.

For hosted gateways:

- prefer a backend proxy that injects credentials server-side;
- if a browser token is unavoidable, issue a short-lived token scoped to `sg_business_dossier`, the allowed origin, and the customer workspace;
- never embed upstream API keys, AI provider keys, admin tokens, or long-lived service tokens in HTML;
- configure the REST gateway CORS allowlist with exact host origins, not `*`;
- keep `gateway-url` same-origin when possible to avoid third-party cookie and CORS failure modes.

## White-Label Styling

The component exposes CSS variables on the custom element:

```css
dude-dossier-widget {
  --dude-widget-accent: #0f766e;
  --dude-widget-accent-contrast: #ffffff;
  --dude-widget-border: #cbd5e1;
  --dude-widget-muted: #64748b;
  --dude-widget-surface: #ffffff;
  --dude-widget-text: #0f172a;
}
```

## Local Demo

Start the gateway:

```bash
npm run dev:gateway
```

Then open `examples/embeddable-widget/demo.html` in a browser. The demo expects the gateway at `http://localhost:3000`.

## Smoke Check

```bash
npm run widget:check
```
