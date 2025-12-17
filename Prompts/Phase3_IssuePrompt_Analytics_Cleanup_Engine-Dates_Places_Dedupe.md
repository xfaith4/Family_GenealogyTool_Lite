Title: Phase 3 — Analytics + cleanup cockpit (dates yyyy-MM-dd, places standardization, dedupe suggestions)

Context
Analytics/cleanup is pillar #2. We need to turn messy GEDCOM data into clean, consistent data with a safe workflow.

Goals
- Dates:
  - Parse raw GEDCOM date strings into canonical `yyyy-MM-dd` where possible.
  - Store canonical date + keep raw/original + confidence/ambiguity flag.
- Places:
  - Add place normalization support using Places + PlaceVariants tables.
  - Generate suggestion candidates using RapidFuzz (or equivalent maintained fuzzy matcher).
- Dedupe:
  - Add “duplicate candidates” suggestions for people based on name + date + place similarity.
- UI:
  - Create an Analytics dashboard page listing:
    - missing dates, ambiguous dates
    - top “unstandardized” places
    - duplicate candidates queue
  - Provide an “Apply fix” flow for at least:
    - approve place variant → canonical place
    - mark candidate duplicates as “reviewed/ignored”

Non-goals
- No irreversible merges in this phase unless there is an audit trail + undo plan.
- No heavy external geocoding.

Deliverables
- New endpoints: analytics summary + list endpoints for queues.
- Backend service layer for parsing/standardizing (deterministic, testable).
- UI page: simple tables, filters, and “mark reviewed” actions.
- Tests: date parsing behaviors, place suggestion generation, “mark reviewed” endpoint.

Acceptance criteria (Done)
- Canonical dates are stored in yyyy-MM-dd when reasonably parseable, else flagged.
- Place suggestion queue populates for a messy GEDCOM.
- Analytics page loads and drives at least one cleanup workflow.
- Unit tests pass.

How to verify
- Import GEDCOM with messy dates/places, open Analytics, review queues, apply one place normalization, confirm DB updated.
