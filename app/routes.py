from __future__ import annotations

from flask import Blueprint, jsonify, request, current_app, send_from_directory, render_template
from typing import Any, Dict, List, Iterable, Tuple
from werkzeug.utils import secure_filename
from sqlalchemy import select, or_, and_, func, update, text
from sqlalchemy.exc import IntegrityError
from datetime import datetime
import os
import hashlib
from pathlib import Path
import tempfile
import zipfile
import sqlite3
import shutil
import mimetypes
import logging
import json

from .db import get_session
from .models import (
    Person,
    Family,
    Note,
    Event,
    EventType,
    MediaAsset,
    MediaLink,
    PersonAttribute,
    relationships,
    family_children,
    DataQualityIssue,
    DataQualityActionLog,
    DateNormalization,
    Place,
    PlaceVariant,
)
from .gedcom import parse_gedcom, to_summary
from .media_utils import compute_sha256, is_image, create_thumbnail, safe_filename
from .rmtree import (
    collect_media_associations,
    collect_media_locations,
    collect_person_records,
    collect_relationship_records,
    load_tables_from_sqlite,
    sqlite_schema_fingerprint,
)
from .dq import run_detection, build_summary, log_action, clean_person_fields

import re
from collections import Counter

api_bp = Blueprint("api", __name__, url_prefix="/api")
ui_bp = Blueprint("ui", __name__)
RELATIONSHIP_PARENT_TYPE = "parent"
MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".mp4", ".mov", ".avi", ".mkv"}
LOG_RESERVED_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
}


def _sanitize_log_extra(extra: Dict[str, Any] | None) -> Dict[str, Any]:
    if not extra:
        return {}
    sanitized: Dict[str, Any] = {}
    for key, value in extra.items():
        target = f"ctx_{key}" if key in LOG_RESERVED_KEYS else key
        sanitized[target] = value
    return sanitized


def _log_info(logger: logging.Logger, message: str, extra: Dict[str, Any] | None = None) -> None:
    logger.info(message, extra=_sanitize_log_extra(extra))


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _media_paths() -> Tuple[Path, Path]:
    media_dir = Path(current_app.config["MEDIA_DIR"])
    ingest_dir = Path(current_app.config.get("MEDIA_INGEST_DIR") or media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    ingest_dir.mkdir(parents=True, exist_ok=True)
    return media_dir, ingest_dir


def _ensure_thumbnail(dest: Path, sha: str, mime: str) -> Tuple[str | None, int | None, int | None]:
    media_dir, _ = _media_paths()
    thumbnail_path = None
    thumb_w = None
    thumb_h = None
    if is_image(mime):
        thumb_result = create_thumbnail(dest.as_posix(), media_dir.as_posix(), sha)
        if thumb_result:
            thumbnail_path = os.path.basename(thumb_result[0])
            thumb_w = thumb_result[1]
            thumb_h = thumb_result[2]
    return thumbnail_path, thumb_w, thumb_h


def _find_placeholder_asset(session, original_name: str) -> MediaAsset | None:
    return (
        session.execute(
            select(MediaAsset).where(MediaAsset.original_filename == original_name).order_by(MediaAsset.created_at.desc())
        ).scalar_one_or_none()
    )


def _register_media_from_path(file_path: Path, session, original_name: str | None = None) -> Tuple[MediaAsset, bool]:
    media_dir, _ = _media_paths()
    name = original_name or file_path.name
    mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
    sha = _hash_file(file_path)

    existing = session.execute(select(MediaAsset).where(MediaAsset.sha256 == sha)).scalar_one_or_none()
    if existing:
        if not existing.source_path:
            existing.source_path = str(file_path)
        if not existing.path:
            stored = safe_filename(name, sha, mime)
            dest = media_dir / stored
            if not dest.exists():
                shutil.copyfile(file_path, dest)
            existing.path = stored
        return existing, False

    placeholder = _find_placeholder_asset(session, name)
    stored_name = safe_filename(name, sha, mime)
    dest = media_dir / stored_name
    if not dest.exists():
        shutil.copyfile(file_path, dest)

    thumbnail_path, thumb_w, thumb_h = _ensure_thumbnail(dest, sha, mime)

    if placeholder:
        placeholder.sha256 = sha
        placeholder.path = stored_name
        placeholder.mime_type = mime
        placeholder.size_bytes = file_path.stat().st_size
        placeholder.source_path = placeholder.source_path or str(file_path)
        placeholder.thumbnail_path = thumbnail_path
        placeholder.thumb_width = thumb_w
        placeholder.thumb_height = thumb_h
        placeholder.status = placeholder.status or "unassigned"
        session.flush()
        return placeholder, False

    asset = MediaAsset(
        path=stored_name,
        sha256=sha,
        original_filename=name,
        mime_type=mime,
        size_bytes=file_path.stat().st_size,
        thumbnail_path=thumbnail_path,
        thumb_width=thumb_w,
        thumb_height=thumb_h,
        source_path=str(file_path),
        status="unassigned",
    )
    session.add(asset)
    session.flush()
    return asset, True


def _refresh_asset_status(session, asset_id: int) -> None:
    link_count = session.execute(select(func.count(MediaLink.id)).where(MediaLink.asset_id == asset_id)).scalar_one()
    asset = session.get(MediaAsset, asset_id)
    if asset:
        media_dir, _ = _media_paths()
        has_file = bool(asset.path) and (media_dir / asset.path).exists()
        if asset.size_bytes is None or not asset.path or not has_file:
            asset.status = "unassigned"
        else:
            asset.status = "assigned" if link_count else "unassigned"
        session.flush()


def _scan_ingest_directory(session) -> int:
    _, ingest_dir = _media_paths()
    if not ingest_dir.exists():
        return 0
    new_assets = 0
    changed = False
    for entry in ingest_dir.iterdir():
        if not entry.is_file():
            continue
        if entry.suffix.lower() not in MEDIA_EXTS:
            continue
        _, created = _register_media_from_path(entry, session)
        changed = True
        if created:
            new_assets += 1
    if changed:
        session.commit()
    return new_assets

@ui_bp.get("/")
def index():
    return render_template("index.html")

@ui_bp.get("/media/unassigned")
def unassigned_media_page():
    return render_template("unassigned.html")

@ui_bp.get("/tree-v2")
def tree_v2_page():
    return render_template("tree-v2.html")

@ui_bp.get("/analytics")
def analytics_page():
    return render_template("analytics.html")

@ui_bp.get("/service-worker.js")
def service_worker():
    return send_from_directory(current_app.static_folder, "service-worker.js")

def _attribute_to_dict(attr: PersonAttribute) -> dict:
    return {
        "id": attr.id,
        "key": attr.key,
        "value": attr.value,
        "created_at": attr.created_at.isoformat() if attr.created_at else None,
    }


def _sorted_attrs(person: Person) -> list[PersonAttribute]:
    return sorted(person.attributes, key=lambda a: (a.created_at or datetime.min, a.id or 0))


def _person_to_dict(p: Person, include_profile: bool = False) -> dict:
    data = {
        "id": p.id,
        "xref": p.xref,
        "given": p.given,
        "surname": p.surname,
        "sex": p.sex,
        "birth_date": p.birth_date,
        "birth_place": p.birth_place,
        "death_date": p.death_date,
        "death_place": p.death_place,
    }
    if include_profile:
        data["attributes"] = [_attribute_to_dict(a) for a in _sorted_attrs(p)]
    return data


def _family_to_dict(f: Family) -> dict:
    return {
        "id": f.id,
        "xref": f.xref,
        "husband_person_id": f.husband_person_id,
        "wife_person_id": f.wife_person_id,
        "marriage_date": f.marriage_date,
        "marriage_place": f.marriage_place,
    }

@api_bp.get("/health")
def health():
    session = get_session()
    session.execute(select(1))
    return jsonify({"ok": True})

@api_bp.get("/people")
def list_people():
    q = (request.args.get("q") or "").strip()
    session = get_session()
    
    if q:
        stmt = select(Person).where(
            or_(Person.given.like(f"%{q}%"), Person.surname.like(f"%{q}%"))
        ).order_by(Person.surname, Person.given).limit(200)
    else:
        stmt = select(Person).order_by(Person.surname, Person.given).limit(200)
    
    people = session.execute(stmt).scalars().all()
    return jsonify([_person_to_dict(p) for p in people])


@api_bp.post("/people/bulk")
def people_bulk():
    data = request.get_json(force=True, silent=False)
    ids = data.get("ids") or []
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return jsonify({"items": []})
    session = get_session()
    people = session.execute(select(Person).where(Person.id.in_(ids))).scalars().all()
    return jsonify({"items": [_person_to_dict(p) for p in people]})

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

    session = get_session()
    person = Person(
        given=given or None,
        surname=surname or None,
        sex=sex or None,
        birth_date=birth_date or None,
        birth_place=birth_place or None,
        death_date=death_date or None,
        death_place=death_place or None,
        updated_at=datetime.utcnow()
    )
    session.add(person)
    session.commit()
    session.refresh(person)
    
    return jsonify(_person_to_dict(person)), 201

@api_bp.get("/people/<int:person_id>")
def get_person(person_id: int):
    session = get_session()
    person = session.get(Person, person_id)
    if not person:
        return jsonify({"error": "Not found"}), 404

    # Get parents
    parents_stmt = select(Person).join(
        relationships, relationships.c.parent_person_id == Person.id
    ).where(relationships.c.child_person_id == person_id).order_by(Person.surname, Person.given)
    parents = session.execute(parents_stmt).scalars().all()

    # Get children
    children_stmt = select(Person).join(
        relationships, relationships.c.child_person_id == Person.id
    ).where(relationships.c.parent_person_id == person_id).order_by(Person.surname, Person.given)
    children = session.execute(children_stmt).scalars().all()

    out = _person_to_dict(person, include_profile=True)
    out["notes"] = [{"id": n.id, "text": n.note_text, "created_at": n.created_at.isoformat() if n.created_at else None} for n in person.notes]
    
    # Get media through MediaLink
    media_list = []
    for link in person.media_links:
        asset = link.media_asset
        media_list.append({
            "id": asset.id,
            "path": asset.path,
            "original_filename": asset.original_filename,
            "mime_type": asset.mime_type,
            "size_bytes": asset.size_bytes,
            "created_at": asset.created_at.isoformat() if asset.created_at else None
        })
    
    out["media"] = media_list
    out["parents"] = [_person_to_dict(p) for p in parents]
    out["children"] = [_person_to_dict(c) for c in children]
    return jsonify(out)

@api_bp.put("/people/<int:person_id>")
def update_person(person_id: int):
    data = request.get_json(force=True, silent=False)
    fields = ["given","surname","sex","birth_date","birth_place","death_date","death_place"]
    updates = {k: (data.get(k) or "").strip() for k in fields}

    session = get_session()
    person = session.get(Person, person_id)
    if not person:
        return jsonify({"error": "Not found"}), 404

    person.given = updates["given"] or None
    person.surname = updates["surname"] or None
    person.sex = updates["sex"] or None
    person.birth_date = updates["birth_date"] or None
    person.birth_place = updates["birth_place"] or None
    person.death_date = updates["death_date"] or None
    person.death_place = updates["death_place"] or None
    person.updated_at = datetime.utcnow()
    
    session.commit()
    session.refresh(person)
    return jsonify(_person_to_dict(person, include_profile=True))


@api_bp.get("/people/<int:person_id>/clean")
def preview_person_clean(person_id: int):
    session = get_session()
    try:
        result = clean_person_fields(session, person_id, apply=False)
    except ValueError:
        return jsonify({"error": "Not found"}), 404
    return jsonify(result)


@api_bp.post("/people/<int:person_id>/clean")
def apply_person_clean(person_id: int):
    payload = request.get_json(force=False, silent=True) or {}
    apply_flag = bool(payload.get("apply", True))
    session = get_session()
    try:
        result = clean_person_fields(session, person_id, apply=apply_flag, applied_by="api")
    except ValueError:
        return jsonify({"error": "Not found"}), 404
    return jsonify(result)

@api_bp.delete("/people/<int:person_id>")
def delete_person(person_id: int):
    session = get_session()
    person = session.get(Person, person_id)
    if not person:
        return jsonify({"error": "Not found"}), 404
    
    session.delete(person)
    session.commit()
    return jsonify({"deleted": True})

@api_bp.post("/people/<int:person_id>/notes")
def add_note(person_id: int):
    data = request.get_json(force=True, silent=False)
    note_text = (data.get("text") or "").strip()
    if not note_text:
        return jsonify({"error": "Note text required"}), 400

    session = get_session()
    person = session.get(Person, person_id)
    if not person:
        return jsonify({"error": "Not found"}), 404

    note = Note(person_id=person_id, note_text=note_text)
    session.add(note)
    session.commit()
    session.refresh(note)
    return jsonify({"id": note.id}), 201


@api_bp.get("/people/<int:person_id>/attributes")
def list_person_attributes(person_id: int):
    session = get_session()
    person = session.get(Person, person_id)
    if not person:
        return jsonify({"error": "Not found"}), 404
    return jsonify([_attribute_to_dict(a) for a in _sorted_attrs(person)])


@api_bp.post("/people/<int:person_id>/attributes")
def add_person_attribute(person_id: int):
    data = request.get_json(force=True, silent=False)
    key = (data.get("key") or "").strip()
    value = (data.get("value") or "").strip()
    if not key or not value:
        return jsonify({"error": "Key and value are required."}), 400

    session = get_session()
    person = session.get(Person, person_id)
    if not person:
        return jsonify({"error": "Not found"}), 404

    attr = PersonAttribute(person_id=person_id, key=key, value=value)
    session.add(attr)
    session.commit()
    session.refresh(attr)
    return jsonify(_attribute_to_dict(attr)), 201


@api_bp.delete("/people/<int:person_id>/attributes/<int:attr_id>")
def delete_person_attribute(person_id: int, attr_id: int):
    session = get_session()
    attr = session.get(PersonAttribute, attr_id)
    if not attr or attr.person_id != person_id:
        return jsonify({"error": "Not found"}), 404
    session.delete(attr)
    session.commit()
    return jsonify({"deleted": True})


@api_bp.get("/families/<int:family_id>")
def get_family(family_id: int):
    session = get_session()
    family = session.get(Family, family_id)
    if not family:
        return jsonify({"error": "Not found"}), 404

    husband = session.get(Person, family.husband_person_id) if family.husband_person_id else None
    wife = session.get(Person, family.wife_person_id) if family.wife_person_id else None

    children_ids = session.execute(
        select(family_children.c.child_person_id).where(family_children.c.family_id == family_id)
    ).scalars().all()
    children = []
    if children_ids:
        children = session.execute(select(Person).where(Person.id.in_(children_ids))).scalars().all()

    media_list = []
    for link in family.media_links:
        asset = link.media_asset
        media_list.append({
            "id": asset.id,
            "path": asset.path,
            "original_filename": asset.original_filename,
            "mime_type": asset.mime_type,
            "size_bytes": asset.size_bytes,
            "created_at": asset.created_at.isoformat() if asset.created_at else None
        })

    out = _family_to_dict(family)
    out["husband"] = _person_to_dict(husband) if husband else None
    out["wife"] = _person_to_dict(wife) if wife else None
    out["children"] = [_person_to_dict(c) for c in children]
    out["notes"] = [{"id": n.id, "text": n.note_text, "created_at": n.created_at.isoformat() if n.created_at else None} for n in family.notes]
    out["media"] = media_list
    return jsonify(out)

@api_bp.post("/import/gedcom")
def import_gedcom():
    session = get_session()

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
        stmt = select(Person).where(Person.xref == i.xref)
        person = session.execute(stmt).scalar_one_or_none()
        
        if person:
            person.given = i.given or None
            person.surname = i.surname or None
            person.sex = i.sex or None
            person.birth_date = i.birth_date or None
            person.birth_place = i.birth_place or None
            person.death_date = i.death_date or None
            person.death_place = i.death_place or None
            person.updated_at = datetime.utcnow()
        else:
            person = Person(
                xref=i.xref,
                given=i.given or None,
                surname=i.surname or None,
                sex=i.sex or None,
                birth_date=i.birth_date or None,
                birth_place=i.birth_place or None,
                death_date=i.death_date or None,
                death_place=i.death_place or None,
                updated_at=datetime.utcnow()
            )
            session.add(person)
        session.flush()
        return person.id

    xref_to_id = {}
    for i in indis.values():
        xref_to_id[i.xref] = upsert_person(i)

    def upsert_family(f):
        stmt = select(Family).where(Family.xref == f.xref)
        family = session.execute(stmt).scalar_one_or_none()
        
        husb_id = xref_to_id.get(f.husb) if f.husb else None
        wife_id = xref_to_id.get(f.wife) if f.wife else None
        
        if family:
            family.husband_person_id = husb_id
            family.wife_person_id = wife_id
            family.marriage_date = f.marriage_date or None
            family.marriage_place = f.marriage_place or None
            family.updated_at = datetime.utcnow()
        else:
            family = Family(
                xref=f.xref,
                husband_person_id=husb_id,
                wife_person_id=wife_id,
                marriage_date=f.marriage_date or None,
                marriage_place=f.marriage_place or None,
                updated_at=datetime.utcnow()
            )
            session.add(family)
        session.flush()
        
        # Clear existing children and re-add
        session.execute(
            relationships.delete().where(
                (relationships.c.parent_person_id == husb_id) | 
                (relationships.c.parent_person_id == wife_id)
            )
        )
        
        for cxref in f.chil:
            cid = xref_to_id.get(cxref)
            if cid:
                # Add to family_children (we need to import this)
                from .models import family_children
                # Check if already exists
                existing = session.execute(
                    select(family_children).where(
                        (family_children.c.family_id == family.id) &
                        (family_children.c.child_person_id == cid)
                    )
                ).first()
                if not existing:
                    session.execute(
                        family_children.insert().values(
                            family_id=family.id,
                            child_person_id=cid
                        )
                    )

        for n_text in f.notes:
            if n_text.strip():
                note = Note(family_id=family.id, note_text=n_text.strip())
                session.add(note)

        return family.id

    for f in fams.values():
        upsert_family(f)

    for i in indis.values():
        pid = xref_to_id.get(i.xref)
        if pid:
            for n_text in i.notes:
                if n_text.strip():
                    note = Note(person_id=pid, note_text=n_text.strip())
                    session.add(note)

    # Rebuild relationships
    session.execute(relationships.delete())
    families = session.execute(select(Family)).scalars().all()
    
    for fam in families:
        # Get children of this family
        from .models import family_children
        kids_stmt = select(family_children.c.child_person_id).where(
            family_children.c.family_id == fam.id
        )
        kids = session.execute(kids_stmt).scalars().all()
        
        for child_id in kids:
            if fam.husband_person_id:
                try:
                    session.execute(
                        relationships.insert().values(
                            parent_person_id=fam.husband_person_id,
                            child_person_id=child_id,
                            rel_type=RELATIONSHIP_PARENT_TYPE
                        )
                    )
                except Exception:
                    # Relationship already exists, ignore
                    pass
            if fam.wife_person_id:
                try:
                    session.execute(
                        relationships.insert().values(
                            parent_person_id=fam.wife_person_id,
                            child_person_id=child_id,
                            rel_type=RELATIONSHIP_PARENT_TYPE
                        )
                    )
                except Exception:
                    # Relationship already exists, ignore
                    pass

    session.commit()
    return jsonify({"imported": to_summary(indis, fams)})

@api_bp.post("/import/rmtree")
def import_rmtree():
    session = get_session()
    start_time = datetime.utcnow()
    logger = current_app.logger

    # Temporary diagnostics for input handling
    json_error = None
    try:
        request.get_json(force=False, silent=False)
    except Exception as exc:  # noqa: BLE001
        json_error = str(exc)
    file_meta = {
        key: getattr(f, "content_length", None) or getattr(f, "mimetype", None) or "unknown"
        for key, f in request.files.items()
    }
    _log_info(
        logger,
        "RMTree import request",
        extra={
            "method": request.method,
            "content_type": request.content_type,
            "content_length": request.content_length,
            "files": file_meta,
            "form_keys": list(request.form.keys()),
            "json_error": json_error,
        },
    )

    def _job(status: str, error: str | None = None) -> Dict[str, Any]:
        return {
            "status": status,
            "error": error,
            "started_at": start_time.isoformat() + "Z",
            "ended_at": datetime.utcnow().isoformat() + "Z",
        }

    def _error(code: str, message: str, status_code: int = 400, **details):
        payload = {"error": code, "message": message, "details": details, "job": _job("failed", code)}
        return jsonify(payload), status_code

    def _find_local_file(name: str) -> Path | None:
        # Normalize to basename only; drop any path components to avoid traversal
        base_name = Path(name).name
        if not base_name:
            return None
        media_dir, ingest_dir = _media_paths()
        for root in (media_dir, ingest_dir):
            candidate = root / base_name
            if candidate.exists():
                return candidate
        return None

    def _placeholder_sha(path_value: str) -> str:
        return hashlib.sha256(f"missing::{path_value}".encode("utf-8")).hexdigest()

    if not request.content_type or not request.content_type.startswith("multipart/form-data"):
        return _error(
            "invalid_content_type",
            "Expected multipart/form-data with field 'file'.",
            400,
            expected="multipart/form-data with field 'file'",
            got=request.content_type,
        )

    f = request.files.get("file")
    if not f:
        return _error(
            "missing_file",
            "File upload is required under form field 'file'.",
            400,
            expected="multipart/form-data with field 'file'",
            got_files=list(request.files.keys()),
        )

    max_len = current_app.config.get("MAX_CONTENT_LENGTH")
    if max_len and request.content_length and request.content_length > max_len:
        return _error(
            "file_too_large",
            f"Upload exceeds limit of {max_len} bytes.",
            413,
            limit=max_len,
            received=request.content_length,
        )

    warnings: List[str] = []
    orphan_relationships = 0
    orphan_media = 0

    with tempfile.TemporaryDirectory() as tmpdir:
        upload_path = os.path.join(tmpdir, secure_filename(f.filename or "upload"))
        size = 0
        first_chunk = b""
        with open(upload_path, "wb") as out:
            while True:
                chunk = f.stream.read(1024 * 1024)
                if not chunk:
                    break
                if not first_chunk:
                    first_chunk = chunk[:32]
                out.write(chunk)
                size += len(chunk)

        if size == 0:
            return _error("empty_file", "Uploaded file is empty.", 400)
        if max_len and size > max_len:
            return _error(
                "file_too_large",
                f"Upload exceeds limit of {max_len} bytes.",
                413,
                limit=max_len,
                received=size,
            )

        _log_info(
            logger,
            "RMTree upload received",
            extra={
                "rmtree_filename": f.filename,
                "size_bytes": size,
            },
        )

        signature = first_chunk[:16]
        is_zip = signature.startswith(b"PK\x03\x04")
        is_sqlite = signature.startswith(b"SQLite format 3\x00")
        sqlite_path = upload_path

        if is_zip:
            try:
                with zipfile.ZipFile(upload_path) as zf:
                    members = [m for m in zf.namelist() if m.lower().endswith(".rmtree")]
                    if not members:
                        return _error(
                            "invalid_archive",
                            "No .rmtree file found inside backup.",
                            400,
                            archive_members=zf.namelist(),
                        )
                    member = members[0]
                    extracted_path = os.path.join(tmpdir, os.path.basename(member))
                    with zf.open(member) as src, open(extracted_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    sqlite_path = extracted_path
                    with open(sqlite_path, "rb") as check_fp:
                        header = check_fp.read(16)
                    if not header.startswith(b"SQLite format 3\x00"):
                        return _error("invalid_signature", "Embedded file is not a SQLite RMTree database.", 422)
            except zipfile.BadZipFile:
                return _error("invalid_archive", "Backup file is not a valid ZIP archive.", 422)
        elif not is_sqlite:
            return _error(
                "invalid_signature",
                "Unrecognized file signature. Expected ZIP (.rmbackup) or SQLite (.rmtree).",
                422,
                got=signature.hex(),
            )

        try:
            sqlite_resolved = Path(sqlite_path).resolve()
            conn = sqlite3.connect(f"file:{sqlite_resolved.as_posix()}?mode=ro", uri=True)
        except sqlite3.DatabaseError as exc:  # noqa: BLE001
            return _error("open_failed", f"Could not open SQLite database: {exc}", 422)

        try:
            conn.row_factory = sqlite3.Row
            quick_check = conn.execute("PRAGMA quick_check").fetchone()
            quick_result = quick_check[0] if quick_check else "unknown"
            if quick_result != "ok":
                warnings.append(f"PRAGMA quick_check reported: {quick_result}")
            user_version_row = conn.execute("PRAGMA user_version").fetchone()
            user_version = user_version_row[0] if user_version_row else 0
            fingerprint, schema_rows = sqlite_schema_fingerprint(sqlite_path)
        except sqlite3.DatabaseError as exc:  # noqa: BLE001
            conn.close()
            return _error("integrity_check_failed", f"SQLite integrity check failed: {exc}", 422)

        tables = load_tables_from_sqlite(sqlite_path)
        conn.close()

        missing_media_ids = set()
        try:
            person_rows = collect_person_records(tables)
            relationship_rows = collect_relationship_records(tables)
            media_locations = collect_media_locations(tables)
            media_associations = collect_media_associations(tables)

            if not (person_rows or relationship_rows or media_locations or media_associations):
                return _error("no_data", "No usable RMTree data was found in the database.", 400)

            source_to_person_id: Dict[Any, int] = {}
            for record in person_rows:
                xref = record["xref"]
                stmt = select(Person).where(Person.xref == xref)
                person = session.execute(stmt).scalar_one_or_none()
                now = datetime.utcnow()

                if person:
                    person.given = record["given"]
                    person.surname = record["surname"]
                    person.sex = record["sex"]
                    person.birth_date = record["birth_date"]
                    person.birth_place = record["birth_place"]
                    person.death_date = record["death_date"]
                    person.death_place = record["death_place"]
                    person.updated_at = now
                else:
                    person = Person(
                        xref=xref,
                        given=record["given"],
                        surname=record["surname"],
                        sex=record["sex"],
                        birth_date=record["birth_date"],
                        birth_place=record["birth_place"],
                        death_date=record["death_date"],
                        death_place=record["death_place"],
                        updated_at=now,
                    )
                    session.add(person)

                session.flush()
                source_to_person_id[record["source_id"]] = person.id

                for note_text in record.get("notes", []):
                    note = Note(person_id=person.id, note_text=note_text)
                    session.add(note)

            media_id_to_asset: Dict[Any, MediaAsset] = {}
            source_to_family_id: Dict[Any, int] = {}
            media_descriptions: Dict[Any, str] = {}
            needs_media_flush = False

            for location in media_locations:
                media_id = location["media_id"]
                path = (location.get("path") or "").strip()
                if media_id is None or not path:
                    continue

                normalized_path = path.replace("\\", "/")
                base_name = Path(normalized_path).name
                name_for_asset = (location.get("original_name") or base_name or "unknown").strip() or "unknown"

                found_file = _find_local_file(base_name)
                if found_file:
                    asset, _ = _register_media_from_path(found_file, session, name_for_asset)
                else:
                    sha = _placeholder_sha(normalized_path)
                    asset = session.execute(select(MediaAsset).where(MediaAsset.sha256 == sha)).scalar_one_or_none()
                    if not asset:
                        asset = MediaAsset(
                            path=base_name,
                            original_filename=name_for_asset,
                            mime_type=None,
                            sha256=sha,
                            size_bytes=None,
                            source_path=normalized_path,
                            status="unassigned",
                        )
                        session.add(asset)
                        needs_media_flush = True
                    missing_media_ids.add(media_id)

                media_id_to_asset[media_id] = asset
                if location.get("description"):
                    media_descriptions[media_id] = location["description"]

            if needs_media_flush:
                session.flush()

            media_links_created = 0
            for association in media_associations:
                media_id = association.get("media_id")
                owner_type = (association.get("owner_type") or "").lower()
                owner_source_id = association.get("owner_id")
                if owner_source_id is None:
                    continue

                asset = media_id_to_asset.get(media_id)
                if not asset:
                    orphan_media += 1
                    continue

                person_id = None
                family_id = None
                if owner_type == "person":
                    person_id = source_to_person_id.get(owner_source_id)
                elif owner_type == "family":
                    family_id = source_to_family_id.get(owner_source_id)
                else:
                    # default to person when type missing but column name suggests person
                    person_id = source_to_person_id.get(owner_source_id)

                if not person_id and not family_id:
                    orphan_media += 1
                    continue

                existing_link = session.execute(
                    select(MediaLink).where(
                        MediaLink.asset_id == asset.id,
                        MediaLink.person_id == person_id,
                        MediaLink.family_id == family_id,
                    )
                ).scalar_one_or_none()
                if existing_link:
                    continue

                description = media_descriptions.get(media_id)
                media_link = MediaLink(
                    asset_id=asset.id,
                    person_id=person_id,
                    family_id=family_id,
                    description=description,
                )
                session.add(media_link)
                media_links_created += 1

            for asset in media_id_to_asset.values():
                _refresh_asset_status(session, asset.id)

            relationship_count = 0
            for relationship in relationship_rows:
                parent_source = relationship.get("parent_id")
                child_source = relationship.get("child_id")
                parent_id = source_to_person_id.get(parent_source)
                child_id = source_to_person_id.get(child_source)
                if parent_id is None or child_id is None:
                    orphan_relationships += 1
                    continue
                try:
                    session.execute(
                        relationships.insert().values(
                            parent_person_id=parent_id,
                            child_person_id=child_id,
                            rel_type=RELATIONSHIP_PARENT_TYPE,
                        )
                    )
                    relationship_count += 1
                except IntegrityError:
                    continue

            session.commit()

            summary = {
                "people": len(source_to_person_id),
                "media_assets": len(media_id_to_asset),
                "media_links": media_links_created,
                "relationships": relationship_count,
                "events": 0,
                "places": 0,
                "sources": 0,
                "missing_media": len(missing_media_ids),
            }
            warnings.append("Event/place/source import not yet implemented; counts set to 0.")
            schema_info = {
                "user_version": user_version,
                "fingerprint": fingerprint,
                "objects_seen": len(schema_rows),
            }
            _log_info(
                logger,
                "RMTree import completed",
                extra={
                    "import_people": summary["people"],
                    "import_media": summary["media_assets"],
                    "import_links": summary["media_links"],
                    "missing_media": summary["missing_media"],
                },
            )
            return jsonify(
                {
                    "imported": summary,
                    "warnings": warnings,
                    "orphaned": {
                        "relationships": orphan_relationships,
                        "media_links": orphan_media,
                    },
                    "schema": schema_info,
                    "job": _job("completed"),
                }
            )
        except Exception as exc:
            session.rollback()
            logger.exception(
                "RMTree import failed",
                extra=_sanitize_log_extra({"error": str(exc), "error_type": type(exc).__name__}),
            )
            return _error(
                "processing_error",
                "Failed to process RMTree import. Check server logs for details.",
                422,
            )

@api_bp.get("/tree/<int:person_id>")
def tree(person_id: int):
    session = get_session()
    person = session.get(Person, person_id)
    if not person:
        return jsonify({"error": "Not found"}), 404

    # Get parents
    parents_stmt = select(Person).join(
        relationships, relationships.c.parent_person_id == Person.id
    ).where(relationships.c.child_person_id == person_id).order_by(Person.surname, Person.given)
    parents = session.execute(parents_stmt).scalars().all()

    # Get children
    children_stmt = select(Person).join(
        relationships, relationships.c.child_person_id == Person.id
    ).where(relationships.c.parent_person_id == person_id).order_by(Person.surname, Person.given)
    children = session.execute(children_stmt).scalars().all()

    return jsonify({
        "root": _person_to_dict(person),
        "parents": [_person_to_dict(p) for p in parents],
        "children": [_person_to_dict(c) for c in children],
    })

@api_bp.post("/people/<int:person_id>/media")
def upload_media(person_id: int):
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "file is required"}), 400

    session = get_session()
    person = session.get(Person, person_id)
    if not person:
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

    # Check if media asset already exists
    stmt = select(MediaAsset).where(MediaAsset.sha256 == sha)
    media_asset = session.execute(stmt).scalar_one_or_none()
    
    if not media_asset:
        media_asset = MediaAsset(
            path=stored_name,
            original_filename=original_name,
            mime_type=mime,
            sha256=sha,
            size_bytes=size_bytes,
            status="assigned",
            source_path=None,
        )
        session.add(media_asset)
        session.flush()
    
    # Create media link
    media_link = MediaLink(
        asset_id=media_asset.id,
        person_id=person_id
    )
    session.add(media_link)
    session.flush()
    _refresh_asset_status(session, media_asset.id)
    session.commit()

    return jsonify({"stored": stored_name, "sha256": sha}), 201

@api_bp.get("/media/<path:file_name>")
def get_media(file_name: str):
    media_dir = current_app.config["MEDIA_DIR"]
    return send_from_directory(media_dir, file_name, as_attachment=False)

def _media_asset_dict(asset, include_id_key: str = "id", link_count: int | None = None, link_id: int | None = None):
    data = {
        include_id_key: asset.id,
        "path": asset.path,
        "sha256": asset.sha256,
        "original_filename": asset.original_filename,
        "mime_type": asset.mime_type,
        "size_bytes": asset.size_bytes,
        "thumbnail_path": asset.thumbnail_path,
        "thumb_width": asset.thumb_width,
        "thumb_height": asset.thumb_height,
        "status": asset.status,
        "source_path": asset.source_path,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }
    if link_count is not None:
        data["link_count"] = link_count
    if link_id is not None:
        data["link_id"] = link_id
    return data

# New Media v2 endpoints

@api_bp.post("/media/upload")
def upload_media_v2():
    """Upload media file and optionally link to person or family."""
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "file is required"}), 400

    person_id = request.form.get("person_id", type=int)
    family_id = request.form.get("family_id", type=int)

    if person_id and family_id:
        return jsonify({"error": "Cannot link to both person and family"}), 400

    session = get_session()

    if person_id:
        if not session.get(Person, person_id):
            return jsonify({"error": "Person not found"}), 404
    if family_id:
        if not session.get(Family, family_id):
            return jsonify({"error": "Family not found"}), 404

    original_name = f.filename or "upload"
    mime = f.mimetype or "application/octet-stream"
    content = f.read()
    sha = compute_sha256(content)
    size_bytes = len(content)

    media_dir = current_app.config["MEDIA_DIR"]
    os.makedirs(media_dir, exist_ok=True)

    asset = session.execute(select(MediaAsset).where(MediaAsset.sha256 == sha)).scalar_one_or_none()

    if asset:
        stored_name = asset.path
    else:
        stored_name = safe_filename(original_name, sha, mime)
        file_path = os.path.join(media_dir, stored_name)

        if not os.path.exists(file_path):
            with open(file_path, "wb") as out:
                out.write(content)

        thumbnail_path = None
        thumb_width = None
        thumb_height = None

        if is_image(mime):
            thumb_result = create_thumbnail(file_path, media_dir, sha)
            if thumb_result:
                thumbnail_full, thumb_width, thumb_height = thumb_result
                thumbnail_path = os.path.basename(thumbnail_full)

        asset = MediaAsset(
            path=stored_name,
            sha256=sha,
            original_filename=original_name,
            mime_type=mime,
            size_bytes=size_bytes,
            thumbnail_path=thumbnail_path,
            thumb_width=thumb_width,
            thumb_height=thumb_height,
            status="unassigned",
            source_path=None,
        )
        session.add(asset)
        session.flush()

    # Create link if requested
    link = None
    if person_id or family_id:
        existing_link = session.execute(
            select(MediaLink).where(
                MediaLink.asset_id == asset.id,
                MediaLink.person_id == person_id,
                MediaLink.family_id == family_id,
            )
        ).scalar_one_or_none()

        if not existing_link:
            link = MediaLink(asset_id=asset.id, person_id=person_id, family_id=family_id)
            session.add(link)
            session.flush()
        else:
            link = existing_link

    _refresh_asset_status(session, asset.id)
    session.commit()

    return jsonify({
        "asset_id": asset.id,
        "link_id": link.id if link else None,
        "sha256": asset.sha256,
        "path": asset.path,
        "thumbnail_path": asset.thumbnail_path,
        "original_filename": asset.original_filename,
    }), 201

@api_bp.get("/media/assets")
def list_media_assets():
    """List all media assets."""
    session = get_session()
    rows = session.execute(
        select(MediaAsset, func.count(MediaLink.id).label("link_count"))
        .outerjoin(MediaLink, MediaLink.asset_id == MediaAsset.id)
        .group_by(MediaAsset.id)
        .order_by(MediaAsset.created_at.desc())
        .limit(200)
    ).all()

    return jsonify([_media_asset_dict(asset, include_id_key="id", link_count=link_count) for asset, link_count in rows])


@api_bp.post("/media/assets/bulk")
def media_assets_bulk():
    data = request.get_json(force=True, silent=False)
    ids = data.get("ids") or []
    ids = [int(i) for i in ids if str(i).isdigit()]
    if not ids:
        return jsonify({"items": []})
    session = get_session()
    rows = session.execute(
        select(MediaAsset, func.count(MediaLink.id).label("link_count"))
        .outerjoin(MediaLink, MediaLink.asset_id == MediaAsset.id)
        .where(MediaAsset.id.in_(ids))
        .group_by(MediaAsset.id)
    ).all()
    return jsonify({"items": [_media_asset_dict(asset, include_id_key="id", link_count=link_count) for asset, link_count in rows]})

@api_bp.get("/media/unassigned")
def list_unassigned_media():
    """List media assets without any links."""
    session = get_session()
    _scan_ingest_directory(session)
    assets = session.execute(
        select(MediaAsset)
        .outerjoin(MediaLink, MediaLink.asset_id == MediaAsset.id)
        .where(
            and_(
                MediaLink.id.is_(None),
                MediaAsset.status == "unassigned",
            )
        )
        .order_by(MediaAsset.created_at.desc())
        .limit(200)
    ).scalars().all()
    
    return jsonify([_media_asset_dict(asset) for asset in assets])


@api_bp.post("/media/assign")
def assign_media():
    """Assign a media asset to a person or family."""
    data = request.get_json(force=True, silent=False)
    asset_id = data.get("media_id") or data.get("asset_id")
    person_id = data.get("person_id")
    family_id = data.get("family_id")

    if not asset_id:
        return jsonify({"error": "media_id is required"}), 400
    if not person_id and not family_id:
        return jsonify({"error": "Either person_id or family_id is required"}), 400
    if person_id and family_id:
        return jsonify({"error": "Cannot link to both person and family"}), 400

    session = get_session()
    asset = session.get(MediaAsset, asset_id)
    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    if person_id and not session.get(Person, person_id):
        return jsonify({"error": "Person not found"}), 404
    if family_id and not session.get(Family, family_id):
        return jsonify({"error": "Family not found"}), 404

    existing = session.execute(
        select(MediaLink).where(
            MediaLink.asset_id == asset_id,
            MediaLink.person_id == person_id,
            MediaLink.family_id == family_id,
        )
    ).scalar_one_or_none()
    if existing:
        _refresh_asset_status(session, asset_id)
        session.commit()
        return jsonify({"link_id": existing.id, "assigned": True}), 200

    link = MediaLink(asset_id=asset_id, person_id=person_id, family_id=family_id)
    session.add(link)
    session.flush()
    _refresh_asset_status(session, asset_id)
    session.commit()
    return jsonify({"link_id": link.id, "assigned": True}), 201

@api_bp.post("/media/link")
def link_media():
    """Link a media asset to a person or family."""
    data = request.get_json(force=True, silent=False)
    asset_id = data.get("asset_id")
    person_id = data.get("person_id")
    family_id = data.get("family_id")

    if not asset_id:
        return jsonify({"error": "asset_id is required"}), 400

    if not person_id and not family_id:
        return jsonify({"error": "Either person_id or family_id is required"}), 400

    if person_id and family_id:
        return jsonify({"error": "Cannot link to both person and family"}), 400

    session = get_session()
    asset = session.get(MediaAsset, asset_id)
    if not asset:
        return jsonify({"error": "Asset not found"}), 404

    if person_id and not session.get(Person, person_id):
        return jsonify({"error": "Person not found"}), 404
    if family_id and not session.get(Family, family_id):
        return jsonify({"error": "Family not found"}), 404

    existing = session.execute(
        select(MediaLink).where(
            MediaLink.asset_id == asset_id,
            MediaLink.person_id == person_id,
            MediaLink.family_id == family_id,
        )
    ).scalar_one_or_none()

    if existing:
        return jsonify({"error": "Link already exists", "link_id": existing.id}), 400

    link = MediaLink(asset_id=asset_id, person_id=person_id, family_id=family_id)
    session.add(link)
    session.flush()
    _refresh_asset_status(session, asset_id)
    session.commit()

    return jsonify({"link_id": link.id}), 201

@api_bp.delete("/media/link/<int:link_id>")
def unlink_media(link_id: int):
    """Remove a media link."""
    session = get_session()
    link = session.get(MediaLink, link_id)
    if not link:
        return jsonify({"error": "Link not found"}), 404

    asset_id = link.asset_id
    session.delete(link)
    session.flush()
    _refresh_asset_status(session, asset_id)
    session.commit()

    return jsonify({"deleted": True})

@api_bp.get("/media/thumbnail/<path:file_name>")
def get_thumbnail(file_name: str):
    """Serve a thumbnail image."""
    media_dir = current_app.config["MEDIA_DIR"]
    return send_from_directory(media_dir, file_name, as_attachment=False)

@api_bp.get("/analytics/orphaned-media")
def analytics_orphaned_media():
    """Count media assets without any links."""
    session = get_session()
    count = session.execute(
        select(func.count(MediaAsset.id))
        .outerjoin(MediaLink, MediaLink.asset_id == MediaAsset.id)
        .where(MediaLink.id.is_(None))
    ).scalar_one()
    
    return jsonify({"orphaned_count": count})

@api_bp.get("/analytics/people-without-media")
def analytics_people_without_media():
    """Count people with no media attached."""
    session = get_session()
    count = session.execute(
        select(func.count(Person.id))
        .outerjoin(MediaLink, MediaLink.person_id == Person.id)
        .where(MediaLink.id.is_(None))
    ).scalar_one()
    
    return jsonify({"people_without_media": count})


# -------------------------
# Analytics v1 (data patterns)
# -------------------------

_YEAR_RE = re.compile(r"(\d{4})")


def _extract_years(value: str | None) -> list[int]:
    """Extract all 4-digit years from a GEDCOM-ish freeform date string."""
    if not value:
        return []
    years = []
    for m in _YEAR_RE.finditer(value):
        try:
            years.append(int(m.group(1)))
        except Exception:
            continue
    return years


def _extract_year_primary(value: str | None) -> int | None:
    """Return the earliest year found in the string (BET/BEF/etc. -> earliest)."""
    years = _extract_years(value)
    return min(years) if years else None

def _person_summary(p: Person) -> dict:
    """Compact person shape for drilldowns."""
    birth_year = _extract_year_primary(p.birth_date)
    death_year = _extract_year_primary(p.death_date)
    return {
        "id": p.id,
        "xref": p.xref,
        "given": p.given,
        "surname": p.surname,
        "birth_date": p.birth_date,
        "death_date": p.death_date,
        "birth_year": birth_year,
        "death_year": death_year,
        "birth_place": p.birth_place,
        "death_place": p.death_place,
    }


def _norm_text(value: str | None) -> str:
    return (value or "").strip().lower()


def _place_key(value: str | None) -> str:
    """Normalize a place string for grouping (cheap + cheerful)."""
    if not value:
        return ""
    v = " ".join((value or "").replace(";", ",").split())
    return v.strip().lower()

def _people_for_drilldown(drill_type: str, filters: dict, session) -> list[Person]:
    drill_type = (drill_type or "").lower()
    filters = filters or {}

    if drill_type == "surname":
        surname = (filters.get("surname") or "").strip().lower()
        if not surname:
            return []
        stmt = select(Person).where(func.lower(Person.surname) == surname).order_by(Person.surname, Person.given)
        return session.execute(stmt).scalars().all()

    if drill_type == "birth_place":
        place = (filters.get("place") or "").strip().lower()
        if not place:
            return []
        stmt = select(Person).where(func.lower(func.trim(Person.birth_place)) == place).order_by(Person.surname, Person.given)
        return session.execute(stmt).scalars().all()

    if drill_type in {"birth_decade", "death_decade", "marriage_decade"}:
        decade = filters.get("decade")
        if decade is None:
            return []
        decade = int(decade)
        if drill_type == "marriage_decade":
            fams = session.execute(select(Family)).scalars().all()
            hits: list[int] = []
            for fam in fams:
                year = _extract_year_primary(fam.marriage_date)
                if year and (year // 10) * 10 == decade:
                    if fam.husband_person_id:
                        hits.append(fam.husband_person_id)
                    if fam.wife_person_id:
                        hits.append(fam.wife_person_id)
            if not hits:
                return []
            stmt = select(Person).where(Person.id.in_(hits)).order_by(Person.surname, Person.given)
            return session.execute(stmt).scalars().all()

        people = session.execute(select(Person)).scalars().all()
        out = []
        for p in people:
            date_val = p.birth_date if drill_type == "birth_decade" else p.death_date
            year = _extract_year_primary(date_val)
            if year and (year // 10) * 10 == decade:
                out.append(p)
        out.sort(key=lambda x: (x.surname or "", x.given or ""))
        return out

    if drill_type == "children_count":
        children = filters.get("children")
        if children is None:
            return []
        child_rows = session.execute(
            select(family_children.c.family_id, func.count(family_children.c.child_person_id))
            .group_by(family_children.c.family_id)
        ).all()
        fam_ids = [fid for (fid, cnt) in child_rows if int(cnt) == int(children)]
        if not fam_ids:
            return []
        fams = session.execute(select(Family).where(Family.id.in_(fam_ids))).scalars().all()
        person_ids: set[int] = set()
        for fam in fams:
            if fam.husband_person_id:
                person_ids.add(fam.husband_person_id)
            if fam.wife_person_id:
                person_ids.add(fam.wife_person_id)
        if not person_ids:
            return []
        stmt = select(Person).where(Person.id.in_(person_ids)).order_by(Person.surname, Person.given)
        return session.execute(stmt).scalars().all()

    if drill_type == "migration_pair":
        from_place = _place_key(filters.get("from"))
        to_place = _place_key(filters.get("to"))
        people = session.execute(select(Person)).scalars().all()
        out = []
        for p in people:
            if _place_key(p.birth_place) == from_place and _place_key(p.death_place) == to_place:
                out.append(p)
        out.sort(key=lambda x: (x.surname or "", x.given or ""))
        return out

    if drill_type == "duplicate_cluster":
        ids = filters.get("ids") or []
        if not ids:
            return []
        stmt = select(Person).where(Person.id.in_(ids)).order_by(Person.surname, Person.given)
        return session.execute(stmt).scalars().all()

    return []


@api_bp.get("/analytics/overview")
def analytics_overview():
    """High-level counts + coverage + a few top lists."""
    session = get_session()

    counts = {
        "people": session.execute(select(func.count(Person.id))).scalar_one(),
        "families": session.execute(select(func.count(Family.id))).scalar_one(),
        "notes": session.execute(select(func.count(Note.id))).scalar_one(),
        "media_assets": session.execute(select(func.count(MediaAsset.id))).scalar_one(),
        "media_links": session.execute(select(func.count(MediaLink.id))).scalar_one(),
    }

    # Coverage metrics (computed in Python because fields are free-form strings)
    people_rows = session.execute(
        select(
            Person.id,
            Person.given,
            Person.surname,
            Person.sex,
            Person.birth_date,
            Person.birth_place,
            Person.death_date,
            Person.death_place,
        )
    ).all()

    total_people = len(people_rows) or 1
    birth_year_known = 0
    death_year_known = 0
    birth_place_known = 0
    death_place_known = 0
    sex_known = 0

    for (_pid, _g, _s, sex, bdate, bplace, ddate, dplace) in people_rows:
        if _extract_year_primary(bdate) is not None:
            birth_year_known += 1
        if _extract_year_primary(ddate) is not None:
            death_year_known += 1
        if (bplace or "").strip():
            birth_place_known += 1
        if (dplace or "").strip():
            death_place_known += 1
        if (sex or "").strip():
            sex_known += 1

    coverage = {
        "birth_year_pct": round((birth_year_known / total_people) * 100, 1),
        "death_year_pct": round((death_year_known / total_people) * 100, 1),
        "birth_place_pct": round((birth_place_known / total_people) * 100, 1),
        "death_place_pct": round((death_place_known / total_people) * 100, 1),
        "sex_pct": round((sex_known / total_people) * 100, 1),
    }

    # Top surnames + places via SQL (fast)
    top_surnames_rows = session.execute(
        select(Person.surname, func.count(Person.id))
        .where(Person.surname.is_not(None))
        .where(Person.surname != "")
        .group_by(Person.surname)
        .order_by(func.count(Person.id).desc())
        .limit(15)
    ).all()
    top_surnames = [{"surname": s, "count": c} for (s, c) in top_surnames_rows]

    top_birth_places_rows = session.execute(
        select(Person.birth_place, func.count(Person.id))
        .where(Person.birth_place.is_not(None))
        .where(Person.birth_place != "")
        .group_by(Person.birth_place)
        .order_by(func.count(Person.id).desc())
        .limit(15)
    ).all()
    top_birth_places = [{"place": p, "count": c} for (p, c) in top_birth_places_rows]

    # Children-per-family distribution
    fam_child_rows = session.execute(
        select(family_children.c.family_id, func.count(family_children.c.child_person_id))
        .group_by(family_children.c.family_id)
    ).all()
    child_counts = [int(c) for (_fid, c) in fam_child_rows]
    dist = Counter(child_counts)
    children_per_family = {
        "avg": round((sum(child_counts) / (len(child_counts) or 1)), 2),
        "max": max(child_counts) if child_counts else 0,
        "distribution": [
            {"children": k, "families": v} for k, v in sorted(dist.items(), key=lambda kv: kv[0])
        ],
    }

    return jsonify({
        "counts": counts,
        "coverage": coverage,
        "top_surnames": top_surnames,
        "top_birth_places": top_birth_places,
        "children_per_family": children_per_family,
    })


@api_bp.get("/analytics/timeseries")
def analytics_timeseries():
    """Births/deaths/marriages grouped by decade (best-effort year extraction)."""
    session = get_session()

    births = Counter()
    deaths = Counter()
    marriages = Counter()

    for (bdate,) in session.execute(select(Person.birth_date)).all():
        y = _extract_year_primary(bdate)
        if y:
            births[(y // 10) * 10] += 1

    for (ddate,) in session.execute(select(Person.death_date)).all():
        y = _extract_year_primary(ddate)
        if y:
            deaths[(y // 10) * 10] += 1

    for (mdate,) in session.execute(select(Family.marriage_date)).all():
        y = _extract_year_primary(mdate)
        if y:
            marriages[(y // 10) * 10] += 1

    def _to_series(counter: Counter):
        return [
            {"decade": int(dec), "count": int(counter[dec])}
            for dec in sorted(counter.keys())
        ]

    return jsonify({
        "births_by_decade": _to_series(births),
        "deaths_by_decade": _to_series(deaths),
        "marriages_by_decade": _to_series(marriages),
    })


@api_bp.get("/analytics/duplicates")
def analytics_duplicates():
    """Potential duplicate people: same (given,surname,birth_year) with >1 record."""
    limit = min(int(request.args.get("limit", 50)), 200)
    session = get_session()
    rows = session.execute(select(Person.id, Person.given, Person.surname, Person.birth_date)).all()

    buckets: dict[tuple[str, str, int], list[int]] = {}
    for pid, given, surname, bdate in rows:
        g = _norm_text(given)
        s = _norm_text(surname)
        if not g or not s:
            continue
        y = _extract_year_primary(bdate)
        if not y:
            continue
        key = (g, s, y)
        buckets.setdefault(key, []).append(int(pid))

    out = []
    for (g, s, y), ids in buckets.items():
        if len(ids) > 1:
            out.append({
                "given": g,
                "surname": s,
                "birth_year": y,
                "count": len(ids),
                "ids": ids[:25],
            })

    out.sort(key=lambda x: (-x["count"], x["surname"], x["given"], x["birth_year"]))
    return jsonify(out[:limit])


@api_bp.get("/analytics/migration-pairs")
def analytics_migration_pairs():
    """Top birth_place -> death_place pairs (best-effort normalization)."""
    limit = min(int(request.args.get("limit", 20)), 200)
    session = get_session()
    rows = session.execute(select(Person.birth_place, Person.death_place)).all()

    pairs = Counter()
    for b, d in rows:
        bk = _place_key(b)
        dk = _place_key(d)
        if not bk or not dk or bk == dk:
            continue
        pairs[(bk, dk)] += 1

    out = [
        {"from": k[0], "to": k[1], "count": int(v)}
        for k, v in pairs.most_common(limit)
    ]
    return jsonify(out)

@api_bp.post("/analytics/drilldown")
def analytics_drilldown():
    """Generic drilldown endpoint for analytics charts."""
    data = request.get_json(force=True, silent=False) or {}
    drill_type = data.get("type")
    filters = data.get("filters") or {}
    try:
        page = max(int(data.get("page", 1) or 1), 1)
        page_size = min(max(int(data.get("pageSize", 20) or 20), 1), 200)
    except Exception:
        return jsonify({"error": "Invalid pagination"}), 400

    session = get_session()
    people = _people_for_drilldown(drill_type, filters, session)
    total = len(people)
    start = (page - 1) * page_size
    end = start + page_size
    items = [_person_summary(p) for p in people[start:end]]

    return jsonify({"items": items, "total": total, "page": page, "pageSize": page_size})

@api_bp.get("/people/<int:person_id>/media/v2")
def get_person_media_v2(person_id: int):
    """Get media assets linked to a person with full details."""
    session = get_session()
    
    person = session.get(Person, person_id)
    if not person:
        return jsonify({"error": "Person not found"}), 404

    rows = session.execute(
        select(MediaLink, MediaAsset)
        .join(MediaAsset, MediaAsset.id == MediaLink.asset_id)
        .where(MediaLink.person_id == person_id)
        .order_by(MediaAsset.created_at.desc())
    ).all()

    out = []
    for link, asset in rows:
        data = _media_asset_dict(asset, include_id_key="asset_id", link_id=link.id)
        out.append(data)
    return jsonify(out)


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
    
    session = get_session()
    root_person = session.get(Person, root_id)
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
        parents = session.execute(
            select(relationships.c.parent_person_id).where(
                relationships.c.child_person_id == person_id
            )
        ).scalars().all()
        for pid in parents:
            person_ids.add(pid)
            to_explore.append((pid, current_depth + 1))
        
        # Get children
        children = session.execute(
            select(relationships.c.child_person_id).where(
                relationships.c.parent_person_id == person_id
            )
        ).scalars().all()
        for cid in children:
            person_ids.add(cid)
            to_explore.append((cid, current_depth + 1))
    
    # Fetch all persons in the graph
    person_nodes = []
    persons = session.execute(
        select(Person).where(Person.id.in_(person_ids))
    ).scalars().all()
    for p in persons:
        has_birth = bool((p.birth_date or "").strip() or (p.birth_place or "").strip())
        has_death = bool((p.death_date or "").strip() or (p.death_place or "").strip())
        has_name = bool((p.given or "").strip() or (p.surname or "").strip())
        quality = "high" if (has_name and has_birth) else ("medium" if has_name else "low")
        
        person_nodes.append({
            "id": f"person_{p.id}",
            "type": "person",
            "data": {
                "id": p.id,
                "xref": p.xref,
                "given": p.given,
                "surname": p.surname,
                "sex": p.sex,
                "birth_date": p.birth_date,
                "birth_place": p.birth_place,
                "death_date": p.death_date,
                "death_place": p.death_place,
                "quality": quality,
            }
        })
    
    # Fetch all families involving these persons
    family_nodes = []
    family_ids_seen = set()
    
    if person_ids:
        families = session.execute(
            select(Family).where(
                or_(
                    Family.husband_person_id.in_(person_ids),
                    Family.wife_person_id.in_(person_ids)
                )
            )
        ).scalars().all()
    else:
        families = []

    family_ids = [f.id for f in families]
    child_map = {}
    if family_ids:
        child_rows = session.execute(
            select(family_children.c.family_id, family_children.c.child_person_id).where(
                family_children.c.family_id.in_(family_ids)
            )
        ).all()
        for fid, cid in child_rows:
            child_map.setdefault(fid, []).append(cid)
    
    for f in families:
        fid = f.id
        if fid in family_ids_seen:
            continue
        family_ids_seen.add(fid)
        
        child_ids = child_map.get(fid, [])
        
        family_nodes.append({
            "id": f"family_{fid}",
            "type": "family",
            "data": {
                "id": fid,
                "xref": f.xref,
                "husband_id": f.husband_person_id,
                "wife_id": f.wife_person_id,
                "marriage_date": f.marriage_date,
                "marriage_place": f.marriage_place,
                "children": child_ids,
            }
        })
    
    # Build edges
    edges = []
    
    # Spouse edges: person -> family
    for f in families:
        fid = f.id
        if f.husband_person_id and f.husband_person_id in person_ids:
            edges.append({
                "id": f"spouse_h_{fid}",
                "source": f"person_{f.husband_person_id}",
                "target": f"family_{fid}",
                "type": "spouse"
            })
        if f.wife_person_id and f.wife_person_id in person_ids:
            edges.append({
                "id": f"spouse_w_{fid}",
                "source": f"person_{f.wife_person_id}",
                "target": f"family_{fid}",
                "type": "spouse"
            })
    
    # Child edges: family -> person
    for f in families:
        fid = f.id
        for cid in child_map.get(fid, []):
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


# -------------------------
# Data Quality APIs
# -------------------------

def _issue_to_dict(issue: DataQualityIssue) -> dict:
    try:
        explanation = json.loads(issue.explanation_json or "{}")
    except Exception:
        explanation = {}
    try:
        entity_ids = json.loads(issue.entity_ids)
    except Exception:
        entity_ids = []
    return {
        "id": issue.id,
        "issue_type": issue.issue_type,
        "severity": issue.severity,
        "entity_type": issue.entity_type,
        "entity_ids": entity_ids,
        "status": issue.status,
        "confidence": issue.confidence,
        "impact_score": issue.impact_score,
        "explanation": explanation,
        "detected_at": issue.detected_at.isoformat(),
        "resolved_at": issue.resolved_at.isoformat() if issue.resolved_at else None,
    }


@api_bp.post("/dq/scan")
def dq_scan():
    incremental = bool(request.args.get("incremental"))
    session = get_session()
    results = run_detection(session, incremental=incremental)
    session.commit()
    return jsonify({"ran": results})


@api_bp.get("/dq/summary")
def dq_summary():
    session = get_session()
    summary = build_summary(session)
    return jsonify(summary)


@api_bp.get("/dq/issues")
def dq_issues():
    issue_type = request.args.get("type")
    status = request.args.get("status")
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(int(request.args.get("perPage", 50)), 200)

    session = get_session()
    stmt = select(DataQualityIssue).order_by(DataQualityIssue.detected_at.desc())
    if issue_type:
        stmt = stmt.where(DataQualityIssue.issue_type == issue_type)
    if status:
        stmt = stmt.where(DataQualityIssue.status == status)

    rows = session.execute(stmt.offset((page - 1) * per_page).limit(per_page)).scalars().all()
    total_stmt = select(func.count(DataQualityIssue.id))
    if issue_type:
        total_stmt = total_stmt.where(DataQualityIssue.issue_type == issue_type)
    if status:
        total_stmt = total_stmt.where(DataQualityIssue.status == status)
    total = session.execute(total_stmt).scalar_one()
    return jsonify({
        "items": [_issue_to_dict(r) for r in rows],
        "page": page,
        "perPage": per_page,
        "total": total,
    })


@api_bp.get("/dq/actions/log")
def dq_actions_log():
    page = max(int(request.args.get("page", 1)), 1)
    per_page = min(int(request.args.get("perPage", 50)), 200)
    session = get_session()
    stmt = (
        select(DataQualityActionLog)
        .order_by(DataQualityActionLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    rows = session.execute(stmt).scalars().all()
    items = []
    for r in rows:
        items.append({
            "id": r.id,
            "action_type": r.action_type,
            "payload": json.loads(r.payload_json or "{}"),
            "undo": bool(r.undo_payload_json),
            "created_at": r.created_at.isoformat(),
            "applied_by": r.applied_by,
        })
    total = session.execute(select(func.count(DataQualityActionLog.id))).scalar_one()
    return jsonify({"items": items, "page": page, "perPage": per_page, "total": total})


@api_bp.post("/dq/actions/mergePeople")
def dq_merge_people():
    data = request.get_json(force=True, silent=False)
    from_id = data.get("fromId")
    into_id = data.get("intoId")
    user = data.get("user")
    fill_missing = bool(data.get("fillMissing"))
    if not from_id or not into_id:
        return jsonify({"error": "fromId and intoId are required"}), 400
    if from_id == into_id:
        return jsonify({"error": "Cannot merge the same person"}), 400

    session = get_session()
    primary = session.get(Person, into_id)
    secondary = session.get(Person, from_id)
    if not primary or not secondary:
        return jsonify({"error": "Person not found"}), 404

    # Collect undo payload
    relationships_rows = session.execute(
        select(relationships.c.parent_person_id, relationships.c.child_person_id, relationships.c.rel_type).where(
            or_(
                relationships.c.parent_person_id == from_id,
                relationships.c.child_person_id == from_id,
            )
        )
    ).all()
    family_rows = session.execute(
        select(Family.id, Family.husband_person_id, Family.wife_person_id).where(
            or_(Family.husband_person_id == from_id, Family.wife_person_id == from_id)
        )
    ).all()
    family_child_rows = session.execute(
        select(family_children.c.family_id, family_children.c.child_person_id).where(
            family_children.c.child_person_id == from_id
        )
    ).all()
    media_rows = session.execute(
        select(MediaLink.id, MediaLink.asset_id, MediaLink.person_id, MediaLink.family_id).where(
            MediaLink.person_id == from_id
        )
    ).all()
    event_rows = session.execute(
        select(Event.id, Event.person_id).where(Event.person_id == from_id)
    ).all()

    undo_payload = {
        "from_person": _person_to_dict(secondary),
        "relationships": [list(r) for r in relationships_rows],
        "families": [{"id": fid, "husband_person_id": h, "wife_person_id": w} for fid, h, w in family_rows],
        "family_children": [{"family_id": fid, "child_person_id": cid} for fid, cid in family_child_rows],
        "media_links": [{"id": rid, "asset_id": aid, "person_id": pid, "family_id": fid} for rid, aid, pid, fid in media_rows],
        "events": [{"id": eid, "person_id": pid} for eid, pid in event_rows],
    }

    try:
        if fill_missing:
            fields = ["given", "surname", "sex", "birth_date", "birth_place", "death_date", "death_place"]
            primary_prev = {f: getattr(primary, f) for f in fields}
            updated = False
            for f in fields:
                if not getattr(primary, f) and getattr(secondary, f):
                    setattr(primary, f, getattr(secondary, f))
                    updated = True
            if updated:
                primary.updated_at = datetime.utcnow()
            undo_payload["primary_prev"] = primary_prev

        session.execute(update(Event).where(Event.person_id == from_id).values(person_id=into_id))
        media_links = session.execute(
            select(MediaLink).where(MediaLink.person_id == from_id)
        ).scalars().all()
        for link in media_links:
            exists = session.execute(
                select(MediaLink.id).where(
                    MediaLink.asset_id == link.asset_id,
                    MediaLink.person_id == into_id,
                    MediaLink.family_id == link.family_id,
                )
            ).scalar_one_or_none()
            if exists:
                session.delete(link)
            else:
                link.person_id = into_id

        session.execute(
            update(Family)
            .where(Family.husband_person_id == from_id)
            .values(husband_person_id=into_id)
        )
        session.execute(
            update(Family)
            .where(Family.wife_person_id == from_id)
            .values(wife_person_id=into_id)
        )

        rel_rows = session.execute(
            select(
                relationships.c.parent_person_id,
                relationships.c.child_person_id,
                relationships.c.rel_type,
            ).where(
                or_(
                    relationships.c.parent_person_id == from_id,
                    relationships.c.child_person_id == from_id,
                )
            )
        ).all()
        session.execute(
            relationships.delete().where(
                or_(
                    relationships.c.parent_person_id == from_id,
                    relationships.c.child_person_id == from_id,
                )
            )
        )
        for parent_id, child_id, rel_type in rel_rows:
            new_parent = into_id if parent_id == from_id else parent_id
            new_child = into_id if child_id == from_id else child_id
            exists = session.execute(
                select(relationships.c.parent_person_id).where(
                    relationships.c.parent_person_id == new_parent,
                    relationships.c.child_person_id == new_child,
                    relationships.c.rel_type == rel_type,
                )
            ).first()
            if not exists:
                session.execute(
                    relationships.insert().values(
                        parent_person_id=new_parent,
                        child_person_id=new_child,
                        rel_type=rel_type,
                    )
                )

        child_rows = session.execute(
            select(family_children.c.family_id, family_children.c.child_person_id).where(
                family_children.c.child_person_id == from_id
            )
        ).all()
        for fid, cid in child_rows:
            exists = session.execute(
                select(family_children.c.family_id).where(
                    family_children.c.family_id == fid,
                    family_children.c.child_person_id == into_id,
                )
            ).first()
            if exists:
                session.execute(
                    family_children.delete().where(
                        family_children.c.family_id == fid,
                        family_children.c.child_person_id == from_id,
                    )
                )
            else:
                session.execute(
                    family_children.update()
                    .where(
                        family_children.c.family_id == fid,
                        family_children.c.child_person_id == from_id,
                    )
                    .values(child_person_id=into_id)
                )
        session.delete(secondary)

        action_entry = log_action(
            session,
            "merge_people",
            {"fromId": from_id, "intoId": into_id},
            undo_payload,
            user,
        )

        dup_issues = session.execute(
            select(DataQualityIssue).where(
                DataQualityIssue.issue_type == "duplicate_person",
                DataQualityIssue.status == "open",
            )
        ).scalars().all()
        for issue in dup_issues:
            try:
                ids = json.loads(issue.entity_ids)
            except Exception:
                ids = []
            if from_id in ids or into_id in ids:
                issue.status = "resolved"
                issue.resolved_at = datetime.utcnow()
        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"mergedInto": into_id, "action_id": action_entry.id, "revertToken": action_entry.id})


@api_bp.post("/dq/actions/mergeFamilies")
def dq_merge_families():
    data = request.get_json(force=True, silent=False)
    from_id = data.get("fromId")
    into_id = data.get("intoId")
    user = data.get("user")
    fill_missing = bool(data.get("fillMissing"))
    if not from_id or not into_id:
        return jsonify({"error": "fromId and intoId are required"}), 400
    if from_id == into_id:
        return jsonify({"error": "Cannot merge the same family"}), 400

    session = get_session()
    primary = session.get(Family, into_id)
    secondary = session.get(Family, from_id)
    if not primary or not secondary:
        return jsonify({"error": "Family not found"}), 404

    child_rows = session.execute(
        select(family_children.c.family_id, family_children.c.child_person_id).where(
            family_children.c.family_id == from_id
        )
    ).all()
    event_rows = session.execute(
        select(Event.id, Event.family_id).where(Event.family_id == from_id)
    ).all()
    note_rows = session.execute(
        select(Note.id, Note.family_id).where(Note.family_id == from_id)
    ).all()
    media_rows = session.execute(
        select(MediaLink.id, MediaLink.asset_id, MediaLink.person_id, MediaLink.family_id).where(
            MediaLink.family_id == from_id
        )
    ).all()

    undo_children = []
    undo_media = []
    inserted_relationships = []
    undo_payload = {
        "from_family": _family_to_dict(secondary),
        "children": undo_children,
        "events": [{"id": eid, "family_id": fid} for eid, fid in event_rows],
        "notes": [{"id": nid, "family_id": fid} for nid, fid in note_rows],
        "media_links": [{"id": rid, "asset_id": aid, "person_id": pid, "family_id": fid} for rid, aid, pid, fid in media_rows],
        "inserted_relationships": inserted_relationships,
    }

    try:
        if fill_missing:
            fields = ["husband_person_id", "wife_person_id", "marriage_date", "marriage_place"]
            primary_prev = {f: getattr(primary, f) for f in fields}
            updated = False
            for f in fields:
                if not getattr(primary, f) and getattr(secondary, f):
                    setattr(primary, f, getattr(secondary, f))
                    updated = True
            if updated:
                primary.updated_at = datetime.utcnow()
            undo_payload["primary_prev"] = primary_prev

        session.execute(update(Event).where(Event.family_id == from_id).values(family_id=into_id))
        session.execute(update(Note).where(Note.family_id == from_id).values(family_id=into_id))

        media_links = session.execute(
            select(MediaLink).where(MediaLink.family_id == from_id)
        ).scalars().all()
        for link in media_links:
            exists = session.execute(
                select(MediaLink.id).where(
                    MediaLink.asset_id == link.asset_id,
                    MediaLink.family_id == into_id,
                    MediaLink.person_id == link.person_id,
                )
            ).scalar_one_or_none()
            if exists:
                session.delete(link)
                undo_media.append({"id": link.id, "deleted": True})
            else:
                undo_media.append({"id": link.id, "family_id": from_id})
                link.family_id = into_id

        for fid, cid in child_rows:
            exists = session.execute(
                select(family_children.c.family_id).where(
                    family_children.c.family_id == into_id,
                    family_children.c.child_person_id == cid,
                )
            ).first()
            undo_children.append({"family_id": fid, "child_person_id": cid, "into_existed": bool(exists)})
            if exists:
                session.execute(
                    family_children.delete().where(
                        family_children.c.family_id == from_id,
                        family_children.c.child_person_id == cid,
                    )
                )
            else:
                session.execute(
                    family_children.update()
                    .where(
                        family_children.c.family_id == from_id,
                        family_children.c.child_person_id == cid,
                    )
                    .values(family_id=into_id)
                )

            if primary.husband_person_id:
                rel_exists = session.execute(
                    select(relationships.c.parent_person_id).where(
                        relationships.c.parent_person_id == primary.husband_person_id,
                        relationships.c.child_person_id == cid,
                        relationships.c.rel_type == RELATIONSHIP_PARENT_TYPE,
                    )
                ).first()
                if not rel_exists:
                    session.execute(
                        relationships.insert().values(
                            parent_person_id=primary.husband_person_id,
                            child_person_id=cid,
                            rel_type=RELATIONSHIP_PARENT_TYPE,
                        )
                    )
                    inserted_relationships.append([primary.husband_person_id, cid, RELATIONSHIP_PARENT_TYPE])

            if primary.wife_person_id:
                rel_exists = session.execute(
                    select(relationships.c.parent_person_id).where(
                        relationships.c.parent_person_id == primary.wife_person_id,
                        relationships.c.child_person_id == cid,
                        relationships.c.rel_type == RELATIONSHIP_PARENT_TYPE,
                    )
                ).first()
                if not rel_exists:
                    session.execute(
                        relationships.insert().values(
                            parent_person_id=primary.wife_person_id,
                            child_person_id=cid,
                            rel_type=RELATIONSHIP_PARENT_TYPE,
                        )
                    )
                    inserted_relationships.append([primary.wife_person_id, cid, RELATIONSHIP_PARENT_TYPE])

        session.delete(secondary)

        action_entry = log_action(
            session,
            "merge_families",
            {"fromId": from_id, "intoId": into_id},
            undo_payload,
            user,
        )

        family_issues = session.execute(
            select(DataQualityIssue).where(
                DataQualityIssue.issue_type.in_(["duplicate_family", "duplicate_family_spouse_swap"]),
                DataQualityIssue.status == "open",
            )
        ).scalars().all()
        for issue in family_issues:
            try:
                ids = json.loads(issue.entity_ids)
            except Exception:
                ids = []
            if from_id in ids or into_id in ids:
                issue.status = "resolved"
                issue.resolved_at = datetime.utcnow()
        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"mergedInto": into_id, "action_id": action_entry.id, "revertToken": action_entry.id})


@api_bp.post("/dq/actions/dedupeMediaLinks")
def dq_dedupe_media_links():
    data = request.get_json(force=True, silent=False)
    link_ids = [int(i) for i in data.get("link_ids") or [] if str(i).isdigit()]
    keep_id = data.get("keep_id")
    user = data.get("user")
    if not link_ids:
        return jsonify({"error": "link_ids required"}), 400

    if keep_id is not None and int(keep_id) in link_ids:
        keep_id = int(keep_id)
    else:
        keep_id = min(link_ids)

    session = get_session()
    links = session.execute(select(MediaLink).where(MediaLink.id.in_(link_ids))).scalars().all()
    if not links:
        return jsonify({"error": "links not found"}), 404

    undo_payload = {
        "deleted_links": [
            {"id": link.id, "asset_id": link.asset_id, "person_id": link.person_id, "family_id": link.family_id}
            for link in links if link.id != keep_id
        ]
    }

    try:
        for link in links:
            if link.id == keep_id:
                continue
            session.delete(link)

        action_entry = log_action(
            session,
            "dedupe_media_links",
            {"link_ids": link_ids, "keep_id": keep_id},
            undo_payload,
            user,
        )

        media_issues = session.execute(
            select(DataQualityIssue).where(
                DataQualityIssue.issue_type == "duplicate_media_link",
                DataQualityIssue.status == "open",
            )
        ).scalars().all()
        for issue in media_issues:
            try:
                ids = json.loads(issue.entity_ids)
            except Exception:
                ids = []
            if any(i in ids for i in link_ids):
                issue.status = "resolved"
                issue.resolved_at = datetime.utcnow()
        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"deduped": len(link_ids) - 1, "action_id": action_entry.id, "revertToken": action_entry.id})


@api_bp.post("/dq/actions/mergeMediaAssets")
def dq_merge_media_assets():
    data = request.get_json(force=True, silent=False)
    from_id = data.get("fromId")
    into_id = data.get("intoId")
    user = data.get("user")
    if not from_id or not into_id:
        return jsonify({"error": "fromId and intoId are required"}), 400
    if from_id == into_id:
        return jsonify({"error": "Cannot merge the same asset"}), 400

    session = get_session()
    primary = session.get(MediaAsset, into_id)
    secondary = session.get(MediaAsset, from_id)
    if not primary or not secondary:
        return jsonify({"error": "Media asset not found"}), 404

    link_rows = session.execute(
        select(MediaLink.id, MediaLink.asset_id).where(MediaLink.asset_id == from_id)
    ).all()
    undo_payload = {
        "from_asset": _media_asset_dict(secondary, include_id_key="id"),
        "links": [{"id": lid, "asset_id": aid} for lid, aid in link_rows],
    }

    try:
        session.execute(update(MediaLink).where(MediaLink.asset_id == from_id).values(asset_id=into_id))
        session.delete(secondary)

        action_entry = log_action(
            session,
            "merge_media_assets",
            {"fromId": from_id, "intoId": into_id},
            undo_payload,
            user,
        )

        asset_issues = session.execute(
            select(DataQualityIssue).where(
                DataQualityIssue.issue_type == "duplicate_media_asset",
                DataQualityIssue.status == "open",
            )
        ).scalars().all()
        for issue in asset_issues:
            try:
                ids = json.loads(issue.entity_ids)
            except Exception:
                ids = []
            if from_id in ids or into_id in ids:
                issue.status = "resolved"
                issue.resolved_at = datetime.utcnow()

        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"mergedInto": into_id, "action_id": action_entry.id, "revertToken": action_entry.id})



def _apply_place_normalization(
    session,
    canonical_value: str,
    variants: list[str],
    applied_by: str | None = None,
    resolve_issues: bool = True,
) -> tuple[int, int]:
    """
    Apply a place normalization (canonical + variants) and log the action.
    Returns: (canonical_place_id, action_id)
    """
    canonical_value = (canonical_value or "").strip()
    variants = [v.strip() for v in (variants or []) if v and v.strip()]
    if not canonical_value or not variants:
        raise ValueError("canonical and variants are required")

    place = session.execute(select(Place).where(Place.name_canonical == canonical_value)).scalar_one_or_none()
    if not place:
        place = Place(name_canonical=canonical_value)
        session.add(place)
        session.flush()

    undo_events: list[dict] = []
    undo_persons: list[dict] = []
    undo_families: list[dict] = []

    for variant in variants:
        existing_variant = session.execute(
            select(PlaceVariant).where(PlaceVariant.name_variant == variant)
        ).scalar_one_or_none()
        if not existing_variant:
            session.add(PlaceVariant(place_id=place.id, name_variant=variant))

        affected_events = session.execute(
            select(Event.id, Event.place_id, Event.place_raw).where(Event.place_raw == variant)
        ).all()
        session.execute(update(Event).where(Event.place_raw == variant).values(place_id=place.id))
        for eid, prev_pid, prev_raw in affected_events:
            undo_events.append({"id": eid, "place_id": prev_pid, "place_raw": prev_raw})

        people_rows = session.execute(
            select(Person.id, Person.birth_place, Person.death_place).where(
                or_(Person.birth_place == variant, Person.death_place == variant)
            )
        ).all()
        for pid, bplace, dplace in people_rows:
            undo_persons.append({"id": pid, "birth_place": bplace, "death_place": dplace})
            if bplace == variant:
                session.execute(update(Person).where(Person.id == pid).values(birth_place=canonical_value))
            if dplace == variant:
                session.execute(update(Person).where(Person.id == pid).values(death_place=canonical_value))

        family_rows = session.execute(
            select(Family.id, Family.marriage_place).where(Family.marriage_place == variant)
        ).all()
        for fid, mplace in family_rows:
            undo_families.append({"id": fid, "marriage_place": mplace})
            session.execute(update(Family).where(Family.id == fid).values(marriage_place=canonical_value))

    action_entry = log_action(
        session,
        "normalize_places",
        {"canonical": canonical_value, "variants": variants},
        {"events": undo_events, "persons": undo_persons, "families": undo_families},
        applied_by,
    )

    if resolve_issues:
        like_conds = []
        # Target only issues that mention any of these strings (best-effort, avoids resolving unrelated open issues)
        for s in [canonical_value, *variants]:
            if s:
                like_conds.append(DataQualityIssue.explanation_json.like(f"%{s}%"))
        if like_conds:
            session.execute(
                update(DataQualityIssue)
                .where(
                    DataQualityIssue.issue_type.in_(["place_cluster", "place_similarity"]),
                    DataQualityIssue.status == "open",
                    or_(*like_conds),
                )
                .values(status="resolved", resolved_at=datetime.utcnow())
            )

    session.commit()
    return int(place.id), int(action_entry.id)

@api_bp.post("/dq/actions/normalizePlaces")
def dq_normalize_places():

    data = request.get_json(force=True, silent=False)
    canonical_value = (data.get("canonical") or "").strip()
    variants = [v.strip() for v in data.get("variants") or [] if v]
    applied_by = data.get("user")
    try:
        session = get_session()
        place_id, action_id = _apply_place_normalization(
            session=session,
            canonical_value=canonical_value,
            variants=variants,
            applied_by=applied_by,
            resolve_issues=True,
        )
    except ValueError as ve:
        return jsonify({"error": str(ve)}), 400
    except Exception:
        # Ensure the session is clean for the request lifecycle
        try:
            session.rollback()
        except Exception:
            pass
        raise

    return jsonify({"canonical_place_id": place_id, "action_id": action_id, "revertToken": action_id})



@api_bp.post("/places/enrich")
def enrich_place():
    """Attach authority metadata to a canonical Place without changing name_canonical.

    Payload:
      - place_id (int) OR canonical (str)
      - authority_source (str) [required]
      - authority_id (str) [required]
      - latitude (float) [optional]
      - longitude (float) [optional]
      - force (bool) overwrite existing authority/coords [optional, default false]
    """
    data = request.get_json(force=True, silent=False) or {}
    place_id = data.get("place_id")
    canonical = (data.get("canonical") or "").strip()
    authority_source = (data.get("authority_source") or "").strip()
    authority_id = (data.get("authority_id") or "").strip()
    force = bool(data.get("force") or False)

    if not authority_source or not authority_id:
        return jsonify({"error": "authority_source and authority_id are required"}), 400
    if not place_id and not canonical:
        return jsonify({"error": "place_id or canonical is required"}), 400

    session = get_session()
    if place_id:
        place = session.get(Place, place_id)
    else:
        place = session.execute(select(Place).where(Place.name_canonical == canonical)).scalar_one_or_none()

    if not place:
        return jsonify({"error": "Place not found"}), 404

    # Only set if missing unless force=true
    if force or not getattr(place, "authority_source", None):
        place.authority_source = authority_source
    if force or not getattr(place, "authority_id", None):
        place.authority_id = authority_id

    if (force or place.latitude is None) and data.get("latitude") is not None:
        try:
            place.latitude = float(data.get("latitude"))
        except Exception:
            return jsonify({"error": "latitude must be numeric"}), 400
    if (force or place.longitude is None) and data.get("longitude") is not None:
        try:
            place.longitude = float(data.get("longitude"))
        except Exception:
            return jsonify({"error": "longitude must be numeric"}), 400

    session.commit()

    return jsonify({
        "id": place.id,
        "canonical": place.name_canonical,
        "authority_source": getattr(place, "authority_source", None),
        "authority_id": getattr(place, "authority_id", None),
        "latitude": place.latitude,
        "longitude": place.longitude,
    })

def _update_event_date_canonical(event: Event, normalized: str | None) -> None:
    if not normalized or len(normalized) < 4:
        event.date_canonical = None
        return
    try:
        if len(normalized) == 10:
            event.date_canonical = datetime.strptime(normalized, "%Y-%m-%d")
        elif len(normalized) == 7:
            event.date_canonical = datetime.strptime(normalized + "-01", "%Y-%m-%d")
        elif len(normalized) == 4:
            event.date_canonical = datetime.strptime(normalized + "-01-01", "%Y-%m-%d")
    except Exception:
        event.date_canonical = None


@api_bp.post("/dq/actions/normalizeDates")
def dq_normalize_dates():
    data = request.get_json(force=True, silent=False)
    items = data.get("items") or []
    applied_by = data.get("user")
    if not items:
        return jsonify({"error": "items required"}), 400

    session = get_session()
    undo_payload = []

    try:
        for item in items:
            entity_type = item.get("entity_type")
            entity_id = item.get("entity_id")
            normalized = item.get("normalized")
            precision = item.get("precision")
            qualifier = item.get("qualifier")
            raw = item.get("raw")
            confidence = item.get("confidence")
            is_ambiguous = bool(item.get("ambiguous"))
            field = item.get("field")

            existing = session.execute(
                select(DateNormalization).where(
                    DateNormalization.entity_type == entity_type,
                    DateNormalization.entity_id == entity_id,
                    DateNormalization.raw_value == raw,
                )
            ).scalar_one_or_none()

            prev_event_date = None
            if entity_type == "event":
                ev_for_prev = session.get(Event, entity_id)
                if ev_for_prev and ev_for_prev.date_canonical:
                    prev_event_date = ev_for_prev.date_canonical.isoformat()

            if existing:
                undo_payload.append({
                    "id": existing.id,
                    "normalized": existing.normalized,
                    "precision": existing.precision,
                    "qualifier": existing.qualifier,
                    "confidence": existing.confidence,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "event_date_canonical": prev_event_date,
                })
                existing.normalized = normalized
                existing.precision = precision
                existing.qualifier = qualifier
                existing.confidence = confidence
                existing.is_ambiguous = is_ambiguous
            else:
                dn = DateNormalization(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    raw_value=raw or "",
                    normalized=normalized,
                    precision=precision,
                    qualifier=qualifier,
                    confidence=confidence,
                    is_ambiguous=is_ambiguous,
                )
                session.add(dn)
                session.flush()
                undo_payload.append({
                    "id": dn.id,
                    "delete": True,
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "event_date_canonical": prev_event_date,
                })

            if entity_type == "event":
                event = session.get(Event, entity_id)
                if event:
                    _update_event_date_canonical(event, normalized)
            if entity_type == "person" and field in ("birth_date", "death_date"):
                person = session.get(Person, entity_id)
                if person:
                    prev_value = getattr(person, field)
                    if normalized and not qualifier and not is_ambiguous:
                        setattr(person, field, normalized)
                        person.updated_at = datetime.utcnow()
                    undo_payload[-1]["person_field"] = field
                    undo_payload[-1]["person_prev"] = prev_value

        action_entry = log_action(
            session,
            "normalize_dates",
            {"items": items},
            {"items": undo_payload},
            applied_by,
        )

        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"updated": len(items), "action_id": action_entry.id, "revertToken": action_entry.id})


@api_bp.post("/dq/actions/standardizeFields")
def dq_standardize_fields():
    data = request.get_json(force=True, silent=False)
    items = data.get("items") or []
    applied_by = data.get("user")
    if not items:
        return jsonify({"error": "items required"}), 400

    session = get_session()
    undo_payload = []
    updates_applied = 0

    try:
        for item in items:
            entity_type = item.get("entity_type")
            entity_id = item.get("entity_id")
            updates = item.get("updates") or {}
            if entity_type != "person":
                return jsonify({"error": f"unsupported entity_type {entity_type}"}), 400
            if not entity_id:
                return jsonify({"error": "entity_id required"}), 400
            if not isinstance(updates, dict) or not updates:
                return jsonify({"error": "updates required"}), 400

            allowed_fields = {"given", "surname"}
            sanitized = {}
            for key, value in updates.items():
                if key not in allowed_fields:
                    continue
                if isinstance(value, str):
                    value = value.strip()
                    if not value:
                        value = None
                sanitized[key] = value

            if not sanitized:
                continue

            person = session.get(Person, entity_id)
            if not person:
                return jsonify({"error": f"person {entity_id} not found"}), 404

            prev_values = {}
            changed = False
            for field, new_value in sanitized.items():
                current = getattr(person, field)
                prev_values[field] = current
                if current != new_value:
                    setattr(person, field, new_value)
                    changed = True

            if changed:
                person.updated_at = datetime.utcnow()
                undo_payload.append({
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "previous": prev_values,
                })
                updates_applied += 1

        if not undo_payload:
            return jsonify({"error": "no changes applied"}), 400

        action_entry = log_action(
            session,
            "standardize_fields",
            {"items": items},
            {"items": undo_payload},
            applied_by,
        )

        issues = session.execute(
            select(DataQualityIssue).where(
                DataQualityIssue.issue_type == "field_standardization",
                DataQualityIssue.status == "open",
            )
        ).scalars().all()
        for issue in issues:
            try:
                ids = json.loads(issue.entity_ids)
            except Exception:
                ids = []
            if any(entry["entity_id"] in ids for entry in undo_payload):
                issue.status = "resolved"
                issue.resolved_at = datetime.utcnow()

        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"updated": updates_applied, "action_id": action_entry.id, "revertToken": action_entry.id})


@api_bp.post("/dq/actions/undo")
def dq_undo():
    data = request.get_json(force=True, silent=False)
    action_id = data.get("action_id")
    if not action_id:
        return jsonify({"error": "action_id required"}), 400
    session = get_session()
    action = session.get(DataQualityActionLog, action_id)
    if not action:
        return jsonify({"error": "action not found"}), 404
    undo_payload = json.loads(action.undo_payload_json or "{}")
    action_payload = json.loads(action.payload_json or "{}")

    try:
        if action.action_type == "merge_people":
            person_data = undo_payload.get("from_person") or {}
            restored = Person(
                id=person_data.get("id"),
                xref=person_data.get("xref"),
                given=person_data.get("given"),
                surname=person_data.get("surname"),
                sex=person_data.get("sex"),
                birth_date=person_data.get("birth_date"),
                birth_place=person_data.get("birth_place"),
                death_date=person_data.get("death_date"),
                death_place=person_data.get("death_place"),
            )
            session.add(restored)
            session.flush()

            primary_prev = undo_payload.get("primary_prev")
            if primary_prev:
                session.execute(
                    update(Person)
                    .where(Person.id == action_payload.get("intoId"))
                    .values(**primary_prev)
                )

            for rel in undo_payload.get("relationships", []):
                parent_id, child_id, rel_type = rel
                into_id = action_payload.get("intoId")
                session.execute(
                    relationships.delete().where(
                        and_(
                            relationships.c.parent_person_id == into_id,
                            relationships.c.child_person_id == child_id,
                        )
                    )
                )
                session.execute(
                    relationships.delete().where(
                        and_(
                            relationships.c.child_person_id == into_id,
                            relationships.c.parent_person_id == parent_id,
                        )
                    )
                )
                session.execute(
                    relationships.insert().values(
                        parent_person_id=parent_id,
                        child_person_id=child_id,
                        rel_type=rel_type,
                    )
                )

            for fam in undo_payload.get("families", []):
                fid = fam.get("id")
                session.execute(
                    update(Family)
                    .where(Family.id == fid)
                    .values(husband_person_id=fam.get("husband_person_id"), wife_person_id=fam.get("wife_person_id"))
                )

            for child in undo_payload.get("family_children", []):
                fid = child.get("family_id")
                cid = child.get("child_person_id")
                into_id = action_payload.get("intoId")
                session.execute(
                    family_children.delete().where(
                        and_(
                            family_children.c.family_id == fid,
                            family_children.c.child_person_id == into_id,
                        )
                    )
                )
                session.execute(
                    family_children.insert().values(family_id=fid, child_person_id=cid)
                )

            for ml in undo_payload.get("media_links", []):
                existing = session.get(MediaLink, ml.get("id"))
                if existing:
                    existing.person_id = ml.get("person_id")
                    existing.family_id = ml.get("family_id")
                else:
                    session.add(MediaLink(
                        id=ml.get("id"),
                        asset_id=ml.get("asset_id"),
                        person_id=ml.get("person_id"),
                        family_id=ml.get("family_id"),
                    ))

            for ev in undo_payload.get("events", []):
                session.execute(
                    update(Event).where(Event.id == ev.get("id")).values(person_id=ev.get("person_id"))
                )
        elif action.action_type == "merge_families":
            family_data = undo_payload.get("from_family") or {}
            restored_family = Family(
                id=family_data.get("id"),
                xref=family_data.get("xref"),
                husband_person_id=family_data.get("husband_person_id"),
                wife_person_id=family_data.get("wife_person_id"),
                marriage_date=family_data.get("marriage_date"),
                marriage_place=family_data.get("marriage_place"),
            )
            session.add(restored_family)
            session.flush()

            primary_prev = undo_payload.get("primary_prev")
            if primary_prev:
                session.execute(
                    update(Family)
                    .where(Family.id == action_payload.get("intoId"))
                    .values(**primary_prev)
                )

            for rel in undo_payload.get("inserted_relationships", []):
                parent_id, child_id, rel_type = rel
                session.execute(
                    relationships.delete().where(
                        and_(
                            relationships.c.parent_person_id == parent_id,
                            relationships.c.child_person_id == child_id,
                            relationships.c.rel_type == rel_type,
                        )
                    )
                )

            for child in undo_payload.get("children", []):
                fid = child.get("family_id")
                cid = child.get("child_person_id")
                into_existed = child.get("into_existed")
                if not into_existed:
                    session.execute(
                        family_children.delete().where(
                            and_(
                                family_children.c.family_id == action_payload.get("intoId"),
                                family_children.c.child_person_id == cid,
                            )
                        )
                    )
                session.execute(
                    family_children.insert().values(family_id=fid, child_person_id=cid)
                )

            for ev in undo_payload.get("events", []):
                session.execute(
                    update(Event).where(Event.id == ev.get("id")).values(family_id=ev.get("family_id"))
                )
            for note in undo_payload.get("notes", []):
                session.execute(
                    update(Note).where(Note.id == note.get("id")).values(family_id=note.get("family_id"))
                )

            for ml in undo_payload.get("media_links", []):
                existing = session.get(MediaLink, ml.get("id"))
                if existing:
                    existing.family_id = ml.get("family_id")
                    existing.person_id = ml.get("person_id")
                else:
                    session.add(MediaLink(
                        id=ml.get("id"),
                        asset_id=ml.get("asset_id"),
                        person_id=ml.get("person_id"),
                        family_id=ml.get("family_id"),
                    ))
        elif action.action_type == "dedupe_media_links":
            for link in undo_payload.get("deleted_links", []):
                session.add(MediaLink(
                    id=link.get("id"),
                    asset_id=link.get("asset_id"),
                    person_id=link.get("person_id"),
                    family_id=link.get("family_id"),
                ))
        elif action.action_type == "merge_media_assets":
            asset_data = undo_payload.get("from_asset") or {}
            created_at = asset_data.get("created_at")
            created_at_value = None
            if created_at:
                try:
                    created_at_value = datetime.fromisoformat(created_at)
                except Exception:
                    created_at_value = None
            restored = MediaAsset(
                id=asset_data.get("id"),
                path=asset_data.get("path"),
                sha256=asset_data.get("sha256"),
                original_filename=asset_data.get("original_filename"),
                mime_type=asset_data.get("mime_type"),
                size_bytes=asset_data.get("size_bytes"),
                thumbnail_path=asset_data.get("thumbnail_path"),
                thumb_width=asset_data.get("thumb_width"),
                thumb_height=asset_data.get("thumb_height"),
                status=asset_data.get("status") or "unassigned",
                source_path=asset_data.get("source_path"),
                created_at=created_at_value,
            )
            session.add(restored)
            session.flush()
            for link in undo_payload.get("links", []):
                session.execute(
                    update(MediaLink).where(MediaLink.id == link.get("id")).values(asset_id=link.get("asset_id"))
                )

        elif action.action_type == "normalize_places":
            for ev in undo_payload.get("events", []):
                session.execute(
                    update(Event)
                    .where(Event.id == ev.get("id"))
                    .values(place_id=ev.get("place_id"), place_raw=ev.get("place_raw"))
                )
            for p in undo_payload.get("persons", []):
                session.execute(
                    update(Person)
                    .where(Person.id == p.get("id"))
                    .values(birth_place=p.get("birth_place"), death_place=p.get("death_place"))
                )
        elif action.action_type == "normalize_dates":
            for item in undo_payload.get("items", []):
                norm = session.get(DateNormalization, item.get("id"))
                if item.get("delete"):
                    if norm:
                        session.delete(norm)
                else:
                    if norm:
                        norm.normalized = item.get("normalized")
                        norm.precision = item.get("precision")
                        norm.qualifier = item.get("qualifier")
                        norm.confidence = item.get("confidence")
                if item.get("entity_type") == "event":
                    ev = session.get(Event, item.get("entity_id"))
                    if ev:
                        target_date = item.get("event_date_canonical")
                        if target_date:
                            try:
                                ev.date_canonical = datetime.fromisoformat(target_date)
                            except Exception:
                                try:
                                    ev.date_canonical = datetime.strptime(target_date, "%Y-%m-%d")
                                except Exception:
                                    ev.date_canonical = None
                        else:
                            ev.date_canonical = None
                if item.get("entity_type") == "person":
                    field = item.get("person_field")
                    prev = item.get("person_prev")
                    if field in ("birth_date", "death_date"):
                        session.execute(
                            update(Person).where(Person.id == item.get("entity_id")).values(**{field: prev})
                        )
        elif action.action_type == "standardize_fields":
            for item in undo_payload.get("items", []):
                entity_type = item.get("entity_type")
                entity_id = item.get("entity_id")
                previous = item.get("previous") or {}
                if entity_type == "person":
                    session.execute(
                        update(Person).where(Person.id == entity_id).values(**previous)
                    )

        session.delete(action)
        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"undone": True})


@ui_bp.get("/data-quality")
def data_quality_page():
    return render_template("data-quality.html")

# ---- Place normalization plan (save approvals, export/import, bulk apply) ----

def _row_to_rule(row) -> dict:
    return {
        "id": row[0],
        "canonical": row[1],
        "variants": json.loads(row[2] or "[]"),
        "approved": bool(row[3]),
        "source_issue_id": row[4],
        "authority_source": row[5],
        "authority_id": row[6],
        "latitude": row[7],
        "longitude": row[8],
        "notes": row[9],
        "created_at": row[10],
        "updated_at": row[11],
    }


@api_bp.get("/places/normalization/rules")
def place_norm_rules_list():
    approved = request.args.get("approved")
    session = get_session()
    where = ""
    params = {}
    if approved is not None:
        where = "WHERE approved = :approved"
        params["approved"] = 1 if str(approved).lower() in ("1", "true", "yes") else 0

    rows = session.execute(
        text(
            f"""
            SELECT id, canonical, variants_json, approved, source_issue_id,
                   authority_source, authority_id, latitude, longitude, notes,
                   created_at, updated_at
            FROM place_normalization_rules
            {where}
            ORDER BY canonical
            """
        ),
        params,
    ).all()
    return jsonify({"items": [_row_to_rule(r) for r in rows]})


@api_bp.post("/places/normalization/rules/upsert")
def place_norm_rules_upsert():
    data = request.get_json(force=True, silent=False) or {}
    rules = data.get("rules")
    if rules is None:
        # allow single rule payload
        rules = [data]

    session = get_session()
    out = []
    try:
        for rule in rules:
            canonical = (rule.get("canonical") or "").strip()
            variants = [v.strip() for v in (rule.get("variants") or []) if v and v.strip()]
            approved = 1 if rule.get("approved") else 0
            source_issue_id = rule.get("source_issue_id")
            authority_source = (rule.get("authority_source") or None)
            authority_id = (rule.get("authority_id") or None)
            latitude = rule.get("latitude")
            longitude = rule.get("longitude")
            notes = rule.get("notes")

            if not canonical or not variants:
                continue

            existing = session.execute(
                text(
                    """
                    SELECT id, variants_json, approved, authority_source, authority_id, latitude, longitude, notes
                    FROM place_normalization_rules
                    WHERE canonical = :canonical
                    """
                ),
                {"canonical": canonical},
            ).first()

            merged_variants = set(variants)
            ex_id = None
            ex_approved = 0
            ex_auth_source = None
            ex_auth_id = None
            ex_lat = None
            ex_lon = None
            ex_notes = None
            if existing:
                ex_id = existing[0]
                merged_variants |= set(json.loads(existing[1] or "[]"))
                ex_approved = int(existing[2] or 0)
                ex_auth_source = existing[3]
                ex_auth_id = existing[4]
                ex_lat = existing[5]
                ex_lon = existing[6]
                ex_notes = existing[7]

            merged_list = sorted(merged_variants, key=lambda s: s.lower())
            # Prefer explicit approved; otherwise keep existing
            final_approved = approved if (rule.get("approved") is not None) else ex_approved
            final_auth_source = authority_source if authority_source is not None else ex_auth_source
            final_auth_id = authority_id if authority_id is not None else ex_auth_id
            final_lat = float(latitude) if latitude is not None else ex_lat
            final_lon = float(longitude) if longitude is not None else ex_lon
            final_notes = notes if notes is not None else ex_notes

            if existing:
                session.execute(
                    text(
                        """
                        UPDATE place_normalization_rules
                        SET variants_json = :variants_json,
                            approved = :approved,
                            source_issue_id = COALESCE(:source_issue_id, source_issue_id),
                            authority_source = :authority_source,
                            authority_id = :authority_id,
                            latitude = :latitude,
                            longitude = :longitude,
                            notes = :notes,
                            updated_at = datetime('now')
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": ex_id,
                        "variants_json": json.dumps(merged_list),
                        "approved": final_approved,
                        "source_issue_id": source_issue_id,
                        "authority_source": final_auth_source,
                        "authority_id": final_auth_id,
                        "latitude": final_lat,
                        "longitude": final_lon,
                        "notes": final_notes,
                    },
                )
            else:
                session.execute(
                    text(
                        """
                        INSERT INTO place_normalization_rules
                            (canonical, variants_json, approved, source_issue_id,
                             authority_source, authority_id, latitude, longitude, notes)
                        VALUES
                            (:canonical, :variants_json, :approved, :source_issue_id,
                             :authority_source, :authority_id, :latitude, :longitude, :notes)
                        """
                    ),
                    {
                        "canonical": canonical,
                        "variants_json": json.dumps(merged_list),
                        "approved": final_approved,
                        "source_issue_id": source_issue_id,
                        "authority_source": final_auth_source,
                        "authority_id": final_auth_id,
                        "latitude": final_lat,
                        "longitude": final_lon,
                        "notes": final_notes,
                    },
                )

            out.append({"canonical": canonical, "approved": bool(final_approved), "variants": merged_list})

        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"saved": out})


@api_bp.get("/places/normalization/export")
def place_norm_export():
    session = get_session()
    rows = session.execute(
        text(
            """
            SELECT canonical, variants_json, authority_source, authority_id, latitude, longitude, notes
            FROM place_normalization_rules
            WHERE approved = 1
            ORDER BY canonical
            """
        )
    ).all()

    rules = []
    for canonical, variants_json, a_src, a_id, lat, lon, notes in rows:
        rules.append({
            "approved": True,
            "canonical": canonical,
            "variants": json.loads(variants_json or "[]"),
            "authority": {
                "source": a_src,
                "id": a_id,
                "latitude": lat,
                "longitude": lon,
            } if (a_src or a_id or lat is not None or lon is not None) else None,
            "notes": notes,
        })

    payload = {
        "version": 1,
        "exportedAt": datetime.utcnow().isoformat() + "Z",
        "rules": rules,
    }
    return jsonify(payload)


@api_bp.post("/places/normalization/import")
def place_norm_import():
    data = request.get_json(force=True, silent=False) or {}
    rules = data.get("rules") or []
    if not isinstance(rules, list):
        return jsonify({"error": "rules must be a list"}), 400

    session = get_session()
    saved = []
    try:
        for r in rules:
            canonical = (r.get("canonical") or "").strip()
            variants = [v.strip() for v in (r.get("variants") or []) if v and v.strip()]
            approved = 1 if (r.get("approved") is None or bool(r.get("approved"))) else 0

            auth = r.get("authority") or {}
            authority_source = auth.get("source")
            authority_id = auth.get("id")
            latitude = auth.get("latitude")
            longitude = auth.get("longitude")
            notes = r.get("notes")

            if not canonical or not variants:
                continue

            existing = session.execute(
                text("SELECT id, variants_json FROM place_normalization_rules WHERE canonical = :canonical"),
                {"canonical": canonical},
            ).first()

            merged = set(variants)
            ex_id = None
            if existing:
                ex_id = existing[0]
                merged |= set(json.loads(existing[1] or "[]"))

            merged_list = sorted(merged, key=lambda s: s.lower())

            if ex_id:
                session.execute(
                    text(
                        """
                        UPDATE place_normalization_rules
                        SET variants_json = :variants_json,
                            approved = :approved,
                            authority_source = COALESCE(:authority_source, authority_source),
                            authority_id = COALESCE(:authority_id, authority_id),
                            latitude = COALESCE(:latitude, latitude),
                            longitude = COALESCE(:longitude, longitude),
                            notes = COALESCE(:notes, notes),
                            updated_at = datetime('now')
                        WHERE id = :id
                        """
                    ),
                    {
                        "id": ex_id,
                        "variants_json": json.dumps(merged_list),
                        "approved": approved,
                        "authority_source": authority_source,
                        "authority_id": authority_id,
                        "latitude": latitude,
                        "longitude": longitude,
                        "notes": notes,
                    },
                )
            else:
                session.execute(
                    text(
                        """
                        INSERT INTO place_normalization_rules
                          (canonical, variants_json, approved, authority_source, authority_id, latitude, longitude, notes)
                        VALUES
                          (:canonical, :variants_json, :approved, :authority_source, :authority_id, :latitude, :longitude, :notes)
                        """
                    ),
                    {
                        "canonical": canonical,
                        "variants_json": json.dumps(merged_list),
                        "approved": approved,
                        "authority_source": authority_source,
                        "authority_id": authority_id,
                        "latitude": latitude,
                        "longitude": longitude,
                        "notes": notes,
                    },
                )

            saved.append({"canonical": canonical, "variants": merged_list, "approved": bool(approved)})

        session.commit()
    except Exception:
        session.rollback()
        raise

    return jsonify({"imported": len(saved), "items": saved})

@api_bp.post("/places/normalization/apply")
def place_norm_apply():
    data = request.get_json(force=True, silent=False) or {}
    dry_run = bool(data.get("dry_run") or False)
    limit = data.get("limit")
    applied_by = data.get("user") or "place-norm-bulk"
    only_ids = data.get("ids")  # optional list of rule ids

    session = get_session()
    params = {}
    where = "WHERE approved = 1"
    if only_ids:
        where += " AND id IN (" + ",".join([str(int(x)) for x in only_ids]) + ")"
    stmt = f"""
        SELECT id, canonical, variants_json, authority_source, authority_id, latitude, longitude
        FROM place_normalization_rules
        {where}
        ORDER BY canonical
    """
    rows = session.execute(text(stmt), params).all()
    if limit is not None:
        rows = rows[: int(limit)]

    if dry_run:
        preview = []
        for rid, canonical, variants_json, a_src, a_id, lat, lon in rows:
            preview.append({
                "id": rid,
                "canonical": canonical,
                "variants": json.loads(variants_json or "[]"),
                "authority_source": a_src,
                "authority_id": a_id,
                "latitude": lat,
                "longitude": lon,
            })
        return jsonify({"dry_run": True, "count": len(preview), "items": preview})

    results = {"applied": [], "failed": []}
    for rid, canonical, variants_json, a_src, a_id, lat, lon in rows:
        try:
            variants = json.loads(variants_json or "[]")
            place_id, action_id = _apply_place_normalization(
                session=session,
                canonical_value=canonical,
                variants=variants,
                applied_by=applied_by,
                resolve_issues=False,  # we'll re-scan anyway
            )

            # Optional enrichment: attach authority if provided and not already present
            if (a_src or a_id or lat is not None or lon is not None):
                place = session.get(Place, place_id)
                if place:
                    if a_src and (getattr(place, "authority_source", None) is None):
                        setattr(place, "authority_source", a_src)
                    if a_id and (getattr(place, "authority_id", None) is None):
                        setattr(place, "authority_id", a_id)
                    if lat is not None and getattr(place, "latitude", None) is None:
                        setattr(place, "latitude", float(lat))
                    if lon is not None and getattr(place, "longitude", None) is None:
                        setattr(place, "longitude", float(lon))
                    session.commit()

            results["applied"].append({"rule_id": rid, "canonical_place_id": place_id, "action_id": action_id})
        except Exception as e:
            try:
                session.rollback()
            except Exception:
                pass
            results["failed"].append({"rule_id": rid, "canonical": canonical, "error": str(e)})

    return jsonify(results)
