# Dude UEN Overlay Prototype

This is a Manifest V3 browser-extension prototype for Singapore UEN detection on arbitrary web pages. It highlights UEN-like text and loads a bounded Dude dossier preview only after the user clicks a detected UEN.

## Supported Browsers

- Chrome and Chromium-based browsers that support Manifest V3.
- Edge should work through the Chromium extension path.
- Firefox is not targeted by this prototype because its Manifest V3 behavior and extension APIs differ.

## Local Setup

1. Start Dude locally:

   ```sh
   npm run dev:local
   ```

2. Open `chrome://extensions`, enable Developer mode, and load `examples/browser-extension` as an unpacked extension.
3. Open extension options and set:
   - Dude gateway URL: `http://localhost:8787` or your REST gateway origin.
   - Dude web app URL: `http://localhost:5173` or your web app origin.

## Privacy And Permissions

- The content script scans visible page text locally for UEN-like patterns.
- It does not send page text, URLs, or detected UENs to Dude until the user clicks a highlighted UEN.
- The request payload is limited to `{ "uen": "<detected UEN>" }`.
- Host permissions are limited to localhost Dude development origins. Widen them only after a production privacy review.

## Limits

- UEN detection is regex-based and can highlight false positives in ordinary page text.
- Image-only UENs, PDFs rendered by browser plugins, shadow-DOM-heavy apps, and dynamically loaded content after the first scan may be missed.
- The preview is a prototype and does not replace the full dossier, provenance, freshness, gaps, and limits shown in the Dude web app.
- Do not use this prototype to make legal, credit, tax, investment, or licensed compliance decisions.
