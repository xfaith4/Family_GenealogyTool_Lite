from __future__ import annotations

from flask import Blueprint, jsonify, request, current_app, send_from_directory, render_template
from werkzeug.utils import secure_filename
import os
import hashlib
import shutil

from .db import get_db
from .gedcom import parse_gedcom, to_summary
from . import APP_VERSION

api_bp = Blueprint("api", __name__, url_prefix="/api")
ui_bp = Blueprint("ui", __name__)

@ui_bp.get("/")
def index():
    return render_template("index.html")

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
            current_app.logger.warning("GEDCOM import failed: no file provided")
            return jsonify({"error": "file is required"}), 400
        text = f.read().decode("utf-8", errors="replace")
    else:
        payload = request.get_json(force=True, silent=False)
        text = (payload.get("gedcom") or "")
        if not text.strip():
            current_app.logger.warning("GEDCOM import failed: empty gedcom content")
            return jsonify({"error": "gedcom is required"}), 400

    try:
        indis, fams = parse_gedcom(text)
    except (ValueError, KeyError, AttributeError) as e:
        current_app.logger.error(f"GEDCOM parsing failed: {str(e)}", exc_info=True)
        return jsonify({"error": f"Failed to parse GEDCOM: {str(e)}"}), 400


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
    
    # Track last import timestamp
    db.execute(
        "INSERT OR REPLACE INTO metadata (key, value, updated_at) VALUES ('last_import', datetime('now'), datetime('now'))"
    )
    db.commit()
    
    current_app.logger.info(f"GEDCOM import successful: {len(indis)} people, {len(fams)} families")
    
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
        current_app.logger.warning(f"Media upload failed for person {person_id}: no file provided")
        return jsonify({"error": "file is required"}), 400

    db = get_db()
    exists = db.execute("SELECT id FROM persons WHERE id = ?", (person_id,)).fetchone()
    if not exists:
        current_app.logger.warning(f"Media upload failed: person {person_id} not found")
        return jsonify({"error": "Not found"}), 404

    original_name = f.filename or "upload"
    safe = secure_filename(original_name) or "upload.bin"

    media_dir = current_app.config["MEDIA_DIR"]
    os.makedirs(media_dir, exist_ok=True)

    try:
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
        
        current_app.logger.info(f"Media uploaded for person {person_id}: {original_name} ({size_bytes} bytes)")

        return jsonify({"stored": stored_name, "sha256": sha}), 201
    except (IOError, OSError) as e:
        current_app.logger.error(f"Media upload failed for person {person_id}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Failed to upload media: {str(e)}"}), 500

@api_bp.get("/media/<path:file_name>")
def get_media(file_name: str):
    media_dir = current_app.config["MEDIA_DIR"]
    return send_from_directory(media_dir, file_name, as_attachment=False)

@api_bp.get("/diagnostics")
def diagnostics():
    db = get_db()
    db_path = current_app.config["DATABASE"]
    
    # Get counts
    people_count = db.execute("SELECT COUNT(*) as cnt FROM persons").fetchone()["cnt"]
    families_count = db.execute("SELECT COUNT(*) as cnt FROM families").fetchone()["cnt"]
    media_count = db.execute("SELECT COUNT(*) as cnt FROM media").fetchone()["cnt"]
    
    # Get unassigned media (media without valid person)
    # Since we have ON DELETE CASCADE, this shouldn't happen, but check anyway
    unassigned_media = 0
    
    # Get schema version and last import
    schema_version_row = db.execute("SELECT value FROM metadata WHERE key = 'schema_version'").fetchone()
    schema_version = schema_version_row["value"] if schema_version_row else "unknown"
    
    last_import_row = db.execute("SELECT value FROM metadata WHERE key = 'last_import'").fetchone()
    last_import = last_import_row["value"] if last_import_row else None
    
    # Get DB file size
    db_size_bytes = 0
    if os.path.exists(db_path):
        db_size_bytes = os.path.getsize(db_path)
    
    return jsonify({
        "app_version": APP_VERSION,
        "db_path": db_path,
        "db_size_bytes": db_size_bytes,
        "schema_version": schema_version,
        "counts": {
            "people": people_count,
            "families": families_count,
            "media": media_count,
            "unassigned_media": unassigned_media,
        },
        "last_import": last_import,
    })

@api_bp.post("/backup")
def create_backup():
    """
    Create a backup of the database and optionally media files.
    
    SECURITY NOTE: This endpoint does not require authentication. In production,
    consider adding rate limiting or authentication to prevent unauthorized users
    from triggering backups repeatedly, which could cause disk space exhaustion
    or performance issues.
    """
    from datetime import datetime
    from pathlib import Path
    
    db_path = current_app.config["DATABASE"]
    media_dir = current_app.config["MEDIA_DIR"]
    
    # Create backups directory
    repo_root = Path(__file__).resolve().parents[1]
    backup_dir = repo_root / "backups"
    backup_dir.mkdir(exist_ok=True)
    
    # Create timestamped backup
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_name = f"backup_{timestamp}"
    backup_path = backup_dir / backup_name
    backup_path.mkdir(exist_ok=True)
    
    try:
        # Backup database
        db_backup_path = backup_path / "family_tree.sqlite"
        shutil.copy2(db_path, db_backup_path)
        
        # Backup media directory if it exists and has files
        media_backup_path = backup_path / "media"
        if os.path.exists(media_dir) and os.listdir(media_dir):
            shutil.copytree(media_dir, media_backup_path)
            media_count = len(os.listdir(media_backup_path))
        else:
            media_count = 0
        
        db_size = os.path.getsize(db_backup_path)
        
        current_app.logger.info(f"Backup created: {backup_name} (DB: {db_size} bytes, Media files: {media_count})")
        
        return jsonify({
            "success": True,
            "backup_name": backup_name,
            "db_size_bytes": db_size,
            "media_files": media_count,
            "timestamp": timestamp,
        }), 201
    except (IOError, OSError, shutil.Error) as e:
        current_app.logger.error(f"Backup failed: {str(e)}", exc_info=True)
        return jsonify({"error": f"Backup failed: {str(e)}"}), 500

@api_bp.post("/restore")
def restore_backup():
    """
    Restore from a backup.
    
    WARNING: The application should be restarted after a restore operation
    to ensure all database connections are refreshed and no stale data is cached.
    """
    from pathlib import Path
    import re
    
    data = request.get_json(force=True, silent=False)
    backup_name = (data.get("backup_name") or "").strip()
    
    if not backup_name:
        return jsonify({"error": "backup_name is required"}), 400
    
    # Validate backup_name format to prevent path traversal
    if not re.match(r'^backup_\d{8}_\d{6}$', backup_name):
        current_app.logger.warning(f"Restore failed: invalid backup name format: {backup_name}")
        return jsonify({"error": "Invalid backup name format"}), 400
    
    repo_root = Path(__file__).resolve().parents[1]
    backup_dir = repo_root / "backups" / backup_name
    
    # Ensure the resolved path is still within the backups directory
    if not str(backup_dir.resolve()).startswith(str((repo_root / "backups").resolve())):
        current_app.logger.warning(f"Restore failed: path traversal attempt: {backup_name}")
        return jsonify({"error": "Invalid backup name"}), 400
    
    if not backup_dir.exists():
        current_app.logger.warning(f"Restore failed: backup {backup_name} not found")
        return jsonify({"error": f"Backup '{backup_name}' not found"}), 404
    
    db_backup = backup_dir / "family_tree.sqlite"
    if not db_backup.exists():
        current_app.logger.warning(f"Restore failed: no database file in backup {backup_name}")
        return jsonify({"error": f"No database file in backup '{backup_name}'"}), 404
    
    try:
        db_path = current_app.config["DATABASE"]
        media_dir = current_app.config["MEDIA_DIR"]
        
        # Close current DB connection
        from flask import g
        db = g.pop("db", None)
        if db is not None:
            db.close()
        
        # Restore database
        shutil.copy2(db_backup, db_path)
        
        # Restore media if exists
        media_backup = backup_dir / "media"
        media_count = 0
        if media_backup.exists():
            # Clear current media
            if os.path.exists(media_dir):
                shutil.rmtree(media_dir)
            shutil.copytree(media_backup, media_dir)
            media_count = len(os.listdir(media_dir))
        
        current_app.logger.info(f"Restore successful from backup: {backup_name}")
        
        return jsonify({
            "success": True,
            "restored_from": backup_name,
            "media_files": media_count,
            "warning": "Please restart the application to ensure all database connections are refreshed.",
        }), 200
    except (IOError, OSError, shutil.Error) as e:
        current_app.logger.error(f"Restore failed from {backup_name}: {str(e)}", exc_info=True)
        return jsonify({"error": f"Restore failed: {str(e)}"}), 500

