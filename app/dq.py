from __future__ import annotations

"""
Deterministic data-quality detection and remediation helpers.

This module intentionally avoids heuristics that are not explainable. Each issue
is stored as a DataQualityIssue row with an explanation payload that can be
shown to users in the Data Quality dashboard.
"""

from datetime import datetime
import json
import math
import re
import os
from collections import defaultdict, Counter
from difflib import SequenceMatcher
from typing import Iterable, List, Tuple, Dict, Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session, load_only

from .models import (
    Person,
    Family,
    Event,
    Place,
    PlaceVariant,
    MediaAsset,
    MediaLink,
    DataQualityIssue,
    DataQualityActionLog,
    DateNormalization,
    relationships,
    family_children,
)


YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")
DATE_RANGE_RE = re.compile(r"\bBET\s+(?P<start>\d{3,4})\s+AND\s+(?P<end>\d{3,4})", re.IGNORECASE)
QUALIFIER_RE = re.compile(r"\b(ABT|ABOUT|BEF|AFT|EST|CALC|CIRCA|CA\.?)\b", re.IGNORECASE)
AMBIGUOUS_NUMERIC_RE = re.compile(r"^(?P<first>\d{1,2})[/-](?P<second>\d{1,2})[/-](?P<year>\d{3,4})$")
PLACE_CLEAN_CONFIDENCE = 0.65  # confidence threshold for automated place normalization; keeps automated cleaning conservative and reviewable


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").lower().strip().split())


def _collapse_spaces(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().split())


def _case_state(value: str) -> str | None:
    letters = [c for c in value if c.isalpha()]
    if not letters:
        return None
    if all(c.isupper() for c in letters):
        return "upper"
    if all(c.islower() for c in letters):
        return "lower"
    return None


def _title_case(value: str) -> str:
    def cap_word(word: str) -> str:
        if not word:
            return word
        lower = word.lower()
        if lower.startswith("mc") and len(lower) > 2 and lower[2].isalpha():
            return "Mc" + lower[2].upper() + lower[3:]
        return lower[:1].upper() + lower[1:]

    def cap_token(token: str) -> str:
        parts = token.split("-")
        return "-".join(cap_piece(p) for p in parts)

    def cap_piece(piece: str) -> str:
        parts = piece.split("'")
        return "'".join(cap_word(p) for p in parts)

    return " ".join(cap_token(token) for token in value.split())


def _suggest_name_standard(value: str | None) -> tuple[str | None, list[str]]:
    if not value:
        return value, []
    trimmed = _collapse_spaces(value)
    if trimmed is None:
        return value, []
    reasons = []
    suggestion = trimmed
    if trimmed != value:
        reasons.append("trim_whitespace")
    state = _case_state(trimmed)
    if state in ("upper", "lower"):
        titled = _title_case(trimmed)
        if titled != trimmed:
            suggestion = titled
            reasons.append("title_case")
    return suggestion, reasons

def _norm_place(value: str | None) -> str:
    if not value:
        return ""
    v = value.lower()
    v = v.replace(".", " ")
    v = re.sub(r"[;|]+", ",", v)
    v = re.sub(r"[^a-z0-9, ]+", " ", v)
    v = v.replace(" st ", " street ").replace(" mt ", " mount ").replace(" co ", " county ")
    return " ".join(v.split())


def _name_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _norm_filename(value: str | None) -> str:
    if not value:
        return ""
    base = os.path.splitext(value)[0].lower()
    base = re.sub(r"[^a-z0-9]+", " ", base)
    return " ".join(base.split())


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = YEAR_RE.search(value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def _parse_date(value: str | None) -> Tuple[str | None, str | None, str | None, float, bool]:
    """
    Best-effort deterministic date parser.
    Returns (normalized, precision, qualifier, confidence, ambiguous)
    """
    if not value:
        return None, None, None, 0.0, False

    raw = value.strip()
    if not raw:
        return None, None, None, 0.0, False

    amb_match = AMBIGUOUS_NUMERIC_RE.match(raw)
    if amb_match:
        first = int(amb_match.group("first"))
        second = int(amb_match.group("second"))
        if 1 <= first <= 12 and 1 <= second <= 12 and first != second:
            return None, None, None, 0.0, True

    # Range
    range_m = DATE_RANGE_RE.search(raw)
    if range_m:
        start = range_m.group("start")
        end = range_m.group("end")
        return f"{start}/{end}", "range", "between", 0.7, False

    qualifier = None
    qual_m = QUALIFIER_RE.search(raw)
    if qual_m:
        qualifier = qual_m.group(1).lower()

    # Exact date formats
    # Attempt both day-first and month-first; no heuristic disambiguation beyond trying both.
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d"), "day", qualifier, 0.95, False
        except Exception:
            continue

    # Month year e.g. Mar 1881 / 03 1881
    month_year = re.match(r"(?P<month>[A-Za-z]{3,9}|\d{1,2})[ ,/]+(?P<year>\d{3,4})", raw, re.IGNORECASE)
    if month_year:
        month = month_year.group("month")
        year = month_year.group("year")
        try:
            month_map = {
                "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
                "JUL": 7, "AUG": 8, "SEP": 9, "SEPT": 9, "OCT": 10, "NOV": 11, "DEC": 12,
            }
            if month.isdigit():
                month_num = int(month)
            else:
                month_num = month_map.get(month.upper()[:4]) or month_map.get(month.upper()[:3])
            if not month_num:
                month_num = datetime.strptime(month[:3].title(), "%b").month
            return f"{int(year):04d}-{month_num:02d}", "month", qualifier, 0.85, False
        except Exception:
            pass

    # Year-only
    y = _parse_year(raw)
    if y:
        return f"{y:04d}", "year", qualifier, 0.6 if qualifier else 0.7, False

    # Unparseable
    return None, None, qualifier, 0.0, True


def _issue_payload(**kwargs) -> str:
    return json.dumps(kwargs, default=str)


def _insert_issue(
    session: Session,
    issue_type: str,
    severity: str,
    entity_type: str,
    entity_ids: list[int],
    confidence: float,
    impact: float,
    explanation: dict,
) -> DataQualityIssue:
    issue = DataQualityIssue(
        issue_type=issue_type,
        severity=severity,
        entity_type=entity_type,
        entity_ids=json.dumps(entity_ids),
        confidence=confidence,
        impact_score=impact,
        explanation_json=_issue_payload(**explanation),
    )
    session.add(issue)
    session.flush()
    return issue


def _existing_issue_key(issue: DataQualityIssue) -> tuple[str, str, str]:
    return (issue.issue_type, issue.entity_type, issue.entity_ids)


def run_detection(session: Session, incremental: bool = False) -> dict:
    """
    Run all detectors and persist issues.
    When incremental=False, open issues are replaced.
    """
    if not incremental:
        session.execute(DataQualityIssue.__table__.delete())
        session.execute(DateNormalization.__table__.delete())

    duplicate_count = _detect_duplicates(session)
    standardization_count = _detect_standardization(session)
    place_cluster_count = _detect_places(session)
    family_duplicate_count = _detect_duplicate_families(session)
    media_duplicate_count = _detect_duplicate_media_links(session)
    media_asset_duplicate_count = _detect_duplicate_media_assets(session)
    date_count = _detect_dates(session)
    integrity_count = _detect_integrity(session)

    session.commit()
    return {
        "duplicates": duplicate_count,
        "standardization": standardization_count,
        "place_clusters": place_cluster_count,
        "family_duplicates": family_duplicate_count,
        "media_duplicates": media_duplicate_count,
        "media_asset_duplicates": media_asset_duplicate_count,
        "dates": date_count,
        "integrity": integrity_count,
    }


def _detect_duplicates(session: Session) -> int:
    people = session.execute(
        select(Person).options(
            load_only(
                Person.id,
                Person.given,
                Person.surname,
                Person.birth_date,
                Person.birth_place,
                Person.death_date,
            )
        )
    ).scalars().all()
    buckets: dict[str, list[Person]] = defaultdict(list)
    for p in people:
        key = f"{_norm_name(p.surname)}|{_parse_year(p.birth_date) or ''}"
        buckets[key].append(p)

    count = 0
    for group in buckets.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a = group[i]
                b = group[j]
                name_a = f"{_norm_name(a.given)} {_norm_name(a.surname)}"
                name_b = f"{_norm_name(b.given)} {_norm_name(b.surname)}"
                sim = _name_similarity(name_a, name_b)
                if sim < 0.68:
                    continue

                birth_a = _parse_year(a.birth_date)
                birth_b = _parse_year(b.birth_date)
                birth_delta = abs(birth_a - birth_b) if (birth_a is not None and birth_b is not None) else None
                birth_score = 0.25 if birth_delta is not None and birth_delta <= 1 else 0

                death_a = _parse_year(a.death_date)
                death_b = _parse_year(b.death_date)
                death_delta = abs(death_a - death_b) if (death_a is not None and death_b is not None) else None
                death_score = 0.1 if death_delta is not None and death_delta <= 1 else 0

                place_score = 0.15 if _norm_place(a.birth_place) and _norm_place(a.birth_place) == _norm_place(b.birth_place) else 0

                score = sim * 0.5 + birth_score + death_score + place_score
                if score < 0.55:
                    continue

                explanation = {
                    "name_similarity": round(sim, 2),
                    "birth_delta": birth_delta,
                    "death_delta": death_delta,
                    "birth_place_match": bool(place_score),
                }
                _insert_issue(
                    session,
                    "duplicate_person",
                    "warning",
                    "person",
                    [a.id, b.id],
                    confidence=round(score, 2),
                    impact=1.0,
                    explanation=explanation,
                )
                count += 1
    return count


def _detect_standardization(session: Session) -> int:
    placeholders = {"unknown", "n/a", "na", "none"}
    people = session.execute(select(Person.id, Person.given, Person.surname)).all()
    count = 0
    for pid, given, surname in people:
        fields = []
        for field_name, value in (("given", given), ("surname", surname)):
            if not value:
                continue
            if _norm_name(value) in placeholders:
                continue
            suggestion, reasons = _suggest_name_standard(value)
            if not suggestion or suggestion == value or not reasons:
                continue
            fields.append({
                "field": field_name,
                "current": value,
                "suggested": suggestion,
                "reasons": reasons,
            })

        if not fields:
            continue

        confidence = 0.9
        if any("title_case" in (f.get("reasons") or []) for f in fields):
            confidence = 0.8
        explanation = {
            "entity_label": " ".join([v for v in (given, surname) if v]) or f"Person {pid}",
            "fields": fields,
        }
        _insert_issue(
            session,
            "field_standardization",
            "info",
            "person",
            [int(pid)],
            confidence=confidence,
            impact=float(len(fields)),
            explanation=explanation,
        )
        count += 1
    return count


def _detect_places(session: Session) -> int:
    variants: dict[str, Counter] = defaultdict(Counter)
    raw_counts: Counter = Counter()
    event_rows = session.execute(select(Event.place_raw)).all()
    for (place_raw,) in event_rows:
        if place_raw:
            key = _norm_place(place_raw)
            variants[key][place_raw] += 1
            raw_counts[place_raw] += 1

    person_places = session.execute(select(Person.birth_place, Person.death_place)).all()
    for bplace, dplace in person_places:
        for pl in (bplace, dplace):
            if pl:
                key = _norm_place(pl)
                variants[key][pl] += 1
                raw_counts[pl] += 1

    count = 0
    for key, counter in variants.items():
        if len(counter) <= 1:
            continue
        total_refs = sum(counter.values())
        top = counter.most_common(1)[0][0]
        variants_list = [{"value": k, "count": v} for k, v in counter.most_common()]
        _insert_issue(
            session,
            "place_cluster",
            "info",
            "place",
            [],
            confidence=0.65,
            impact=float(total_refs),
            explanation={"canonical_suggestion": top, "variants": variants_list},
        )
        count += 1

    raw_entries = [
        {"value": value, "count": cnt, "norm": _norm_place(value)}
        for value, cnt in raw_counts.items()
        if value
    ]
    raw_entries.sort(key=lambda item: item["value"].lower())

    def pick_canonical(a: dict, b: dict) -> dict:
        if a["count"] != b["count"]:
            return a if a["count"] > b["count"] else b
        if len(a["value"]) != len(b["value"]):
            return a if len(a["value"]) > len(b["value"]) else b
        return a if a["value"].lower() <= b["value"].lower() else b

    for i in range(len(raw_entries)):
        for j in range(i + 1, len(raw_entries)):
            a = raw_entries[i]
            b = raw_entries[j]
            if not a["norm"] or not b["norm"]:
                continue
            if a["norm"] == b["norm"]:
                continue
            sim = _name_similarity(a["norm"], b["norm"])
            if sim < 0.8:
                continue
            canonical = pick_canonical(a, b)
            variants_list = sorted(
                [{"value": a["value"], "count": a["count"]}, {"value": b["value"], "count": b["count"]}],
                key=lambda item: (-item["count"], item["value"].lower()),
            )
            _insert_issue(
                session,
                "place_similarity",
                "info",
                "place",
                [],
                confidence=round(sim, 2),
                impact=float(a["count"] + b["count"]),
                explanation={
                    "canonical_suggestion": canonical["value"],
                    "variants": variants_list,
                    "similarity": round(sim, 2),
                },
            )
            count += 1
    return count


def _detect_duplicate_families(session: Session) -> int:
    people = session.execute(select(Person.id, Person.given, Person.surname)).all()
    name_map = {
        int(pid): f"{_norm_name(given)} {_norm_name(surname)}".strip()
        for pid, given, surname in people
    }
    families = session.execute(select(Family)).scalars().all()
    buckets: dict[tuple[int, int], list[Family]] = defaultdict(list)
    for fam in families:
        if not fam.husband_person_id or not fam.wife_person_id:
            continue
        key = tuple(sorted([fam.husband_person_id, fam.wife_person_id]))
        buckets[key].append(fam)

    count = 0
    for spouse_key, group in buckets.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a = group[i]
                b = group[j]
                date_a = _parse_year(a.marriage_date)
                date_b = _parse_year(b.marriage_date)
                date_score = 0.15 if date_a and date_b and date_a == date_b else 0
                place_score = 0.15 if _norm_place(a.marriage_place) and _norm_place(a.marriage_place) == _norm_place(b.marriage_place) else 0
                score = 0.7 + date_score + place_score
                if score < 0.75:
                    continue
                _insert_issue(
                    session,
                    "duplicate_family",
                    "info",
                    "family",
                    [a.id, b.id],
                    confidence=round(score, 2),
                    impact=1.0,
                    explanation={
                        "spouses": list(spouse_key),
                        "marriage_dates": [a.marriage_date, b.marriage_date],
                        "marriage_places": [a.marriage_place, b.marriage_place],
                    },
                )
                count += 1

    name_buckets: dict[tuple[str, str], list[Family]] = defaultdict(list)
    for fam in families:
        if not fam.husband_person_id or not fam.wife_person_id:
            continue
        husband_name = name_map.get(fam.husband_person_id, "").strip()
        wife_name = name_map.get(fam.wife_person_id, "").strip()
        if not husband_name or not wife_name:
            continue
        key = tuple(sorted([husband_name, wife_name]))
        name_buckets[key].append(fam)

    for key, group in name_buckets.items():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a = group[i]
                b = group[j]
                set_a = {a.husband_person_id, a.wife_person_id}
                set_b = {b.husband_person_id, b.wife_person_id}
                if set_a == set_b:
                    continue
                score = 0.6
                date_a = _parse_year(a.marriage_date)
                date_b = _parse_year(b.marriage_date)
                if date_a and date_b and date_a == date_b:
                    score += 0.15
                if _norm_place(a.marriage_place) and _norm_place(a.marriage_place) == _norm_place(b.marriage_place):
                    score += 0.15
                if score < 0.7:
                    continue
                _insert_issue(
                    session,
                    "duplicate_family_spouse_swap",
                    "info",
                    "family",
                    [a.id, b.id],
                    confidence=round(score, 2),
                    impact=1.0,
                    explanation={
                        "spouse_names": list(key),
                        "family_ids": [a.id, b.id],
                        "marriage_dates": [a.marriage_date, b.marriage_date],
                        "marriage_places": [a.marriage_place, b.marriage_place],
                    },
                )
                count += 1
    return count


def _detect_duplicate_media_links(session: Session) -> int:
    rows = session.execute(
        select(
            MediaLink.asset_id,
            MediaLink.person_id,
            MediaLink.family_id,
            func.count(MediaLink.id).label("link_count"),
        )
        .group_by(MediaLink.asset_id, MediaLink.person_id, MediaLink.family_id)
        .having(func.count(MediaLink.id) > 1)
    ).all()

    count = 0
    for asset_id, person_id, family_id, link_count in rows:
        link_ids = session.execute(
            select(MediaLink.id)
            .where(
                MediaLink.asset_id == asset_id,
                MediaLink.person_id == person_id,
                MediaLink.family_id == family_id,
            )
            .order_by(MediaLink.id)
        ).scalars().all()
        _insert_issue(
            session,
            "duplicate_media_link",
            "info",
            "media_link",
            [int(lid) for lid in link_ids],
            confidence=0.9,
            impact=float(link_count),
            explanation={
                "asset_id": asset_id,
                "person_id": person_id,
                "family_id": family_id,
                "link_ids": [int(lid) for lid in link_ids],
            },
        )
        count += 1
    return count


def _detect_duplicate_media_assets(session: Session) -> int:
    assets = session.execute(select(MediaAsset)).scalars().all()
    entries = []
    for asset in assets:
        norm = _norm_filename(asset.original_filename)
        if not norm:
            continue
        entries.append({
            "id": asset.id,
            "filename": asset.original_filename,
            "norm": norm,
            "size": asset.size_bytes,
        })

    buckets: dict[str, list[dict]] = defaultdict(list)
    for entry in entries:
        prefix = entry["norm"][:4] if entry["norm"] else ""
        buckets[prefix].append(entry)

    count = 0
    for group in buckets.values():
        if len(group) < 2:
            continue
        for i in range(len(group)):
            for j in range(i + 1, len(group)):
                a = group[i]
                b = group[j]
                sim = _name_similarity(a["norm"], b["norm"])
                if sim < 0.92:
                    continue
                size_a = a["size"]
                size_b = b["size"]
                size_score = 0.0
                if size_a and size_b:
                    delta = abs(size_a - size_b)
                    max_size = max(size_a, size_b)
                    if max_size and (delta / max_size) <= 0.02:
                        size_score = 0.1
                confidence = round(min(sim + size_score, 0.99), 2)
                _insert_issue(
                    session,
                    "duplicate_media_asset",
                    "info",
                    "media_asset",
                    [a["id"], b["id"]],
                    confidence=confidence,
                    impact=1.0,
                    explanation={
                        "asset_ids": [a["id"], b["id"]],
                        "filenames": [a["filename"], b["filename"]],
                        "sizes": [a["size"], b["size"]],
                        "similarity": round(sim, 2),
                    },
                )
                count += 1
    return count


def _detect_dates(session: Session) -> int:
    count = 0
    # Person birth/death
    persons = session.execute(select(Person.id, Person.birth_date, Person.death_date)).all()
    for pid, b, d in persons:
        for label, raw in (("birth_date", b), ("death_date", d)):
            norm, precision, qualifier, conf, ambiguous = _parse_date(raw)
            if not raw:
                continue
            dn = DateNormalization(
                entity_type="person",
                entity_id=int(pid),
                raw_value=raw,
                normalized=norm,
                precision=precision,
                qualifier=qualifier,
                confidence=conf,
                is_ambiguous=ambiguous,
            )
            session.add(dn)
            severity = "error" if ambiguous else "warning"
            _insert_issue(
                session,
                "date_normalization",
                severity,
                "person",
                [pid],
                confidence=conf,
                impact=1.0,
                explanation={
                    "field": label,
                    "raw": raw,
                    "normalized": norm,
                    "precision": precision,
                    "qualifier": qualifier,
                    "ambiguous": ambiguous,
                },
            )
            count += 1

    # Event dates
    events = session.execute(select(Event.id, Event.date_raw)).all()
    for eid, raw in events:
        if not raw:
            continue
        norm, precision, qualifier, conf, ambiguous = _parse_date(raw)
        dn = DateNormalization(
            entity_type="event",
            entity_id=int(eid),
            raw_value=raw,
            normalized=norm,
            precision=precision,
            qualifier=qualifier,
            confidence=conf,
            is_ambiguous=ambiguous,
        )
        session.add(dn)
        severity = "error" if ambiguous else "info"
        _insert_issue(
            session,
            "date_normalization",
            severity,
            "event",
            [eid],
            confidence=conf,
            impact=1.0,
            explanation={
                "raw": raw,
                "normalized": norm,
                "precision": precision,
                "qualifier": qualifier,
                "ambiguous": ambiguous,
            },
        )
        count += 1
    return count


def _detect_integrity(session: Session) -> int:
    count = 0

    # Orphaned events (no person/family)
    orphan_ids = session.execute(
        select(Event.id).where(Event.person_id.is_(None)).where(Event.family_id.is_(None))
    ).scalars().all()
    for eid in orphan_ids:
        _insert_issue(
            session,
            "orphan_event",
            "error",
            "event",
            [int(eid)],
            confidence=0.9,
            impact=1.0,
            explanation={"reason": "Event has no person or family reference"},
        )
        count += 1

    # Orphaned families (no spouses, no children)
    families = session.execute(select(Family.id, Family.husband_person_id, Family.wife_person_id)).all()
    for fid, hid, wid in families:
        child_count = session.execute(
            select(func.count(family_children.c.child_person_id)).where(family_children.c.family_id == fid)
        ).scalar_one()
        if hid is None and wid is None and child_count == 0:
            _insert_issue(
                session,
                "orphan_family",
                "warning",
                "family",
                [int(fid)],
                confidence=0.85,
                impact=0.5,
                explanation={"reason": "Family has no spouses and no children"},
            )
            count += 1

    # Impossible order: death before birth
    persons = session.execute(select(Person.id, Person.birth_date, Person.death_date)).all()
    for pid, b, d in persons:
        y_birth = _parse_year(b)
        y_death = _parse_year(d)
        if y_birth and y_death and y_death < y_birth:
            _insert_issue(
                session,
                "impossible_timeline",
                "error",
                "person",
                [int(pid)],
                confidence=0.95,
                impact=1.0,
                explanation={"birth_year": y_birth, "death_year": y_death},
            )
            count += 1

    # Parent/child timeline checks
    rel_rows = session.execute(
        select(
            relationships.c.parent_person_id,
            relationships.c.child_person_id,
            Person.birth_date,
            Person.death_date,
        )
        .join(Person, Person.id == relationships.c.parent_person_id)
    ).all()
    child_rows = {
        pid: (b, d)
        for pid, b, d in session.execute(select(Person.id, Person.birth_date, Person.death_date)).all()
    }
    for parent_id, child_id, parent_birth, parent_death in rel_rows:
        child_birth, _ = child_rows.get(child_id, (None, None))
        y_parent = _parse_year(parent_birth)
        y_child = _parse_year(child_birth)
        y_parent_death = _parse_year(parent_death)
        if y_parent is not None and y_child is not None:
            if y_parent > y_child - 12:
                _insert_issue(
                    session,
                    "parent_child_age",
                    "warning",
                    "relationship",
                    [int(parent_id), int(child_id)],
                    confidence=0.8,
                    impact=0.8,
                    explanation={"parent_birth_year": y_parent, "child_birth_year": y_child},
                )
                count += 1
        if y_parent_death is not None and y_child is not None and y_parent_death < y_child:
            _insert_issue(
                session,
                "parent_child_death",
                "warning",
                "relationship",
                [int(parent_id), int(child_id)],
                confidence=0.85,
                impact=0.8,
                explanation={"parent_death_year": y_parent_death, "child_birth_year": y_child},
            )
            count += 1

    # Marriage timeline checks
    family_rows = session.execute(
        select(
            Family.id,
            Family.husband_person_id,
            Family.wife_person_id,
            Family.marriage_date,
        )
    ).all()
    person_years = {
        pid: (_parse_year(b), _parse_year(d))
        for pid, b, d in session.execute(select(Person.id, Person.birth_date, Person.death_date)).all()
    }
    for fid, hid, wid, marriage_date in family_rows:
        y_marriage = _parse_year(marriage_date)
        if y_marriage is None:
            continue
        for spouse_id in (hid, wid):
            if not spouse_id:
                continue
            y_birth, y_death = person_years.get(spouse_id, (None, None))
            if y_birth is not None and y_marriage < y_birth + 12:
                _insert_issue(
                    session,
                    "marriage_too_early",
                    "warning",
                    "family",
                    [int(fid)],
                    confidence=0.8,
                    impact=0.7,
                    explanation={"marriage_year": y_marriage, "spouse_birth_year": y_birth, "spouse_id": spouse_id},
                )
                count += 1
            if y_death is not None and y_marriage > y_death:
                _insert_issue(
                    session,
                    "marriage_after_death",
                    "warning",
                    "family",
                    [int(fid)],
                    confidence=0.85,
                    impact=0.7,
                    explanation={"marriage_year": y_marriage, "spouse_death_year": y_death, "spouse_id": spouse_id},
                )
                count += 1

    # Placeholder names
    placeholders = {"unknown", "n/a", "na", "none"}
    persons = session.execute(select(Person.id, Person.given, Person.surname)).all()
    for pid, given, surname in persons:
        if (_norm_name(given) in placeholders) or (_norm_name(surname) in placeholders):
            _insert_issue(
                session,
                "placeholder_name",
                "warning",
                "person",
                [int(pid)],
                confidence=0.8,
                impact=0.2,
                explanation={"given": given, "surname": surname},
            )
            count += 1

    return count


def _clean_date_record(raw: str | None, label: str) -> dict:
    norm, precision, qualifier, conf, ambiguous = _parse_date(raw)
    return {
        "field": label,
        "type": "date",
        "original": raw,
        "normalized": norm,
        "precision": precision,
        "qualifier": qualifier,
        "confidence": conf,
        "ambiguous": ambiguous,
    }


def _clean_place_record(raw: str | None, label: str) -> dict:
    cleaned = _norm_place(raw) if raw else None
    return {
        "field": label,
        "type": "place",
        "original": raw,
        "normalized": cleaned or None,
        "confidence": PLACE_CLEAN_CONFIDENCE if cleaned else 0.0,
        "ambiguous": False,
    }


def clean_person_fields(session: Session, person_id: int, apply: bool = False, applied_by: str | None = None) -> dict:
    """
    Preview or apply transparent cleaning of a person's date/place fields.
    Returns a payload describing each field and whether changes were applied.
    """
    person = session.get(Person, person_id)
    if not person:
        raise ValueError("Person not found")

    records: list[dict[str, Any]] = []
    for label in ("birth_date", "death_date"):
        records.append(_clean_date_record(getattr(person, label), label))
    for label in ("birth_place", "death_place"):
        records.append(_clean_place_record(getattr(person, label), label))

    applied_any = False
    if apply:
        undo_payload: dict[str, Any] = {}
        for rec in records:
            if rec["ambiguous"] or not rec["normalized"]:
                continue
            current = getattr(person, rec["field"])
            if current == rec["normalized"]:
                continue
            undo_payload[rec["field"]] = current
            setattr(person, rec["field"], rec["normalized"])
            if rec["type"] == "date":
                dn = DateNormalization(
                    entity_type="person",
                    entity_id=person_id,
                    raw_value=rec["original"] or "",
                    normalized=rec["normalized"],
                    precision=rec.get("precision"),
                    qualifier=rec.get("qualifier"),
                    confidence=rec.get("confidence"),
                    is_ambiguous=bool(rec.get("ambiguous")),
                )
                session.add(dn)
        if undo_payload:
            person.updated_at = datetime.utcnow()
            session.flush()
            log_action(
                session,
                "person_clean",
                payload={"person_id": person_id, "applied_fields": list(undo_payload.keys()), "preview": records},
                undo={"person_id": person_id, "values": undo_payload},
                applied_by=applied_by,
            )
            session.commit()
            applied_any = True

    return {"person_id": person_id, "fields": records, "applied": applied_any}


def build_summary(session: Session) -> dict:
    total_dates = session.execute(select(func.count(DateNormalization.id))).scalar_one()
    normalized_dates = session.execute(
        select(func.count(DateNormalization.id)).where(DateNormalization.normalized.is_not(None))
    ).scalar_one()
    unresolved_duplicates = session.execute(
        select(func.count(DataQualityIssue.id)).where(
            DataQualityIssue.issue_type.in_(
                [
                    "duplicate_person",
                    "duplicate_family",
                    "duplicate_family_spouse_swap",
                    "duplicate_media_link",
                    "duplicate_media_asset",
                ]
            ),
            DataQualityIssue.status == "open",
        )
    ).scalar_one()
    place_clusters = session.execute(
        select(func.count(DataQualityIssue.id)).where(
            DataQualityIssue.issue_type.in_(["place_cluster", "place_similarity"]),
            DataQualityIssue.status == "open",
        )
    ).scalar_one()
    integrity_warnings = session.execute(
        select(func.count(DataQualityIssue.id)).where(
            DataQualityIssue.issue_type.in_(
                [
                    "orphan_event",
                    "orphan_family",
                    "impossible_timeline",
                    "parent_child_age",
                    "parent_child_death",
                    "marriage_too_early",
                    "marriage_after_death",
                    "placeholder_name",
                ]
            ),
            DataQualityIssue.status == "open",
        )
    ).scalar_one()
    standardization_suggestions = session.execute(
        select(func.count(DataQualityIssue.id)).where(
            DataQualityIssue.issue_type == "field_standardization",
            DataQualityIssue.status == "open",
        )
    ).scalar_one()

    date_pct = 0.0
    if total_dates:
        date_pct = round((normalized_dates / total_dates) * 100, 1)

    score_components = [
        0.4 * (date_pct / 100.0),
        0.3 * (1 / (1 + unresolved_duplicates)),
        0.2 * (1 / (1 + place_clusters)),
        0.1 * (1 / (1 + integrity_warnings)),
    ]
    dq_score = round(sum(score_components) * 100, 1)

    return {
        "data_quality_score": dq_score,
        "standardized_dates_pct": date_pct,
        "unresolved_duplicates": int(unresolved_duplicates),
        "place_clusters": int(place_clusters),
        "integrity_warnings": int(integrity_warnings),
        "standardization_suggestions": int(standardization_suggestions),
    }


def log_action(session: Session, action_type: str, payload: dict, undo: dict | None, applied_by: str | None) -> DataQualityActionLog:
    entry = DataQualityActionLog(
        action_type=action_type,
        payload_json=json.dumps(payload, default=str),
        undo_payload_json=json.dumps(undo, default=str) if undo else None,
        applied_by=applied_by,
    )
    session.add(entry)
    session.flush()
    return entry
