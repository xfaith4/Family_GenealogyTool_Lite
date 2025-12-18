from __future__ import annotations

from flask import Blueprint, jsonify, request, current_app, send_from_directory, render_template
from werkzeug.utils import secure_filename
from sqlalchemy import select, or_, func
from datetime import datetime
import os
import hashlib
from pathlib import Path

from .db import get_session
from .models import Person, Family, Note, MediaAsset, MediaLink, relationships, family_children
from .gedcom import parse_gedcom, to_summary
from .media_utils import compute_sha256, is_image, create_thumbnail, safe_filename

api_bp = Blueprint("api", __name__, url_prefix="/api")
ui_bp = Blueprint("ui", __name__)

@ui_bp.get("/")
def index():
    return render_template("index.html")

@ui_bp.get("/media/unassigned")
def unassigned_media_page():
    return render_template("unassigned.html")

@ui_bp.get("/tree-v2")
def tree_v2_page():
    return render_template("tree-v2.html")

def _person_to_dict(p: Person) -> dict:
    return {
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

    out = _person_to_dict(person)
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
    return jsonify(_person_to_dict(person))

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
                            rel_type='parent'
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
                            rel_type='parent'
                        )
                    )
                except Exception:
                    # Relationship already exists, ignore
                    pass

    session.commit()
    return jsonify({"imported": to_summary(indis, fams)})

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
            size_bytes=size_bytes
        )
        session.add(media_asset)
        session.flush()
    
    # Create media link
    media_link = MediaLink(
        asset_id=media_asset.id,
        person_id=person_id
    )
    session.add(media_link)
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

@api_bp.get("/media/unassigned")
def list_unassigned_media():
    """List media assets without any links."""
    session = get_session()
    assets = session.execute(
        select(MediaAsset)
        .outerjoin(MediaLink, MediaLink.asset_id == MediaAsset.id)
        .where(MediaLink.id.is_(None))
        .order_by(MediaAsset.created_at.desc())
        .limit(200)
    ).scalars().all()
    
    return jsonify([_media_asset_dict(asset) for asset in assets])

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
    session.commit()

    return jsonify({"link_id": link.id}), 201

@api_bp.delete("/media/link/<int:link_id>")
def unlink_media(link_id: int):
    """Remove a media link."""
    session = get_session()
    link = session.get(MediaLink, link_id)
    if not link:
        return jsonify({"error": "Link not found"}), 404

    session.delete(link)
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
