from __future__ import annotations

from flask import Blueprint, jsonify, request, current_app, send_from_directory, render_template
from werkzeug.utils import secure_filename
import os
import hashlib

from .db import get_db
from .gedcom import parse_gedcom, to_summary
from .date_parser import parse_date
from .place_service import generate_place_suggestions, get_unstandardized_places, approve_place_variant
from .dedupe_service import generate_duplicate_candidates, get_duplicate_candidates, mark_duplicate_reviewed

api_bp = Blueprint("api", __name__, url_prefix="/api")
ui_bp = Blueprint("ui", __name__)

@ui_bp.get("/")
def index():
    return render_template("index.html")

@ui_bp.get("/analytics")
def analytics():
    return render_template("analytics.html")

def _row_to_person(row):
    return {
        "id": row["id"],
        "xref": row["xref"],
        "given": row["given"],
        "surname": row["surname"],
        "sex": row["sex"],
        "birth_date": row["birth_date"],
        "birth_place": row["birth_place"],
        "death_date": row["death_date"],
        "death_place": row["death_place"],
    }

@api_bp.get("/health")
def health():
    db = get_db()
    db.execute("SELECT 1;").fetchone()
    return jsonify({"ok": True})

@api_bp.get("/people")
def list_people():
    q = (request.args.get("q") or "").strip()
    db = get_db()
    if q:
        like = f"%{q}%"
        rows = db.execute(
            "SELECT * FROM persons WHERE given LIKE ? OR surname LIKE ? ORDER BY surname, given LIMIT 200",
            (like, like),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM persons ORDER BY surname, given LIMIT 200").fetchall()
    return jsonify([_row_to_person(r) for r in rows])

@api_bp.post("/people")
def create_person():
    data = request.get_json(force=True, silent=False)
    given = (data.get("given") or "").strip()
    surname = (data.get("surname") or "").strip()
    sex = (data.get("sex") or "").strip()
    birth_date = (data.get("birth_date") or "").strip()
    birth_place = (data.get("birth_place") or "").strip()
    death_date = (data.get("death_date") or "").strip()
    death_place = (data.get("death_place") or "").strip()

    if not given and not surname:
        return jsonify({"error": "Given or surname is required."}), 400

    db = get_db()
    cur = db.execute(
        """
        INSERT INTO persons (xref, given, surname, sex, birth_date, birth_place, death_date, death_place, updated_at)
        VALUES (NULL, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
        """,
        (given, surname, sex, birth_date, birth_place, death_date, death_place),
    )
    db.commit()
    pid = cur.lastrowid
    row = db.execute("SELECT * FROM persons WHERE id = ?", (pid,)).fetchone()
    return jsonify(_row_to_person(row)), 201

@api_bp.get("/people/<int:person_id>")
def get_person(person_id: int):
    db = get_db()
    row = db.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404

    notes = db.execute("SELECT id, note_text, created_at FROM notes WHERE person_id = ? ORDER BY id DESC", (person_id,)).fetchall()
    media = db.execute("SELECT id, file_name, original_name, mime_type, size_bytes, created_at FROM media WHERE person_id = ? ORDER BY id DESC", (person_id,)).fetchall()
    parents = db.execute(
        """
        SELECT p.* FROM relationships r
        JOIN persons p ON p.id = r.parent_person_id
        WHERE r.child_person_id = ?
        ORDER BY p.surname, p.given
        """,
        (person_id,),
    ).fetchall()
    children = db.execute(
        """
        SELECT p.* FROM relationships r
        JOIN persons p ON p.id = r.child_person_id
        WHERE r.parent_person_id = ?
        ORDER BY p.surname, p.given
        """,
        (person_id,),
    ).fetchall()

    out = _row_to_person(row)
    out["notes"] = [{"id": n["id"], "text": n["note_text"], "created_at": n["created_at"]} for n in notes]
    out["media"] = [{"id": m["id"], "file_name": m["file_name"], "original_name": m["original_name"], "mime_type": m["mime_type"], "size_bytes": m["size_bytes"], "created_at": m["created_at"]} for m in media]
    out["parents"] = [_row_to_person(p) for p in parents]
    out["children"] = [_row_to_person(c) for c in children]
    return jsonify(out)

@api_bp.put("/people/<int:person_id>")
def update_person(person_id: int):
    data = request.get_json(force=True, silent=False)
    fields = ["given","surname","sex","birth_date","birth_place","death_date","death_place"]
    updates = {k: (data.get(k) or "").strip() for k in fields}

    db = get_db()
    existing = db.execute("SELECT id FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not existing:
        return jsonify({"error": "Not found"}), 404

    # Parse dates if they were updated
    birth_canonical, birth_conf = parse_date(updates["birth_date"])
    death_canonical, death_conf = parse_date(updates["death_date"])

    db.execute(
        """
        UPDATE persons
        SET given=?, surname=?, sex=?, 
            birth_date=?, birth_date_canonical=?, birth_date_confidence=?,
            birth_place=?, 
            death_date=?, death_date_canonical=?, death_date_confidence=?,
            death_place=?, updated_at=datetime('now')
        WHERE id=?
        """,
        (updates["given"], updates["surname"], updates["sex"], 
         updates["birth_date"], birth_canonical, birth_conf,
         updates["birth_place"], 
         updates["death_date"], death_canonical, death_conf,
         updates["death_place"], person_id),
    )
    db.commit()
    row = db.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    return jsonify(_row_to_person(row))

@api_bp.delete("/people/<int:person_id>")
def delete_person(person_id: int):
    db = get_db()
    row = db.execute("SELECT id FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    db.execute("DELETE FROM persons WHERE id = ?", (person_id,))
    db.commit()
    return jsonify({"deleted": True})

@api_bp.post("/people/<int:person_id>/notes")
def add_note(person_id: int):
    data = request.get_json(force=True, silent=False)
    note = (data.get("text") or "").strip()
    if not note:
        return jsonify({"error": "Note text required"}), 400

    db = get_db()
    exists = db.execute("SELECT id FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not exists:
        return jsonify({"error": "Not found"}), 404

    cur = db.execute("INSERT INTO notes (person_id, note_text) VALUES (?, ?)", (person_id, note))
    db.commit()
    return jsonify({"id": cur.lastrowid}), 201

@api_bp.post("/import/gedcom")
def import_gedcom():
    db = get_db()

    if request.content_type and request.content_type.startswith("multipart/form-data"):
        f = request.files.get("file")
        if not f:
            return jsonify({"error": "file is required"}), 400
        text = f.read().decode("utf-8", errors="replace")
    else:
        payload = request.get_json(force=True, silent=False)
        text = (payload.get("gedcom") or "")
        if not text.strip():
            return jsonify({"error": "gedcom is required"}), 400

    indis, fams = parse_gedcom(text)

    def upsert_person(i):
        # Parse dates
        birth_canonical, birth_conf = parse_date(i.birth_date)
        death_canonical, death_conf = parse_date(i.death_date)
        
        row = db.execute("SELECT id FROM persons WHERE xref = ?", (i.xref,)).fetchone()
        if row:
            db.execute(
                """
                UPDATE persons SET given=?, surname=?, sex=?, 
                    birth_date=?, birth_date_canonical=?, birth_date_confidence=?,
                    birth_place=?, 
                    death_date=?, death_date_canonical=?, death_date_confidence=?,
                    death_place=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (i.given, i.surname, i.sex, 
                 i.birth_date, birth_canonical, birth_conf,
                 i.birth_place, 
                 i.death_date, death_canonical, death_conf,
                 i.death_place, row["id"]),
            )
            return row["id"]
        cur = db.execute(
            """
            INSERT INTO persons (xref, given, surname, sex, 
                birth_date, birth_date_canonical, birth_date_confidence, birth_place, 
                death_date, death_date_canonical, death_date_confidence, death_place, 
                updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (i.xref, i.given, i.surname, i.sex, 
             i.birth_date, birth_canonical, birth_conf, i.birth_place, 
             i.death_date, death_canonical, death_conf, i.death_place),
        )
        return cur.lastrowid

    xref_to_id = {}
    for i in indis.values():
        xref_to_id[i.xref] = upsert_person(i)

    def upsert_family(f):
        # Parse marriage date
        marriage_canonical, marriage_conf = parse_date(f.marriage_date)
        
        row = db.execute("SELECT id FROM families WHERE xref = ?", (f.xref,)).fetchone()
        husb_id = xref_to_id.get(f.husb) if f.husb else None
        wife_id = xref_to_id.get(f.wife) if f.wife else None
        if row:
            db.execute(
                """
                UPDATE families SET husband_person_id=?, wife_person_id=?, 
                    marriage_date=?, marriage_date_canonical=?, marriage_date_confidence=?,
                    marriage_place=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (husb_id, wife_id, 
                 f.marriage_date, marriage_canonical, marriage_conf,
                 f.marriage_place, row["id"]),
            )
            fam_id = row["id"]
        else:
            cur = db.execute(
                """
                INSERT INTO families (xref, husband_person_id, wife_person_id, 
                    marriage_date, marriage_date_canonical, marriage_date_confidence,
                    marriage_place, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (f.xref, husb_id, wife_id, 
                 f.marriage_date, marriage_canonical, marriage_conf,
                 f.marriage_place),
            )
            fam_id = cur.lastrowid

        for cxref in f.chil:
            cid = xref_to_id.get(cxref)
            if cid:
                db.execute("INSERT OR IGNORE INTO family_children (family_id, child_person_id) VALUES (?, ?)", (fam_id, cid))

        for n in f.notes:
            if n.strip():
                db.execute("INSERT INTO notes (family_id, note_text) VALUES (?, ?)", (fam_id, n.strip()))

        return fam_id

    for f in fams.values():
        upsert_family(f)

    for i in indis.values():
        pid = xref_to_id.get(i.xref)
        if pid:
            for n in i.notes:
                if n.strip():
                    db.execute("INSERT INTO notes (person_id, note_text) VALUES (?, ?)", (pid, n.strip()))

    # Rebuild relationships
    db.execute("DELETE FROM relationships;")
    fam_rows = db.execute("SELECT id, husband_person_id, wife_person_id FROM families").fetchall()
    for fr in fam_rows:
        kids = db.execute("SELECT child_person_id FROM family_children WHERE family_id = ?", (fr["id"],)).fetchall()
        for k in kids:
            child_id = k["child_person_id"]
            if fr["husband_person_id"]:
                db.execute(
                    "INSERT OR IGNORE INTO relationships (parent_person_id, child_person_id, rel_type) VALUES (?, ?, 'parent')",
                    (fr["husband_person_id"], child_id),
                )
            if fr["wife_person_id"]:
                db.execute(
                    "INSERT OR IGNORE INTO relationships (parent_person_id, child_person_id, rel_type) VALUES (?, ?, 'parent')",
                    (fr["wife_person_id"], child_id),
                )

    # Generate analytics data
    generate_place_suggestions(db)
    generate_duplicate_candidates(db)

    db.commit()
    return jsonify({"imported": to_summary(indis, fams)})

@api_bp.get("/tree/<int:person_id>")
def tree(person_id: int):
    db = get_db()
    root = db.execute("SELECT * FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not root:
        return jsonify({"error": "Not found"}), 404

    parents = db.execute(
        """
        SELECT p.* FROM relationships r
        JOIN persons p ON p.id = r.parent_person_id
        WHERE r.child_person_id = ?
        ORDER BY p.surname, p.given
        """,
        (person_id,),
    ).fetchall()
    children = db.execute(
        """
        SELECT p.* FROM relationships r
        JOIN persons p ON p.id = r.child_person_id
        WHERE r.parent_person_id = ?
        ORDER BY p.surname, p.given
        """,
        (person_id,),
    ).fetchall()

    return jsonify({
        "root": _row_to_person(root),
        "parents": [_row_to_person(p) for p in parents],
        "children": [_row_to_person(c) for c in children],
    })

@api_bp.post("/people/<int:person_id>/media")
def upload_media(person_id: int):
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "file is required"}), 400

    db = get_db()
    exists = db.execute("SELECT id FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not exists:
        return jsonify({"error": "Not found"}), 404

    original_name = f.filename or "upload"
    safe = secure_filename(original_name) or "upload.bin"

    media_dir = current_app.config["MEDIA_DIR"]
    os.makedirs(media_dir, exist_ok=True)

    content = f.read()
    sha = hashlib.sha256(content).hexdigest()
    ext = os.path.splitext(safe)[1].lower()
    stored_name = f"{sha}{ext}" if ext else sha
    path = os.path.join(media_dir, stored_name)

    if not os.path.exists(path):
        with open(path, "wb") as out:
            out.write(content)

    mime = f.mimetype or "application/octet-stream"
    size_bytes = len(content)

    db.execute(
        """
        INSERT INTO media (person_id, file_name, original_name, mime_type, sha256, size_bytes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (person_id, stored_name, original_name, mime, sha, size_bytes),
    )
    db.commit()

    return jsonify({"stored": stored_name, "sha256": sha}), 201

@api_bp.get("/media/<path:file_name>")
def get_media(file_name: str):
    media_dir = current_app.config["MEDIA_DIR"]
    return send_from_directory(media_dir, file_name, as_attachment=False)

# Analytics endpoints
@api_bp.get("/analytics/summary")
def analytics_summary():
    db = get_db()
    
    # Date stats
    total_persons = db.execute("SELECT COUNT(*) FROM persons").fetchone()[0]
    missing_birth_dates = db.execute(
        "SELECT COUNT(*) FROM persons WHERE birth_date IS NULL OR birth_date = ''"
    ).fetchone()[0]
    ambiguous_birth_dates = db.execute(
        "SELECT COUNT(*) FROM persons WHERE birth_date_confidence IN ('ambiguous', 'partial')"
    ).fetchone()[0]
    unparseable_birth_dates = db.execute(
        "SELECT COUNT(*) FROM persons WHERE birth_date IS NOT NULL AND birth_date != '' AND birth_date_confidence = 'unparseable'"
    ).fetchone()[0]
    
    # Place stats
    pending_place_variants = db.execute(
        "SELECT COUNT(*) FROM place_variants WHERE status = 'pending'"
    ).fetchone()[0]
    
    # Duplicate stats
    pending_duplicates = db.execute(
        "SELECT COUNT(*) FROM duplicate_candidates WHERE status = 'pending'"
    ).fetchone()[0]
    
    return jsonify({
        "total_persons": total_persons,
        "dates": {
            "missing_birth": missing_birth_dates,
            "ambiguous_birth": ambiguous_birth_dates,
            "unparseable_birth": unparseable_birth_dates,
        },
        "places": {
            "pending_variants": pending_place_variants,
        },
        "duplicates": {
            "pending": pending_duplicates,
        },
    })

@api_bp.get("/analytics/dates/missing")
def analytics_missing_dates():
    db = get_db()
    try:
        limit = int(request.args.get("limit", 100))
        limit = min(max(limit, 1), 1000)  # Clamp between 1 and 1000
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit parameter"}), 400
    
    rows = db.execute(
        """
        SELECT id, given, surname, birth_date, death_date
        FROM persons
        WHERE (birth_date IS NULL OR birth_date = '') AND (death_date IS NULL OR death_date = '')
        ORDER BY surname, given
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    
    return jsonify([
        {
            "id": r[0],
            "given": r[1],
            "surname": r[2],
            "birth_date": r[3],
            "death_date": r[4],
        }
        for r in rows
    ])

@api_bp.get("/analytics/dates/ambiguous")
def analytics_ambiguous_dates():
    db = get_db()
    try:
        limit = int(request.args.get("limit", 100))
        limit = min(max(limit, 1), 1000)  # Clamp between 1 and 1000
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit parameter"}), 400
    
    rows = db.execute(
        """
        SELECT id, given, surname, birth_date, birth_date_canonical, birth_date_confidence,
               death_date, death_date_canonical, death_date_confidence
        FROM persons
        WHERE birth_date_confidence IN ('ambiguous', 'partial', 'unparseable')
           OR death_date_confidence IN ('ambiguous', 'partial', 'unparseable')
        ORDER BY birth_date_confidence DESC, surname, given
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    
    return jsonify([
        {
            "id": r[0],
            "given": r[1],
            "surname": r[2],
            "birth_date": r[3],
            "birth_date_canonical": r[4],
            "birth_date_confidence": r[5],
            "death_date": r[6],
            "death_date_canonical": r[7],
            "death_date_confidence": r[8],
        }
        for r in rows
    ])

@api_bp.get("/analytics/places/unstandardized")
def analytics_unstandardized_places():
    db = get_db()
    try:
        limit = int(request.args.get("limit", 100))
        limit = min(max(limit, 1), 1000)  # Clamp between 1 and 1000
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit parameter"}), 400
    variants = get_unstandardized_places(db, limit)
    return jsonify(variants)

@api_bp.post("/analytics/places/approve")
def analytics_approve_place():
    data = request.get_json(force=True, silent=False)
    variant_id = data.get("variant_id")
    
    if not variant_id:
        return jsonify({"error": "variant_id is required"}), 400
    
    # Validate variant_id is an integer
    try:
        variant_id = int(variant_id)
    except (ValueError, TypeError):
        return jsonify({"error": "variant_id must be an integer"}), 400
    
    db = get_db()
    success = approve_place_variant(db, variant_id)
    
    if success:
        return jsonify({"approved": True})
    else:
        return jsonify({"error": "Variant not found"}), 404

@api_bp.get("/analytics/duplicates")
def analytics_duplicates():
    db = get_db()
    try:
        limit = int(request.args.get("limit", 100))
        limit = min(max(limit, 1), 1000)  # Clamp between 1 and 1000
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid limit parameter"}), 400
    candidates = get_duplicate_candidates(db, limit)
    return jsonify(candidates)

@api_bp.post("/analytics/duplicates/review")
def analytics_review_duplicate():
    data = request.get_json(force=True, silent=False)
    candidate_id = data.get("candidate_id")
    action = data.get("action")  # 'ignore' or 'merge'
    
    if not candidate_id or not action:
        return jsonify({"error": "candidate_id and action are required"}), 400
    
    # Validate candidate_id is an integer
    try:
        candidate_id = int(candidate_id)
    except (ValueError, TypeError):
        return jsonify({"error": "candidate_id must be an integer"}), 400
    
    if action not in ['ignore', 'merge']:
        return jsonify({"error": "action must be 'ignore' or 'merge'"}), 400
    
    # For this phase, only support 'ignore', not actual merging
    status = 'ignored' if action == 'ignore' else 'merged'
    
    db = get_db()
    success = mark_duplicate_reviewed(db, candidate_id, status)
    
    if success:
        return jsonify({"reviewed": True, "status": status})
    else:
        return jsonify({"error": "Candidate not found"}), 404
