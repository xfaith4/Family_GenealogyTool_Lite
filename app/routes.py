from __future__ import annotations

from flask import Blueprint, jsonify, request, current_app, send_from_directory, render_template
from werkzeug.utils import secure_filename
import os
import hashlib

from .db import get_db
from .gedcom import parse_gedcom, to_summary

api_bp = Blueprint("api", __name__, url_prefix="/api")
ui_bp = Blueprint("ui", __name__)

@ui_bp.get("/")
def index():
    return render_template("index.html")

@ui_bp.get("/tree-v2")
def tree_v2():
    return render_template("tree-v2.html")

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

    db.execute(
        """
        UPDATE persons
        SET given=?, surname=?, sex=?, birth_date=?, birth_place=?, death_date=?, death_place=?, updated_at=datetime('now')
        WHERE id=?
        """,
        (updates["given"], updates["surname"], updates["sex"], updates["birth_date"], updates["birth_place"], updates["death_date"], updates["death_place"], person_id),
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
        row = db.execute("SELECT id FROM persons WHERE xref = ?", (i.xref,)).fetchone()
        if row:
            db.execute(
                """
                UPDATE persons SET given=?, surname=?, sex=?, birth_date=?, birth_place=?, death_date=?, death_place=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (i.given, i.surname, i.sex, i.birth_date, i.birth_place, i.death_date, i.death_place, row["id"]),
            )
            return row["id"]
        cur = db.execute(
            """
            INSERT INTO persons (xref, given, surname, sex, birth_date, birth_place, death_date, death_place, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
            """,
            (i.xref, i.given, i.surname, i.sex, i.birth_date, i.birth_place, i.death_date, i.death_place),
        )
        return cur.lastrowid

    xref_to_id = {}
    for i in indis.values():
        xref_to_id[i.xref] = upsert_person(i)

    def upsert_family(f):
        row = db.execute("SELECT id FROM families WHERE xref = ?", (f.xref,)).fetchone()
        husb_id = xref_to_id.get(f.husb) if f.husb else None
        wife_id = xref_to_id.get(f.wife) if f.wife else None
        if row:
            db.execute(
                """
                UPDATE families SET husband_person_id=?, wife_person_id=?, marriage_date=?, marriage_place=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (husb_id, wife_id, f.marriage_date, f.marriage_place, row["id"]),
            )
            fam_id = row["id"]
        else:
            cur = db.execute(
                """
                INSERT INTO families (xref, husband_person_id, wife_person_id, marriage_date, marriage_place, updated_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
                """,
                (f.xref, husb_id, wife_id, f.marriage_date, f.marriage_place),
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

@api_bp.get("/graph")
def graph():
    """
    Graph API endpoint for v2 tree navigation.
    Returns nodes (persons and families) and edges (relationships).
    
    Query params:
    - rootPersonId: Starting person (required)
    - depth: How many generations to traverse (default: 2, max: 5)
    """
    root_id = request.args.get("rootPersonId", type=int)
    depth = min(int(request.args.get("depth", 2)), 5)
    
    if not root_id:
        return jsonify({"error": "rootPersonId is required"}), 400
    
    db = get_db()
    root_person = db.execute("SELECT * FROM persons WHERE id = ?", (root_id,)).fetchone()
    if not root_person:
        return jsonify({"error": "Person not found"}), 404
    
    # Collect all person IDs to include
    person_ids = {root_id}
    to_explore = [(root_id, 0)]
    explored = set()
    
    while to_explore:
        person_id, current_depth = to_explore.pop(0)
        if person_id in explored or current_depth >= depth:
            continue
        explored.add(person_id)
        
        # Get parents
        parents = db.execute(
            """
            SELECT parent_person_id FROM relationships 
            WHERE child_person_id = ?
            """,
            (person_id,)
        ).fetchall()
        for p in parents:
            pid = p["parent_person_id"]
            person_ids.add(pid)
            to_explore.append((pid, current_depth + 1))
        
        # Get children
        children = db.execute(
            """
            SELECT child_person_id FROM relationships 
            WHERE parent_person_id = ?
            """,
            (person_id,)
        ).fetchall()
        for c in children:
            cid = c["child_person_id"]
            person_ids.add(cid)
            to_explore.append((cid, current_depth + 1))
    
    # Fetch all persons in the graph
    person_nodes = []
    for pid in person_ids:
        p = db.execute("SELECT * FROM persons WHERE id = ?", (pid,)).fetchone()
        if p:
            # Calculate quality flag (how complete is the data)
            has_birth = bool((p["birth_date"] or "").strip() or (p["birth_place"] or "").strip())
            has_death = bool((p["death_date"] or "").strip() or (p["death_place"] or "").strip())
            has_name = bool((p["given"] or "").strip() or (p["surname"] or "").strip())
            quality = "high" if (has_name and has_birth) else ("medium" if has_name else "low")
            
            person_nodes.append({
                "id": f"person_{p['id']}",
                "type": "person",
                "data": {
                    "id": p["id"],
                    "xref": p["xref"],
                    "given": p["given"],
                    "surname": p["surname"],
                    "sex": p["sex"],
                    "birth_date": p["birth_date"],
                    "birth_place": p["birth_place"],
                    "death_date": p["death_date"],
                    "death_place": p["death_place"],
                    "quality": quality,
                }
            })
    
    # Fetch all families involving these persons
    family_nodes = []
    family_ids_seen = set()
    
    if person_ids:
        placeholders = ",".join("?" * len(person_ids))
        families = db.execute(
            f"""
            SELECT DISTINCT f.* FROM families f
            WHERE f.husband_person_id IN ({placeholders})
               OR f.wife_person_id IN ({placeholders})
            """,
            list(person_ids) + list(person_ids)
        ).fetchall()
    else:
        families = []
    
    for f in families:
        fid = f["id"]
        if fid in family_ids_seen:
            continue
        family_ids_seen.add(fid)
        
        # Get children of this family
        children = db.execute(
            "SELECT child_person_id FROM family_children WHERE family_id = ?",
            (fid,)
        ).fetchall()
        child_ids = [c["child_person_id"] for c in children]
        
        family_nodes.append({
            "id": f"family_{fid}",
            "type": "family",
            "data": {
                "id": fid,
                "xref": f["xref"],
                "husband_id": f["husband_person_id"],
                "wife_id": f["wife_person_id"],
                "marriage_date": f["marriage_date"],
                "marriage_place": f["marriage_place"],
                "children": child_ids,
            }
        })
    
    # Build edges
    edges = []
    
    # Spouse edges: person -> family
    for f in families:
        fid = f["id"]
        if f["husband_person_id"] and f["husband_person_id"] in person_ids:
            edges.append({
                "id": f"spouse_h_{fid}",
                "source": f"person_{f['husband_person_id']}",
                "target": f"family_{fid}",
                "type": "spouse"
            })
        if f["wife_person_id"] and f["wife_person_id"] in person_ids:
            edges.append({
                "id": f"spouse_w_{fid}",
                "source": f"person_{f['wife_person_id']}",
                "target": f"family_{fid}",
                "type": "spouse"
            })
    
    # Child edges: family -> person
    for f in families:
        fid = f["id"]
        children = db.execute(
            "SELECT child_person_id FROM family_children WHERE family_id = ?",
            (fid,)
        ).fetchall()
        for idx, c in enumerate(children):
            cid = c["child_person_id"]
            if cid in person_ids:
                edges.append({
                    "id": f"child_{fid}_{cid}",
                    "source": f"family_{fid}",
                    "target": f"person_{cid}",
                    "type": "child"
                })
    
    return jsonify({
        "nodes": person_nodes + family_nodes,
        "edges": edges,
        "rootPersonId": root_id,
        "depth": depth,
    })
