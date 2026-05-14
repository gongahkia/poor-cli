# Phase 3 Integration Plan

This plan covers what to lift from `legacy/junas/` into the Dude web app in later phases. It does not move files yet.

## A. LIFT

| Item | Source path(s) | Destination path(s) | Reason for SG diligence | Mode |
| --- | --- | --- | --- | --- |
| Vite app baseline | `legacy/junas/vite.config.ts`, `legacy/junas/index.html`, `legacy/junas/src/main.tsx` | `apps/web/vite.config.ts`, `apps/web/index.html`, `apps/web/src/main.tsx` | Gives Dude a browser-first React/Vite shell without Tauri. | Copy + rewrite |
| Tailwind baseline and required tokens | `legacy/junas/tailwind.config.ts`, `legacy/junas/src/app/globals.css` | `apps/web/tailwind.config.ts`, `apps/web/src/styles/globals.css` | Provides a clean Vite/Tailwind foundation with only the CSS variables required by lifted Radix components plus baseline colors. | Fresh config with selective token port |
| Shared class utility | `legacy/junas/src/lib/utils.ts` | `apps/web/src/lib/cn.ts` or `apps/web/src/lib/utils.ts` | `clsx` + `tailwind-merge` keeps component class composition clean. | Copy + rewrite |
| Radix Button | `legacy/junas/src/components/ui/button.tsx` | `apps/web/src/components/ui/button.tsx` | Needed for search submission, copy URL, export PDF, and section actions. | Direct copy with import-path adjustment |
| Radix Input | `legacy/junas/src/components/ui/input.tsx` | `apps/web/src/components/ui/input.tsx` | Needed for the company/UEN search box. | Direct copy with import-path adjustment |
| Radix Dialog | `legacy/junas/src/components/ui/dialog.tsx` | `apps/web/src/components/ui/dialog.tsx` | Useful for source detail, raw JSON, or export confirmation overlays if needed in v1. | Direct copy with import-path adjustment |
| Radix Label | `legacy/junas/src/components/ui/label.tsx` | `apps/web/src/components/ui/label.tsx` | Keeps input and form controls accessible. | Direct copy with import-path adjustment |
| Skeleton loading | `legacy/junas/src/components/ui/skeleton.tsx` | `apps/web/src/components/ui/skeleton.tsx` | Supports honest loading states while `sg_business_dossier` resolves. | Copy + trim chat-specific skeletons |
| Markdown renderer | `legacy/junas/src/components/chat/MarkdownRenderer.tsx` | `apps/web/src/components/markdown/MarkdownRenderer.tsx` | Useful for rendering brief handoff markdown, limits, and future AI synthesis artifacts. | Copy + rewrite |
| Markdown dependencies | Junas package dependency pattern: `react-markdown`, `remark-gfm`, `remark-math`, `rehype-katex`, `katex` | `apps/web/package.json` | Supports tables, GFM, and math if source artifacts include richer markdown. | Dependency lift |
| Mermaid renderer | `legacy/junas/src/components/chat/MermaidDiagram.tsx` | `apps/web/src/components/diagrams/MermaidDiagram.tsx` | Client-side relationship and ownership graph rendering for future dossier views. | Copy + rewrite |
| Graphviz renderer scaffold | `legacy/junas/src/components/chat/GraphvizDiagram.tsx` | `apps/web/src/components/diagrams/GraphvizDiagram.tsx` | Preserves the approved component contract for future entity relationship graphs. | Fresh scaffold inspired by original; no `@viz-js/viz` dependency yet |
| Diagram language router | `legacy/junas/src/components/chat/MarkdownRenderer.tsx` | `apps/web/src/components/diagrams/DiagramBlock.tsx` | Lets markdown code fences render only approved client-side diagram types. | Copy + rewrite |
| DOMPurify sanitizers | `legacy/junas/src/lib/sanitize.ts` | `apps/web/src/lib/sanitize.ts` | Required for safe SVG/HTML rendering from diagrams or future AI-generated content. | Direct lift with import-style cleanup |
| PDF export | `legacy/junas/src/lib/pdf-export.ts` | `apps/web/src/lib/export/pdf.ts` | Provides “Export PDF” for a diligence brief. | Copy + rewrite for Dude diligence brief shape |
| AI provider abstraction scaffold | Junas high-level multi-provider concept only; do not lift or reference implementation files during implementation | `apps/web/src/lib/ai/index.ts`, `apps/web/src/lib/ai/providers/openai.ts`, `apps/web/src/lib/ai/providers/anthropic.ts`, `apps/web/src/lib/ai/providers/google.ts`, `apps/web/src/lib/ai/types.ts` | Preserves a clean future AI synthesis tier seam without exposing keys in the browser. | Fresh implementation |
| Search suggestion ranker | `legacy/junas/src/lib/search.ts`, `legacy/junas/src/lib/commands/search.ts` as pattern reference only | `apps/web/src/lib/search/rank-search-suggestions.ts` | Fuse.js can rank forgiving company/UEN search suggestions for the single search box. | Fresh narrow helper inspired by original |
| Basic app types | `legacy/junas/src/types/provider.ts` for AI pattern; no direct app chat types | `apps/web/src/lib/ai/types.ts`, `apps/web/src/types/dossier.ts` | Keeps future AI contracts and dossier UI contracts explicit. | Fresh types |
| Workspace registration | Root `package.json` | Root `package.json` | Makes `apps/web` visible to npm workspaces. | Direct edit |

Notes:

- PlantUML is intentionally excluded because `legacy/junas/src/components/chat/PlantUMLDiagram.tsx` calls `https://www.plantuml.com/plantuml/svg/...`.
- D2 is intentionally excluded for v1 because `legacy/junas/src/components/chat/D2Diagram.tsx` opens `https://play.d2lang.com/...` rather than rendering client-side. Defer pending a local/WASM renderer story.
- The AI module should be roughly 150 lines across a clean `generate({ prompt, system, model, provider })` entrypoint plus three thin providers for Anthropic, OpenAI, and Google. It should contain exactly one entrypoint TODO noting future AI synthesis tier wiring, read API keys from server-side env vars only, and not be imported by the v1 UI.
- The web app should call the existing `packages/mcp-server/src/rest-gateway.ts` endpoints directly in later phases; no BFF is planned.

## B. SKIP

| Item | Source path(s) | Reason to skip v1 |
| --- | --- | --- |
| Tauri shell | `legacy/junas/src-tauri/` | Desktop runtime is out of scope; Dude v1 is web-only. |
| Tauri bridge and IPC | `legacy/junas/src/lib/tauri-bridge.ts`, Tauri-specific call sites | Coupled to desktop commands, keychain, and local filesystem capabilities. |
| Rust backend | `legacy/junas/src-tauri/src/**` | Not needed for MCP REST gateway-backed web app. |
| OS keychain handling | `legacy/junas/src-tauri/src/keychain.rs`, related provider settings copy | v1 has no BYOK client-side key handling. |
| Ollama provider path | `legacy/junas/src/lib/ai/**`, `legacy/junas/src/lib/providers/registry.ts`, Tauri bridge paths mentioning `ollama` | Local-LLM desktop concern; explicitly out of scope. |
| LM Studio provider path | Same provider files as above | Local-LLM desktop concern; explicitly out of scope. |
| Local model management | `legacy/junas/src/lib/ml/**`, `legacy/junas/frontend/lib/ml/**` | Local inference/model cache is not part of diligence MVP. |
| RAG service | `legacy/junas/src/lib/rag/**` | Future AI synthesis is deferred; no document-indexing layer in v1. |
| Browser document parsing | `legacy/junas/src/lib/tauri-bridge.ts` PDF/DOCX parsing paths, `legacy/junas/src/components/chat/DocumentPreview.tsx` | Bulk documents and legal review are out of scope for counterparty search. |
| Legal templates and clauses | `legacy/junas/src/lib/templates/**`, `legacy/junas/src/lib/clauses/**`, `legacy/junas/src/components/TemplateLibrary.tsx`, `legacy/junas/src/components/ClauseLibrary.tsx` | Legal drafting workflows do not fit Dude v1. |
| Legal source workflows | `legacy/junas/src/lib/legal-sources/**`, `legacy/junas/src/lib/citations/**`, `legacy/junas/src/lib/jurisdictions/**` | Product is public-data due diligence, not legal research. |
| Legal disclaimers as product copy | `legacy/junas/src/components/LegalDisclaimer.tsx`, Junas README disclaimer copy | Dude needs bounded public-data limits, not legal AI disclaimer copy. |
| Share URL compression | `legacy/junas/src/lib/share-utils.ts` | v1 share path is only `/c/:identifier`; no compressed client state. |
| Junas chat UX | `legacy/junas/src/components/chat/ChatInterface.tsx`, `MessageList.tsx`, `MessageInput.tsx`, tree/history components | v1 is search/result workflow, not a chat product. |
| Junas command palette | `legacy/junas/src/components/chat/CommandPalette.tsx`, command processor modules | Useful pattern, but too chat/legal-agent-specific for v1. |
| Next/FastAPI app | `legacy/junas/frontend/**`, `legacy/junas/backend/**` | Reference-only per decision; do not import Python service or Next app. |
| PlantUML renderer | `legacy/junas/src/components/chat/PlantUMLDiagram.tsx` | Calls a remote renderer; deferred pending self-host story. |
| D2 renderer | `legacy/junas/src/components/chat/D2Diagram.tsx` | Calls a remote playground; deferred pending client-side/WASM renderer story. |
| Compromise NLP helpers | `legacy/junas/src/lib/nlp/**` | Deferred until a pasted-text input flow exists. |
| Theme zoo | Most of `legacy/junas/src/app/globals.css` alternate themes | Too broad for v1; port only minimal tokens needed for Dude. |
| Junas local persistence | `legacy/junas/src/lib/storage.ts`, `legacy/junas/src/lib/storage/**`, conversation stores | Accounts, saved searches, and monitoring are deferred. |
| Junas legal compliance rules | `legacy/junas/src/lib/compliance/**`, `legacy/junas/src/components/ComplianceDashboard.tsx` | Legal compliance dashboard is not the MVP flow. |
| Generated build artifacts | `legacy/junas/dist/**`, package lock artifacts beyond dependency reference | Do not import generated output. |

## C. UNCERTAIN

1. None for Phase 4. Decisions resolved:
   - Fuse.js is limited to `rankSearchSuggestions()` for the search box.
   - Compromise.js is deferred.
   - Tailwind starts clean and ports only required component tokens.
   - Radix lift is limited to Button, Input, Dialog, Label, and Skeleton.
   - Share path is `/c/:identifier` only.
   - Graphviz keeps a component scaffold but defers the `@viz-js/viz` dependency until relationship graphs ship.
