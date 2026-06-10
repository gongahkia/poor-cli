# WORKON-PIVOT-ASAP

Strategy doc for `haus`. Locked direction after market research + user discussion 2026-05-16.

## North star

> Show HN: I gave Claude an MCP server and made it interior-design my HDB flat.

- *Goal*: GitHub stars + HN front page. Not revenue. Not SaaS.
- *Niche*: HDB BTO Singapore. Stays specific. Specificity is the hook, not the liability.
- *Wedge*: MCP / AI-agent autonomy. The 30-tool surface area is the moat.
- *Demo*: one-shot "design my flat" agent. User picks BTO layout + style prompt → Claude autonomously furnishes it end-to-end.

## KPIs (90 days post-launch)

- [Speculation] Realistic target: 1.5k–3k stars, HN front page once, ~30k repo visits.
- Stretch: 5k+ stars, sustained MCP-directory traffic.
- Floor: 300–500 stars without HN traction.

## Tension acknowledged

Singapore-only + global HN audience is a trade-off. Specificity wins on HN *only if* the demo carries. Mitigation: demo quality is the single biggest lever — if the GIF doesn't make people screenshot-share it, none of the rest matters.

## Competitive landscape (verified)

- *Direct SG*: Qanvast BTO Layout Planner, 3dbto.sg, btomyhome.com. All free + lead-gen or paid SketchUp models. None ship MCP.
- *Adjacent AI*: Maket.ai (1M users, $4.4M raised), CubiCasa (acquired Clear Capital 2021), Planner 5D, Snaptrude. None target SG, none ship MCP.
- *MCP for Three.js*: locchung/three-js-mcp, baryhuang/mcp-threejs, DmitriyGolub/threejs-devtools-mcp. All general-purpose scene tools, none vertical for room design.
- *OSS room editors*: OpenPlan3D, theLodgeBots/open3dFloorplan, mehanix/arcada. Crowded but none ride MCP.

[Inference] White space = vertical (BTO) + MCP-native. Both edges are needed; either alone has competitors.

## Tier 1 — demo-determinant (ship or it fails)

### 1. Hero demo GIF/video
- 30-second loop at top of README. Below the badges, above everything else.
- Content: user types `"design a minimalist 4-room family flat"` → Claude calls ~15 tools → fully furnished apartment rotates in view.
- Record at 1080p, ≤8MB GIF or mp4 link.
- *Files*: `asset/demo/hero.mp4`, `asset/demo/hero.gif`, README.md hero section.

### 2. Higher-level agent loop tool
- Current MCP exposes CRUD primitives only. Demos read as "Claude calls a function" not "Claude designs."
- Add `design_room` / `design_flat` tools that bundle multi-step intent:
  - Input: room_id (or whole flat) + style prompt + constraints.
  - Internally: read layout → choose furniture set → place → align → snap → tag.
  - Returns: summary + tool-call trace for transparency.
- *Files*: `src/haus/mcp_server.py` (new high-level tools), `src/haus/agent_loop.py` (new).

### 3. BTO layouts dropdown (pre-seeded)
- The `corpus/` already has cleaned BTO floor plans. Surface them as a one-click "Load real layout" picker in the editor.
- Bundle the vectorized outputs as JSON so no preprocessing on first run.
- *Files*: `viewer/js/btoLibrary.js` (new), `viewer/editor.html` (dropdown), `corpus/library/*.json` (pre-vectorized).

### 4. README hero rewrite
- Open with: 1-line value prop, hero GIF, 1-command install, "Try the demo" link.
- Move stack table, MCP tool table, credits, architecture below the fold.
- Keep current attribution intact per user decision; just relocate to bottom.
- *Files*: `README.md`.

### 5. One-command install
- `uvx haus` or `pipx install haus` → `haus view` opens browser + MCP-ready.
- Currently requires `git clone && make setup && make view`. Friction kills star conversion.
- *Files*: `pyproject.toml`, `src/haus/cli.py`.

## Tier 2 — virality multipliers

### 6. Provider showdown content
- Same prompt across Claude / GPT / Gemini. Side-by-side furnished outputs as a still image or short video.
- Lives in a `BENCHMARKS.md` or blog post. Drives reshares; legitimate evaluation, not just bait.
- *Files*: `BENCHMARKS.md`, `asset/benchmarks/*.png`.

### 7. MCP directory listings
- mcp.so, mcp.pizza, pulsemcp.com, smithery.ai, Anthropic MCP directory.
- Each takes <30min, free distribution, surfaces in `claude mcp add` flows.
- *Files*: `mcp-manifest.json` if any registry needs it.

### 8. Editor visual polish
- First-impression matters more than feature count. Pass on lighting, materials, shadow softness, default camera angle, ambient occlusion.
- Default scene must look good in screenshots without any user setup.
- *Files*: `viewer/js/scene.js` (lighting), `viewer/js/main.js` (default camera).

### 9. SG tech amplification
- Pre-launch ping to Zane (@injaneity), Wei Sin (@weisintai). Post on SG-focused Twitter / r/singapore the day of HN submission.
- HN traction window is ~4 hours. Geographic time-zone: submit ~8am PT (11pm SGT) for max US daytime + SG evening engagement.

## Tier 3 — explicitly cut

- *Generic raster→vector pipeline pitch*: CubiCasa5k ML beats CV on accuracy. Don't headline this. Keep code, demote in narrative.
- *Photo-to-stage / real estate agent pivot*: out of scope per user decision.
- *Multi-floor / BIM export / DXF*: distraction. BTOs are single-floor.
- *Mobile / AR scan*: Apple RoomPlan / CubiCasa own that. Not our wedge.
- *Generative text-to-floorplan*: Maket/SpatialGen territory. Stays out.
- *B2B sales to designers/contractors*: not the goal.

## Launch checklist

- [x] Hero GIF/video assets recorded and embedded in README
- [x] `design_room` + `design_flat` tools implemented with room-bounded collision-aware placement
- [x] Pre-vectorized BTO library shipped in repo
- [x] README rewritten with value prop above the fold
- [x] One-command local viewer path implemented through `haus view`
- [x] Editor lighting/materials polish pass complete
- [x] BENCHMARKS.md with provider showdown
- [x] Chat-first planner implemented as the default visible interface
- [x] Backend destructive-tool confirmation gate implemented
- [x] Strict server-side tool argument validation implemented
- [x] Planner modes labelled honestly: deterministic, LLM-reviewed, LLM-structured
- [x] Standards profiles added for compact, comfortable, accessible, kitchen, bedroom, and bathroom screening
- [x] Polygon room geometry and semantic export/BIM-readiness report added
- [ ] Listed on mcp.so + mcp.pizza + pulsemcp + smithery + Anthropic registry
- [ ] HN draft title + first comment prewritten
- [ ] SG tech amplification network primed

## Risks & mitigations

- *MCP novelty saturates*: window closing fast. Ship in weeks not months. // user said "whatever it takes" but real-world urgency stands
- *Singapore-niche caps reach*: mitigation is demo quality + framing the SG-ness as charm. If first 100 HN comments are "what's HDB?" we lost — pre-empt with a one-line glossary in README.
- *Three.js editor polish bar is high*: budget real time for materials/lighting. Bad lighting = "looks like a school project" comments.
- *Codex Hackathon credit stays*: per user. [Inference] Some HN readers will read "later dropped by original team" as a negative signal. Counter-narrative ready: rebuilt solo, MCP layer is original work, link to current commit graph.

## Concrete next actions (this week)

1. Run a clean install smoke test on macOS and Linux for `haus view`.
2. Record a fresh chat-first demo that shows draft → warnings/profile → apply → validation.
3. Write HN title, first comment, and a short "what is HDB/BTO?" explanation.
4. Submit/update MCP directory listings.
5. Add more curated room polygons/openings to the BTO library so polygon-aware placement is visible in demos.
6. Expand benchmark prompts for destructive prompt injection, accessible-profile warnings, and kitchen/bedroom ergonomics.

## Current implementation status

- Chat is functional and now safer: provider tool calls are validated, destructive actions require backend confirmation, concept drafts no longer require an API key, and plan cards expose planner mode, profile, confidence, and readiness.
- Modelling is useful for concept planning: furniture placement is room-bounded and collision-aware, walkway scoring is profile-driven, room polygons are supported, and semantic JSON/BIM-readiness reports exist.
- Still not done for professional/compliance use: no full IFC export, no construction drawings, no code-compliance certification, limited furniture/product catalog, limited door/window semantics, and no persistent multi-user project database.

## Honest expectations

[Inference] Top-quartile outcome with full execution: 3–5k stars, one HN front-page day, sustained MCP-directory traffic, no revenue. Floor-plan editors don't compound like devtools or AI frameworks — there's no Cursor trajectory here, and chasing one would force out of the SG niche. Calibrate accordingly.
