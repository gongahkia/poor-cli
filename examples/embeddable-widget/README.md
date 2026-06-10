# Embeddable Pulse Widget

This example provides a zero-build web component and an iframe wrapper for embedding Swee Pulse signals in a client portal, intranet, or CMS page.

## Success Definition

- A host page can embed source-backed Singapore city signals without adopting the React app.
- The widget calls the product REST gateway endpoint `GET /api/v1/pulse/snapshot`.
- API, auth, origin, and white-label theming behavior are documented.
- The smoke check verifies the example files expose the expected integration contract.

## Web Component

```html
<script src="/widgets/swee-pulse-widget.js"></script>

<swee-pulse-widget
  gateway-url="https://swee.example"
  brand-name="City pulse"
  focus="weather"
  area="Bedok"
></swee-pulse-widget>
```

Attributes:

| Attribute | Purpose |
| --- | --- |
| `gateway-url` | REST gateway origin. Defaults to the embedding page origin. |
| `area` | Optional initial Singapore area filter. If omitted, the widget loads the all-Singapore snapshot. |
| `focus` | Optional focus: `all`, `mobility`, or `weather`. |
| `brand-name` | White-label heading shown above the input. |
| `theme` | Reserved theme selector. `compact` is currently supported. |
| `api-token` | Optional browser-visible bearer token. Use only short-lived, origin-scoped, least-privilege tokens. |

Events:

| Event | Detail |
| --- | --- |
| `swee-pulse-complete` | `{ snapshot }` after a successful refresh. |
| `swee-pulse-error` | `{ error }` after a failed request. |

## Iframe Wrapper

Use `widget-frame.html` when the host cannot load custom elements directly:

```html
<iframe
  title="Swee Pulse"
  src="https://swee.example/widgets/widget-frame.html?gatewayUrl=https%3A%2F%2Fswee.example&brandName=City%20pulse&focus=weather&area=Bedok"
  width="720"
  height="420"
  loading="lazy"
></iframe>
```

The iframe wrapper accepts these query parameters: `gatewayUrl`, `brandName`, `focus`, `area`, and `theme`.

## Auth And Origins

For public or self-hosted gateways with no browser auth, no token is required.

For hosted gateways:

- prefer a backend proxy that injects credentials server-side;
- if a browser token is unavoidable, issue a short-lived token scoped to Pulse read endpoints, the allowed origin, and the customer workspace;
- never embed upstream API keys, AI provider keys, admin tokens, or long-lived service tokens in HTML;
- configure the REST gateway CORS allowlist with exact host origins, not `*`;
- keep `gateway-url` same-origin when possible to avoid third-party cookie and CORS failure modes.

## White-Label Styling

The component exposes CSS variables on the custom element:

```css
swee-pulse-widget {
  --swee-widget-accent: #0f766e;
  --swee-widget-accent-contrast: #ffffff;
  --swee-widget-border: #cbd5e1;
  --swee-widget-muted: #64748b;
  --swee-widget-surface: #ffffff;
  --swee-widget-text: #0f172a;
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
