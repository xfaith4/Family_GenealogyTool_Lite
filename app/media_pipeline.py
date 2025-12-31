from __future__ import annotations

import csv
import hashlib
import json
import mimetypes
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import select, func
from sqlalchemy.orm import Session, sessionmaker

from .media_utils import create_thumbnail, is_image, safe_filename
from .models import MediaAsset, MediaLink, MediaDerivation, Person
from .rmtree import (
    collect_media_associations,
    collect_media_locations,
    collect_person_records,
    load_tables_from_sqlite,
)

MEDIA_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tif", ".tiff", ".bmp", ".heic", ".pdf", ".mp4", ".mov", ".avi", ".mkv"}
OCR_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def compute_sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_path(value: str) -> str:
    cleaned = (value or "").strip().replace("\\", "/")
    cleaned = re.sub(r"/+", "/", cleaned)
    if re.match(r"^[a-zA-Z]:/", cleaned):
        cleaned = cleaned[2:]
    cleaned = cleaned.lstrip("/").lower()
    return cleaned


def log_event(event: str, payload: Dict[str, Any] | None = None, verbose: bool = False) -> None:
    if not verbose:
        return
    out = {"event": event, **(payload or {})}
    print(json.dumps(out, default=str))


@dataclass
class MediaPaths:
    media_dir: Path
    ingest_dir: Path


class MediaIngestService:
    def __init__(self, session: Session, paths: MediaPaths, verbose: bool = False, dry_run: bool = False):
        self.session = session
        self.paths = paths
        self.verbose = verbose
        self.dry_run = dry_run
        self.paths.media_dir.mkdir(parents=True, exist_ok=True)
        self.paths.ingest_dir.mkdir(parents=True, exist_ok=True)

    def register_asset(
        self,
        file_path: Path,
        original_name: Optional[str] = None,
        status: str = "unassigned",
    ) -> Tuple[MediaAsset, bool]:
        file_path = Path(file_path)
        name = original_name or file_path.name
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        sha = compute_sha256_file(file_path)

        existing = self.session.execute(select(MediaAsset).where(MediaAsset.sha256 == sha)).scalar_one_or_none()
        if existing:
            updated = False
            if not existing.source_path:
                existing.source_path = str(file_path)
                updated = True
            if not existing.path:
                rel_path, _ = self._ensure_asset_file(file_path, name, sha, mime)
                existing.path = rel_path
                updated = True
            if updated and not self.dry_run:
                self.session.flush()
            log_event("media.asset.exists", {"sha256": sha, "id": existing.id}, self.verbose)
            return existing, False

        rel_path, dest = self._ensure_asset_file(file_path, name, sha, mime)
        thumbnail_path, thumb_w, thumb_h = self._ensure_thumbnail(dest, sha, mime)

        asset = MediaAsset(
            path=rel_path,
            sha256=sha,
            original_filename=name,
            mime_type=mime,
            size_bytes=file_path.stat().st_size,
            thumbnail_path=thumbnail_path,
            thumb_width=thumb_w,
            thumb_height=thumb_h,
            source_path=str(file_path),
            status=status,
        )
        if not self.dry_run:
            self.session.add(asset)
            self.session.flush()
        log_event("media.asset.created", {"sha256": sha, "path": rel_path}, self.verbose)
        return asset, True

    def scan_directory(self, source_dir: Path, exts: Iterable[str] = MEDIA_EXTS) -> int:
        source_dir = Path(source_dir)
        if not source_dir.exists():
            return 0
        exts = set(exts) if exts else set(MEDIA_EXTS)
        count = 0
        for file_path in source_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in exts:
                continue
            _, created = self.register_asset(file_path)
            if created:
                count += 1
        if not self.dry_run:
            self.session.commit()
        return count

    def refresh_asset_status(self, asset_id: int) -> None:
        link_count = self.session.execute(
            select(func.count(MediaLink.id)).where(MediaLink.asset_id == asset_id)
        ).scalar_one()
        asset = self.session.get(MediaAsset, asset_id)
        if not asset:
            return
        has_file = bool(asset.path) and (self.paths.media_dir / asset.path).exists()
        if asset.size_bytes is None or not asset.path or not has_file:
            asset.status = "unassigned"
        else:
            asset.status = "assigned" if link_count else "unassigned"
        if not self.dry_run:
            self.session.flush()

    def ensure_derivation(self, original_id: int, derived_id: int, derivation_type: str) -> bool:
        existing = self.session.execute(
            select(MediaDerivation).where(
                MediaDerivation.original_asset_id == original_id,
                MediaDerivation.derived_asset_id == derived_id,
                MediaDerivation.derivation_type == derivation_type,
            )
        ).scalar_one_or_none()
        if existing:
            return False
        if not self.dry_run:
            self.session.add(MediaDerivation(
                original_asset_id=original_id,
                derived_asset_id=derived_id,
                derivation_type=derivation_type,
            ))
            self.session.flush()
        return True

    def _ensure_asset_file(self, file_path: Path, name: str, sha: str, mime: str) -> Tuple[str, Path]:
        try:
            rel = file_path.resolve().relative_to(self.paths.media_dir.resolve()).as_posix()
            return rel, file_path
        except Exception:
            pass
        rel = safe_filename(name, sha, mime)
        dest = self.paths.media_dir / rel
        if not dest.exists() and not self.dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file_path, dest)
        return rel, dest

    def _ensure_thumbnail(self, dest: Path, sha: str, mime: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
        if not is_image(mime):
            return None, None, None
        if self.dry_run:
            return None, None, None
        thumb_result = create_thumbnail(dest.as_posix(), self.paths.media_dir.as_posix(), sha)
        if not thumb_result:
            return None, None, None
        thumbnail_path, thumb_w, thumb_h = thumb_result
        return os.path.basename(thumbnail_path), thumb_w, thumb_h


class OCRService:
    def __init__(self, ingest: MediaIngestService, lang: str = "eng", verbose: bool = False, dry_run: bool = False):
        self.ingest = ingest
        self.lang = lang
        self.verbose = verbose
        self.dry_run = dry_run

    def ocr_path(self, path: Path, out_dir: Optional[Path] = None, only_missing: bool = False) -> Optional[MediaAsset]:
        path = Path(path)
        if not path.exists():
            return None
        if path.suffix.lower() not in OCR_IMAGE_EXTS and path.suffix.lower() != ".pdf":
            return None

        orig_asset, _ = self.ingest.register_asset(path)
        if only_missing and self._has_derivation(orig_asset.id, "ocr_pdf"):
            log_event("ocr.skip.exists", {"asset_id": orig_asset.id}, self.verbose)
            return None

        sha = compute_sha256_file(path)
        out_root = out_dir or (self.ingest.paths.media_dir / "derived" / "ocr")
        out_root.mkdir(parents=True, exist_ok=True)
        out_pdf = out_root / f"{sha}.pdf"
        out_txt = out_root / f"{sha}.txt"

        tool = self._find_tool()
        if tool is None:
            log_event("ocr.missing_tool", {"path": str(path)}, self.verbose)
            return None

        if self.dry_run:
            return None

        if tool == "ocrmypdf":
            cmd = [
                "ocrmypdf",
                "--output-type", "pdfa",
                "--skip-text",
                "--sidecar", str(out_txt),
                "-l", self.lang,
                str(path),
                str(out_pdf),
            ]
        else:
            base_out = out_pdf.with_suffix("")
            cmd = ["tesseract", str(path), str(base_out), "-l", self.lang, "pdf"]

        try:
            subprocess.run(cmd, check=True, capture_output=not self.verbose)
        except subprocess.CalledProcessError as exc:
            log_event("ocr.failed", {"path": str(path), "error": str(exc)}, self.verbose)
            return None

        if not out_pdf.exists():
            return None

        derived_asset, created = self.ingest.register_asset(out_pdf, original_name=out_pdf.name, status="unassigned")
        if created:
            self.ingest.ensure_derivation(orig_asset.id, derived_asset.id, "ocr_pdf")

        if out_txt.exists():
            text_asset, created_txt = self.ingest.register_asset(out_txt, original_name=out_txt.name, status="unassigned")
            if created_txt:
                self.ingest.ensure_derivation(orig_asset.id, text_asset.id, "ocr_text")

        if not self.dry_run:
            self.ingest.session.commit()
        return derived_asset

    def _find_tool(self) -> Optional[str]:
        if shutil.which("ocrmypdf"):
            return "ocrmypdf"
        if shutil.which("tesseract"):
            return "tesseract"
        return None

    def _has_derivation(self, original_id: int, derivation_type: str) -> bool:
        existing = self.ingest.session.execute(
            select(MediaDerivation).where(
                MediaDerivation.original_asset_id == original_id,
                MediaDerivation.derivation_type == derivation_type,
            )
        ).scalar_one_or_none()
        return bool(existing)


@dataclass
class LegacyAssociation:
    media_id: Any
    owner_type: str
    owner_id: Any
    path: Optional[str]
    original_name: Optional[str]
    description: Optional[str]


class LegacyAssociationSource:
    def __init__(self, db_path: Path):
        self.db_path = db_path

    def load(self) -> Tuple[List[LegacyAssociation], Dict[Any, Dict[str, Any]]]:
        tables = load_tables_from_sqlite(str(self.db_path))
        locations = collect_media_locations(tables)
        associations = collect_media_associations(tables)
        people = collect_person_records(tables)
        person_map = {p["source_id"]: p for p in people if p.get("source_id") is not None}
        loc_map = {loc["media_id"]: loc for loc in locations if loc.get("media_id") is not None}
        merged: List[LegacyAssociation] = []
        for assoc in associations:
            media_id = assoc.get("media_id")
            owner_type = assoc.get("owner_type")
            owner_id = assoc.get("owner_id")
            loc = loc_map.get(media_id, {})
            merged.append(LegacyAssociation(
                media_id=media_id,
                owner_type=owner_type,
                owner_id=owner_id,
                path=loc.get("path"),
                original_name=loc.get("original_name"),
                description=loc.get("description"),
            ))
        return merged, person_map


def match_candidates(
    legacy_path: Optional[str],
    legacy_name: Optional[str],
    assets: List[MediaAsset],
    media_dir: Path,
    ingest_dir: Path,
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    if not legacy_path and not legacy_name:
        return candidates

    legacy_basename = Path(legacy_path or legacy_name or "").name
    norm_legacy = normalize_path(legacy_path or legacy_name or "")

    def add_candidate(asset: MediaAsset, method: str, confidence: float) -> None:
        candidates.append({
            "asset_id": asset.id,
            "method": method,
            "confidence": confidence,
        })

    if legacy_path:
        legacy_file = Path(legacy_path)
        if legacy_file.exists():
            sha = compute_sha256_file(legacy_file)
            match = next((a for a in assets if a.sha256 == sha), None)
            if match:
                add_candidate(match, "sha256", 1.0)
                return candidates

    for asset in assets:
        if asset.path:
            if normalize_path(asset.path) == norm_legacy:
                add_candidate(asset, "path", 0.95)
        if asset.original_filename and normalize_path(asset.original_filename) == normalize_path(legacy_basename):
            add_candidate(asset, "basename", 0.8)
        if asset.source_path and normalize_path(asset.source_path) == norm_legacy:
            add_candidate(asset, "source_path", 0.9)

    return candidates


def legacy_link(
    session: Session,
    paths: MediaPaths,
    legacy_db: Path,
    report_path: Path,
    apply: bool = False,
    min_confidence: float = 0.9,
    verbose: bool = False,
    dry_run: bool = False,
) -> Dict[str, Any]:
    source = LegacyAssociationSource(legacy_db)
    associations, person_map = source.load()
    people = session.execute(select(Person.id, Person.given, Person.surname, Person.xref)).all()
    xref_map = {p.xref: p.id for p in people if p.xref}
    name_map = {f"{(p.given or '').strip().lower()} {(p.surname or '').strip().lower()}".strip(): p.id for p in people}
    assets = session.execute(select(MediaAsset)).scalars().all()
    ingest = MediaIngestService(session, paths, verbose=verbose, dry_run=dry_run)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_rows = []
    applied = 0

    for assoc in associations:
        if assoc.owner_type != "person":
            continue
        legacy_person = person_map.get(assoc.owner_id)
        person_id = None
        if legacy_person:
            legacy_xref = legacy_person.get("xref")
            if legacy_xref and legacy_xref in xref_map:
                person_id = xref_map[legacy_xref]
            else:
                person_id = xref_map.get(f"rmtree:{legacy_person.get('source_id')}")
            if not person_id:
                name_key = f"{(legacy_person.get('given') or '').strip().lower()} {(legacy_person.get('surname') or '').strip().lower()}".strip()
                person_id = name_map.get(name_key)

        candidates = match_candidates(assoc.path, assoc.original_name, assets, paths.media_dir, paths.ingest_dir)
        if not candidates and assoc.path:
            search_name = Path(assoc.path).name
            for root in (paths.media_dir, paths.ingest_dir):
                candidate_file = root / search_name
                if candidate_file.exists():
                    asset, _ = ingest.register_asset(candidate_file)
                    candidates = [{"asset_id": asset.id, "method": "basename_disk", "confidence": 0.85}]
                    assets.append(asset)
                    break

        best = max(candidates, key=lambda c: c["confidence"], default=None)
        confidence = best["confidence"] if best else 0.0
        asset_id = best["asset_id"] if best else None
        method = best["method"] if best else "none"

        report_rows.append({
            "legacy_ref": assoc.path or assoc.original_name or "",
            "current_path": _asset_path_by_id(assets, asset_id),
            "person_id": person_id or "",
            "person_name": _person_name_by_id(people, person_id),
            "match_method": method,
            "confidence": confidence,
        })

        if apply and asset_id and person_id and confidence >= min_confidence:
            existing_link = session.execute(
                select(MediaLink).where(
                    MediaLink.asset_id == asset_id,
                    MediaLink.person_id == person_id,
                )
            ).scalar_one_or_none()
            if not existing_link and not dry_run:
                session.add(MediaLink(
                    asset_id=asset_id,
                    person_id=person_id,
                    description=f"legacy:rmtree:{assoc.media_id}",
                ))
                ingest.refresh_asset_status(asset_id)
                applied += 1

    if not dry_run:
        session.commit()

    with open(report_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["legacy_ref", "current_path", "person_id", "person_name", "match_method", "confidence"],
        )
        writer.writeheader()
        writer.writerows(report_rows)

    return {"applied": applied, "report": str(report_path), "candidates": len(report_rows)}


def _asset_path_by_id(assets: Iterable[MediaAsset], asset_id: Optional[int]) -> str:
    for asset in assets:
        if asset.id == asset_id:
            return asset.path or ""
    return ""


def _person_name_by_id(people_rows: Iterable[Tuple[Any, Any, Any, Any]], person_id: Optional[int]) -> str:
    for pid, given, surname, _ in people_rows:
        if pid == person_id:
            return f"{given or ''} {surname or ''}".strip()
    return ""


def run_watch_loop(
    session_factory: sessionmaker,
    paths: MediaPaths,
    interval: float = 5.0,
    ocr: bool = False,
    lang: str = "eng",
    verbose: bool = False,
    dry_run: bool = False,
) -> None:
    seen: Dict[str, float] = {}
    while True:
        session = session_factory()
        try:
            ingest = MediaIngestService(session, paths, verbose=verbose, dry_run=dry_run)
            new_files = []
            for file_path in paths.ingest_dir.rglob("*"):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in MEDIA_EXTS:
                    continue
                key = str(file_path)
                mtime = file_path.stat().st_mtime
                if key in seen and seen[key] >= mtime:
                    continue
                seen[key] = mtime
                new_files.append(file_path)

            for file_path in new_files:
                ingest.register_asset(file_path)

            if ocr and new_files:
                ocr_service = OCRService(ingest, lang=lang, verbose=verbose, dry_run=dry_run)
                for file_path in new_files:
                    ocr_service.ocr_path(file_path, only_missing=True)
            if new_files and not dry_run:
                session.commit()
        finally:
            session.close()
        time.sleep(interval)
