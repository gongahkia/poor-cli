# Swee Pulse Overlay Prototype

This is a Manifest V3 browser-extension prototype for Singapore place-name detection on arbitrary web pages. It highlights common planning-area names and loads a bounded Swee Pulse preview only after the user clicks a detected place.

## Supported Browsers

- Chrome and Chromium-based browsers that support Manifest V3.
- Edge should work through the Chromium extension path.
- Firefox is not targeted by this prototype because its Manifest V3 behavior and extension APIs differ.

## Local Setup

1. Start Swee SG locally:

   ```sh
   npm run dev:local
   ```

2. Open `chrome://extensions`, enable Developer mode, and load `examples/browser-extension` as an unpacked extension.
3. Open extension options and set:
   - Swee SG gateway URL: `http://localhost:3000` or your REST gateway origin.
   - Swee SG web app URL: `http://localhost:5173` or your web app origin.

## Privacy And Permissions

- The content script scans visible page text locally for known Singapore area names.
- It does not send page text, URLs, or detected places to Swee SG until the user clicks a highlighted place.
- The request is limited to `GET /api/v1/pulse/snapshot?focus=all&area=<detected area>`.
- Host permissions are limited to localhost Swee SG development origins. Widen them only after a production privacy review.

## Limits

- Place-name detection is dictionary-based and can highlight false positives in ordinary page text.
- Image-only text, PDFs rendered by browser plugins, shadow-DOM-heavy apps, and dynamically loaded content after the first scan may be missed.
- The preview is a prototype and does not replace the full Pulse dashboard, source health, freshness, gaps, and Shield audit trails shown in the Swee SG web app.
- Do not use this prototype as an official emergency, transport, weather, legal, credit, tax, investment, or licensed compliance decision tool.
