from __future__ import annotations

from flask import Blueprint, jsonify, request, current_app, send_from_directory, render_template
from werkzeug.utils import secure_filename
from sqlalchemy import select, or_
from datetime import datetime
import os
import hashlib

from .db import get_session
from .models import Person, Family, Note, MediaAsset, MediaLink, relationships
from .gedcom import parse_gedcom, to_summary

api_bp = Blueprint("api", __name__, url_prefix="/api")
ui_bp = Blueprint("ui", __name__)

@ui_bp.get("/")
def index():
    return render_template("index.html")

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
            "file_name": asset.file_name,
            "original_name": asset.original_name,
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
            file_name=stored_name,
            original_name=original_name,
            mime_type=mime,
            sha256=sha,
            size_bytes=size_bytes
        )
        session.add(media_asset)
        session.flush()
    
    # Create media link
    media_link = MediaLink(
        media_asset_id=media_asset.id,
        person_id=person_id
    )
    session.add(media_link)
    session.commit()

    return jsonify({"stored": stored_name, "sha256": sha}), 201

@api_bp.get("/media/<path:file_name>")
def get_media(file_name: str):
    media_dir = current_app.config["MEDIA_DIR"]
    return send_from_directory(media_dir, file_name, as_attachment=False)
