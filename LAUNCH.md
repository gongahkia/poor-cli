# Haus Launch Collateral

## Hacker News

### Title

Show HN: I gave Claude an MCP server and made it interior-design my HDB flat

### First comment draft

Hi HN, I built Haus, a small open-source floor-plan editor for Singapore HDB BTO flats with an MCP server attached.

For non-Singapore readers: HDB flats are Singapore public-housing apartments, and BTO means "Build-To-Order", a common way Singaporeans buy new flats from the government.

The demo: https://github.com/gongahkia/haus#readme

The interesting part is not generic floor-plan conversion. The editor exposes a broad MCP tool surface for layout queries, furniture placement, collision checks, sightlines, room tagging, and high-level room/flat design. In the demo, the user can load a real BTO layout and ask Claude to design a minimalist 4-room family flat; Claude then calls the layout tools and furnishes the scene end to end.

Current scope:

- HDB/BTO layouts as the niche.
- Browser-based Three.js editor for GLB/SVG/JSON layout work.
- MCP-native autonomous layout tooling.
- Local-first workflow, no SaaS account required.

Credits: the original idea came from Zane and Wei Sin during the OpenAI Codex Hackathon 2026. They later moved on to another project; I kept the attribution intact and rebuilt the current direction around the MCP-assisted editor/demo.

I would be especially interested in feedback on the MCP tool design: what extra spatial/layout tools would make the agent feel more like a real design collaborator rather than a script calling CRUD functions?

## Singapore-Focused Post

### Twitter/X draft

Built a tiny open-source HDB BTO interior-design toy: load a real BTO flat layout, type "design a minimalist 4-room family flat", and let Claude furnish it through an MCP server.

It is niche on purpose: Singapore BTO layouts, Three.js editor, furniture placement, sightline checks, and exported GLB/SVG/JSON.

Repo/demo: https://github.com/gongahkia/haus

### r/singapore / SG tech community draft

I built an open-source HDB BTO layout editor with an AI-agent twist.

You can load a pre-vectorized BTO floor plan, place furniture/walls in a Three.js editor, and use an MCP-powered chat panel to ask an LLM to arrange the flat. The goal is a fun technical demo rather than a commercial renovation planner: "design my 4-room BTO in a minimalist family style" and watch the agent call layout tools to furnish it.

Repo/demo: https://github.com/gongahkia/haus

Why HDB/BTO specifically: the layouts are familiar to Singaporeans, constrained enough for a good demo, and much more interesting than a generic empty-room planner.

## Launch Timing

- Target HN submission time: 8:00am PT.
- Singapore equivalent during June daylight saving time: 11:00pm SGT on the same calendar date.
- Reason: catches the start of the US workday while still being late evening in Singapore for local amplification.
- If launching outside US daylight saving time, re-check the conversion before posting.

## Messaging Guardrails

Lead with:

- AI-agent autonomy through MCP.
- Real Singapore HDB/BTO layouts.
- The visual demo: prompt to furnished flat.
- Open-source local workflow.

Avoid leading with explicitly cut scopes:

- Generic raster-to-vector floor-plan conversion.
- Real-estate photo staging.
- Multi-floor, BIM, or DXF workflows.
- Mobile AR scan or Apple RoomPlan-style capture.
- Generative text-to-floorplan.
- B2B sales to designers or contractors.
