Title: Phase 4 — Media handling v2 (upload, thumbnails, link to person/family, unassigned queue)

Context
Media is pillar #3. We need lightweight uploads, thumbnail creation, and clean database references.

Goals
- Upload media (jpg/png/webp, and allow pdf/video to be stored even if no thumbnail is generated yet).
- Create thumbnails automatically for images (Pillow baseline).
- Store:
  - MediaAsset (path, sha256, original filename, mime, size, created_at)
  - Thumbnail path (if created) + dimensions
  - MediaLink records attaching assets to Person and/or Family
  - “Unassigned media” view (assets without links)
- UI:
  - Person details: show media thumbnails + attach/detach
  - Unassigned media page: browse, search, and attach to person/family
- Analytics hooks:
  - count orphaned/unassigned assets
  - people with no media

Non-goals
- No cloud storage. Local filesystem only.
- No face recognition.

Deliverables
- Endpoints: upload, list media, link/unlink, thumbnail serving.
- Robust file handling: safe filenames, dedupe by hash, avoid overwriting.
- Tests: upload image creates thumbnail, linking works, unassigned list works.

Acceptance criteria (Done)
- Uploading images generates thumbnails reliably.
- Media links appear in Person UI and can be managed.
- Unassigned queue exists and supports basic attach workflow.
- Unit tests pass.

How to verify
- Upload 10 photos, confirm thumbnails, attach a few, confirm unassigned count decreases.
