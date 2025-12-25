# Data Quality Workflow

This app ships a deterministic “Data Quality” workflow for finding, reviewing, and fixing issues without silent mutations.

## Architecture
- **Detectors:** Implemented in `app/dq.py`. They write `dq_issues` rows plus supporting `date_normalizations` records.
- **Actions:** Logged in `dq_action_log` with reversible payloads. Undo is available via `POST /api/dq/actions/undo`.
- **UI:** `/data-quality` (template + `static/data-quality.js`) with tabs for overview, duplicates, places, dates, integrity, and change log.

## Detectors & thresholds
- **Duplicate people (`duplicate_person`):**
  - Normalized name similarity (SequenceMatcher) must be ≥ 0.68.
  - Birth-year delta ≤ 1 adds 0.25; death-year delta ≤ 1 adds 0.1; matching birth place adds 0.15.
  - Overall confidence ≥ 0.55 creates an issue.
- **Duplicate families (`duplicate_family`, `duplicate_family_spouse_swap`):**
  - Same spouse IDs with matching marriage date/place (score ≥ 0.75) or swapped spouse names with supporting date/place evidence (score ≥ 0.7).
  - Tracks marriage dates/places and spouse names in the explanation payload.
- **Duplicate media (`duplicate_media_link`, `duplicate_media_asset`):**
  - Duplicate links share the same asset/person/family (count > 1, confidence 0.9).
  - Media assets flagged when filename similarity ≥ 0.92 (size within 2% adds confidence).
- **Place clusters and similarities (`place_cluster`, `place_similarity`):**
  - Token-normalized variants from event `place_raw` and person birth/death places.
  - Two+ distinct variants with a shared normalized key create a cluster; top variant suggested as canonical.
  - Cross-variant similarity ≥ 0.8 suggests a canonical form even when normalized keys differ.
- **Date normalization (`date_normalization`):**
  - Parses ISO `YYYY-MM-DD`, `MM/DD/YYYY`, `DD/MM/YYYY`, `YYYY/MM/DD`, `Mon YYYY`, numeric month + year, ranges `BET yyyy AND yyyy`, and qualifiers `abt/about/bef/aft/est/calc/circa/ca`.
  - Stores normalized value, precision (day/month/year/range), qualifier, confidence, ambiguity flag.
  - Original raw is preserved; ambiguous parses become errors (person rows as `error`, event rows as `info`).
- **Integrity issues:**
  - Orphan events (no person/family) and orphan families (no spouses/children).
  - Impossible timelines (death year before birth year).
  - Parent/child age checks (parent birth within 12 years of child birth) and death-before-child checks.
  - Marriage too early (within 12 years of spouse birth) or after spouse death.
  - Placeholder names (`unknown`, `n/a`, etc.).

## API contract
- `POST /api/dq/scan?incremental=0|1` — run detectors; returns counts.
- `GET /api/dq/summary` — scoreboard with quality score, duplicate and place queues, integrity warnings, and % standardized dates.
- `GET /api/dq/issues?type=&status=&page=&perPage=` — paged issues list with explanations.
- `GET /api/dq/actions/log` — paged change log.
- `POST /api/dq/actions/mergePeople` — body `{fromId, intoId, fillMissing?, user?}` merges people, preserves relationships/events/media, logs undo.
- `POST /api/dq/actions/mergeFamilies` — body `{fromId, intoId, fillMissing?, user?}` merges families, consolidating children/media; logs undo.
- `POST /api/dq/actions/dedupeMediaLinks` — body `{link_ids[], keep_id, user?}` keeps one media link and removes the rest.
- `POST /api/dq/actions/mergeMediaAssets` — body `{fromId, intoId, user?}` merges media assets and moves links to the kept asset.
- `POST /api/dq/actions/normalizePlaces` — body `{canonical, variants[], user?}` maps variants to a canonical place, updates events/people, logs undo.
- `POST /api/dq/actions/normalizeDates` — body `{items:[{entity_type,entity_id,normalized,precision,qualifier,raw,confidence,ambiguous,field?}], user?}` updates normalized dates and event `date_canonical`.
- `POST /api/dq/actions/undo` — body `{action_id}` replays undo payload for the selected action.

## Database additions
- `dq_issues` — issues with type, severity, entity references, confidence, impact, explanation JSON, detected/resolved timestamps.
- `dq_action_log` — action payloads with undo payloads and actor.
- `date_normalizations` — normalized dates per entity, with precision/qualifier/confidence/ambiguity flags.

## Undo & safety
- Every write action logs an undo payload. Undo replays the prior state for merges, place normalization, and date normalization.
- Actions run in transactions via SQLAlchemy to keep referential integrity.
- No silent mutation: original raw values remain stored (`date_raw`, person birth/death strings, place_raw).

## Extending detectors
1. Add a new detector in `app/dq.py` that writes to `dq_issues` with an explanation payload.
2. Include the issue type in `/api/dq/issues` filtering and optionally the overview summary.
3. Add UI rendering in `data-quality.js` and the template if a new queue is needed.
