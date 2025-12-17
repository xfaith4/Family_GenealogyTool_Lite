Title: Phase 2 — Tree Navigation v2 (Graph API + Cytoscape.js + elk, feature-flagged)

Context
Tree navigation is one of the three “must win” pillars. We need a smooth, scalable, elegant tree/graph view that can handle imperfect genealogy structure (multiple spouses, step/adopt later, missing links).

Goals
- Add a Graph API endpoint that returns:
  - nodes: person and family nodes, key facts (name, birth/death), quality flags
  - edges: parent/child and spouse/family relationships
  - focus parameters: root person id, depth limit, optional “expand node”
- Implement a new tree UI using Cytoscape.js + elk layout behind a feature flag (e.g., ?tree=v2 or config).
- Keep current tree view as fallback.

Non-goals
- No full visual polish perfection; just professional, fast, usable.
- No React/Vite. Keep vanilla JS.

Deliverables
- Backend: `GET /api/graph?rootPersonId=...&depth=...`
- Frontend: new JS module to render graph (zoom/pan, click node → side panel).
- Basic performance-minded behavior: lazy expansion OR depth limit supported.
- Tests: graph endpoint returns correct structure for a small imported GEDCOM.

Acceptance criteria (Done)
- With a sample GEDCOM, v2 tree loads fast and supports zoom/pan + click-to-inspect.
- Old tree view remains available and functional.
- Unit tests pass.

How to verify
- Start app, import GEDCOM, open v2 tree, navigate 3–4 generations smoothly.
- Run tests.
