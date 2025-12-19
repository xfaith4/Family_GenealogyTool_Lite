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
from collections import defaultdict, Counter
from difflib import SequenceMatcher
from typing import Iterable, List, Tuple, Dict, Any

from sqlalchemy import select, func, and_, or_
from sqlalchemy.orm import Session

from .models import (
    Person,
    Family,
    Event,
    Place,
    PlaceVariant,
    DataQualityIssue,
    DataQualityActionLog,
    DateNormalization,
    relationships,
    family_children,
)


YEAR_RE = re.compile(r"(1[5-9]\d{2}|20\d{2})")
DATE_RANGE_RE = re.compile(r"\bBET\s+(?P<start>\d{3,4})\s+AND\s+(?P<end>\d{3,4})", re.IGNORECASE)
QUALIFIER_RE = re.compile(r"\b(ABT|ABOUT|BEF|AFT|EST|CALC|CIRCA|CA\.?)\b", re.IGNORECASE)


def _norm_name(value: str | None) -> str:
    return " ".join((value or "").lower().strip().split())


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
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d"), "day", qualifier, 0.95, False
        except Exception:
            continue

    # Month year e.g. Mar 1881 / 03 1881
    month_year = re.match(r"(?P<month>[A-Za-z]{3,9}|\d{1,2})[ ,/]+(?P<year>\d{3,4})", raw)
    if month_year:
        month = month_year.group("month")
        year = month_year.group("year")
        try:
            month_num = int(month) if month.isdigit() else datetime.strptime(month[:3], "%b").month
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
        session.query(DataQualityIssue).delete()
        session.query(DateNormalization).delete()

    duplicate_count = _detect_duplicates(session)
    place_cluster_count = _detect_places(session)
    date_count = _detect_dates(session)
    integrity_count = _detect_integrity(session)

    session.commit()
    return {
        "duplicates": duplicate_count,
        "place_clusters": place_cluster_count,
        "dates": date_count,
        "integrity": integrity_count,
    }


def _detect_duplicates(session: Session) -> int:
    people = session.execute(select(Person)).scalars().all()
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
                birth_delta = abs(birth_a - birth_b) if (birth_a and birth_b) else None
                birth_score = 0.25 if birth_delta is not None and birth_delta <= 1 else 0

                death_a = _parse_year(a.death_date)
                death_b = _parse_year(b.death_date)
                death_delta = abs(death_a - death_b) if (death_a and death_b) else None
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


def _detect_places(session: Session) -> int:
    variants: dict[str, Counter] = defaultdict(Counter)
    event_rows = session.execute(select(Event.place_raw)).all()
    for (place_raw,) in event_rows:
        if place_raw:
            key = _norm_place(place_raw)
            variants[key][place_raw] += 1

    person_places = session.execute(select(Person.birth_place, Person.death_place)).all()
    for bplace, dplace in person_places:
        for pl in (bplace, dplace):
            if pl:
                key = _norm_place(pl)
                variants[key][pl] += 1

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


def build_summary(session: Session) -> dict:
    total_dates = session.execute(select(func.count(DateNormalization.id))).scalar_one()
    normalized_dates = session.execute(
        select(func.count(DateNormalization.id)).where(DateNormalization.normalized.is_not(None))
    ).scalar_one()
    unresolved_duplicates = session.execute(
        select(func.count(DataQualityIssue.id)).where(
            DataQualityIssue.issue_type == "duplicate_person", DataQualityIssue.status == "open"
        )
    ).scalar_one()
    place_clusters = session.execute(
        select(func.count(DataQualityIssue.id)).where(
            DataQualityIssue.issue_type == "place_cluster", DataQualityIssue.status == "open"
        )
    ).scalar_one()
    integrity_warnings = session.execute(
        select(func.count(DataQualityIssue.id)).where(
            DataQualityIssue.issue_type.in_(["orphan_event", "impossible_timeline"]), DataQualityIssue.status == "open"
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
