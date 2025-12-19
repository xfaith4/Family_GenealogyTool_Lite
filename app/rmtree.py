from __future__ import annotations

import re
import sqlite3
import hashlib
from pathlib import Path
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Tuple


@dataclass
class TableData:
    columns: List[str]
    rows: List[Tuple[Any, ...]]


def parse_rmtree_sql(text: str) -> Dict[str, TableData]:
    """
    Parse a SQL-like RMTree export and return normalized table data.
    """
    cleaned = _strip_comments(text)
    tables: Dict[str, TableData] = {}
    with sqlite3.connect(":memory:") as conn:
        cursor = conn.cursor()
        for stmt in _split_statements(cleaned):
            parsed = _parse_insert_statement(stmt, cursor)
            if not parsed:
                continue
            table_name, columns, rows = parsed
            if not columns or not rows:
                continue
            entry = tables.setdefault(table_name, TableData(columns=list(columns), rows=[]))
            entry.rows.extend(rows)
    return tables


def load_tables_from_sqlite(db_path: str, fetch_size: int = 500) -> Dict[str, TableData]:
    """
    Read tables from a RootsMagic SQLite database into the TableData structure
    used by the existing collectors. Tables and columns are normalized to
    lowercase with underscores to make schema differences tolerant.
    """
    tables: Dict[str, TableData] = {}
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        table_names = [
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        ]
        for raw_name in table_names:
            try:
                columns_info = conn.execute(f'PRAGMA table_info("{raw_name}")').fetchall()
                columns = [_normalize_identifier(col["name"]) for col in columns_info]
                if not columns:
                    continue
                cursor = conn.execute(f'SELECT * FROM "{raw_name}"')
                normalized_name = _normalize_identifier(raw_name)
                table_data = tables.setdefault(normalized_name, TableData(columns=columns, rows=[]))
                while True:
                    chunk = cursor.fetchmany(fetch_size)
                    if not chunk:
                        break
                    for row in chunk:
                        table_data.rows.append(tuple(row[col["name"]] for col in columns_info))
            except sqlite3.DatabaseError:
                # Skip tables with unsupported collations or other issues
                continue
    return tables


def sqlite_schema_fingerprint(db_path: str) -> tuple[str, list[tuple[Any, ...]]]:
    """
    Compute a deterministic fingerprint of sqlite_master to help debug schema differences.
    Returns the fingerprint and the raw rows.
    """
    uri = f"file:{Path(db_path).as_posix()}?mode=ro"
    rows: list[tuple[Any, ...]] = []
    with sqlite3.connect(uri, uri=True) as conn:
        cursor = conn.execute(
            "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE type IN ('table','index','view') ORDER BY type, name"
        )
        rows = cursor.fetchall()
    joined = "|".join(f"{r[0]}:{r[1]}:{r[2]}:{r[3] or ''}" for r in rows)
    fingerprint = hashlib.sha256(joined.encode("utf-8")).hexdigest()
    return fingerprint, rows


def _strip_comments(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = re.sub(r"/\*.*?\*/", " ", text, flags=re.S)
    text = re.sub(r"--.*", "", text)
    return text


def _split_statements(text: str) -> List[str]:
    statements = []
    current: List[str] = []
    in_quote = False
    quote_char = ""
    depth = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if in_quote:
            if ch == quote_char:
                if i + 1 < len(text) and text[i + 1] == quote_char:
                    i += 1
                else:
                    in_quote = False
            current.append(ch)
            i += 1
            continue
        if ch in ("'", '"'):
            in_quote = True
            quote_char = ch
            current.append(ch)
            i += 1
            continue
        if ch == ";":
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
            depth = 0
            i += 1
            continue
        if ch == "(":
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
        current.append(ch)
        i += 1
    remainder = "".join(current).strip()
    if remainder:
        statements.append(remainder)
    return statements


def _parse_insert_statement(stmt: str, cursor: sqlite3.Cursor) -> Tuple[str, List[str], List[Tuple[Any, ...]]] | None:
    m = re.match(
        r"INSERT\s+INTO\s+(?P<table>[^\s(]+)\s*(?:\((?P<cols>[^)]+)\))?\s+VALUES\s+(?P<values>.+)$",
        stmt,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None
    table_name = _normalize_identifier(m.group("table"))
    cols = m.group("cols")
    if not cols:
        return None
    columns = [_normalize_identifier(col) for col in cols.split(",") if col.strip()]
    values_part = m.group("values").strip()
    tuple_strings = _extract_value_tuples(values_part)
    if not tuple_strings:
        return None
    rows = _evaluate_value_tuples(tuple_strings, cursor)
    return table_name, columns, rows


def _normalize_identifier(value: str) -> str:
    value = value.strip()
    if "." in value:
        value = value.split(".")[-1]
    if value.startswith("[") and value.endswith("]"):
        value = value[1:-1]
    if value.startswith(("'", '"', "`")) and value.endswith(("'", '"', "`")):
        value = value[1:-1]
    value = value.strip()
    value = re.sub(r"\s+", "_", value)
    return value.lower()


def _extract_value_tuples(values_part: str) -> List[str]:
    tuples: List[str] = []
    start = None
    depth = 0
    in_quote = False
    quote_char = ""

    i = 0
    while i < len(values_part):
        ch = values_part[i]
        if in_quote:
            if ch == quote_char:
                if i + 1 < len(values_part) and values_part[i + 1] == quote_char:
                    i += 1
                else:
                    in_quote = False
            i += 1
            continue
        if ch in ("'", '"'):
            in_quote = True
            quote_char = ch
            i += 1
            continue
        if ch == "(":
            if depth == 0:
                start = i
            depth += 1
        elif ch == ")" and depth > 0:
            depth -= 1
            if depth == 0 and start is not None:
                tuples.append(values_part[start:i + 1])
                start = None
        i += 1
    return tuples


def _evaluate_value_tuples(tuple_strings: Iterable[str], cursor: sqlite3.Cursor) -> List[Tuple[Any, ...]]:
    rows: List[Tuple[Any, ...]] = []
    for chunk in tuple_strings:
        content = chunk.strip()
        if content.startswith("(") and content.endswith(")"):
            content = content[1:-1]
        content = content.strip()
        if not content:
            continue
        try:
            cursor.execute(f"SELECT {content}")
        except sqlite3.DatabaseError:
            continue
        row = cursor.fetchone()
        if row is not None:
            rows.append(row)
    return rows


def collect_person_records(tables: Dict[str, TableData]) -> List[Dict[str, Any]]:
    candidates = _filter_tables(
        tables,
        name_keywords=("individual", "person", "indi"),
        column_keywords=("given", "surname", "gender", "sex", "birth", "death"),
    )
    records: List[Dict[str, Any]] = []
    for data in candidates:
        records.extend(_extract_person_rows_from_table(data))
    return records


def collect_relationship_records(tables: Dict[str, TableData]) -> List[Dict[str, Any]]:
    candidates = _filter_tables(
        tables,
        name_keywords=("relationship", "parent", "child"),
        column_keywords=("parent", "child"),
    )
    records: List[Dict[str, Any]] = []
    for data in candidates:
        records.extend(_extract_relationship_rows_from_table(data))
    return records


def collect_media_locations(tables: Dict[str, TableData]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for data in tables.values():
        if not _table_has_media_path(data.columns):
            continue
        media_rows = _extract_media_location_rows(data)
        records.extend(media_rows)
    return records


def collect_media_associations(tables: Dict[str, TableData]) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for data in tables.values():
        if not _table_has_media_reference(data.columns):
            continue
        assoc_rows = _extract_media_association_rows(data)
        records.extend(assoc_rows)
    return records


def _filter_tables(
    tables: Dict[str, TableData],
    name_keywords: Tuple[str, ...],
    column_keywords: Tuple[str, ...],
) -> List[TableData]:
    matches: List[TableData] = []
    for name, data in tables.items():
        if any(kw in name for kw in name_keywords):
            matches.append(data)
            continue
        if any(any(kw in column for kw in column_keywords) for column in data.columns):
            matches.append(data)
    return matches


def _find_column(columns: List[str], keywords: Iterable[str], exclude: Iterable[str] = ()) -> str | None:
    exclude = set(exclude)
    for keyword in keywords:
        for column in columns:
            if keyword in column and not any(ex in column for ex in exclude):
                return column
    return None


def _extract_person_rows_from_table(data: TableData) -> List[Dict[str, Any]]:
    columns = data.columns
    id_col = _find_column(columns, ("individualid", "personid", "id"), exclude=("media", "relation", "parent", "child"))
    if not id_col:
        return []
    firstname_col = _find_column(columns, ("given", "givn", "first", "fname", "name"))
    lastname_col = _find_column(columns, ("surname", "last", "lname"))
    sex_col = _find_column(columns, ("sex", "gender"))
    birth_date_col = _find_column(columns, ("birthdate", "birth_date", "dob", "born"), exclude=("place",))
    birth_place_col = _find_column(columns, ("birthplace", "birth_place", "birthlocation", "birth_loc"))
    death_date_col = _find_column(columns, ("deathdate", "death_date", "dod", "died"), exclude=("place",))
    death_place_col = _find_column(columns, ("deathplace", "death_place", "deathlocation"))
    xref_col = _find_column(columns, ("xref", "xrefid"))
    note_col = _find_column(columns, ("notes", "note", "description"), exclude=("media",))

    def normalize(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    records: List[Dict[str, Any]] = []
    for row in data.rows:
        row_dict = dict(zip(columns, row))
        source_id = row_dict.get(id_col)
        if source_id is None:
            continue
        person_data: Dict[str, Any] = {
            "source_id": source_id,
            "xref": normalize(row_dict.get(xref_col)) or f"rmtree:{source_id}",
            "given": normalize(row_dict.get(firstname_col)),
            "surname": normalize(row_dict.get(lastname_col)),
            "sex": normalize(row_dict.get(sex_col)),
            "birth_date": normalize(row_dict.get(birth_date_col)),
            "birth_place": normalize(row_dict.get(birth_place_col)),
            "death_date": normalize(row_dict.get(death_date_col)),
            "death_place": normalize(row_dict.get(death_place_col)),
        }
        if note_col:
            note_value = normalize(row_dict.get(note_col))
            if note_value:
                person_data["notes"] = [note_value]
        records.append(person_data)
    return records


def _extract_relationship_rows_from_table(data: TableData) -> List[Dict[str, Any]]:
    columns = data.columns
    child_col = _find_column(columns, ("childid", "child", "personid"))
    if not child_col:
        return []
    potential_parents = [
        col for col in columns if any(kw in col for kw in ("parent", "father", "mother"))
    ]
    if not potential_parents:
        return []
    records: List[Dict[str, Any]] = []
    for row in data.rows:
        row_dict = dict(zip(columns, row))
        child_id = row_dict.get(child_col)
        if child_id is None:
            continue
        for parent_col in potential_parents:
            parent_id = row_dict.get(parent_col)
            if parent_id is None:
                continue
            records.append({"parent_id": parent_id, "child_id": child_id})
    return records


def _table_has_media_path(columns: List[str]) -> bool:
    has_media = any("media" in col for col in columns)
    has_path = any("path" in col or "file" in col for col in columns)
    return has_media and has_path


def _table_has_media_reference(columns: List[str]) -> bool:
    has_media = any("media" in col for col in columns)
    has_target = any(
        any(kw in col for kw in ("person", "family", "owner", "object"))
        for col in columns
    )
    return has_media and has_target


def _extract_media_location_rows(data: TableData) -> List[Dict[str, Any]]:
    columns = data.columns
    media_id_col = _find_column(columns, ("mediaid", "media_id", "id"), exclude=("person", "family"))
    path_col = _find_column(columns, ("path", "filepath", "filename", "location"))
    name_col = _find_column(columns, ("name", "title"))
    desc_col = _find_column(columns, ("description", "comment", "note"))
    if not media_id_col or not path_col:
        return []
    records: List[Dict[str, Any]] = []
    for row in data.rows:
        row_dict = dict(zip(columns, row))
        media_id = row_dict.get(media_id_col)
        path = row_dict.get(path_col)
        if media_id is None or path is None:
            continue
        record: Dict[str, Any] = {
            "media_id": media_id,
            "path": str(path).strip(),
            "original_name": str(row_dict.get(name_col)).strip() if name_col and row_dict.get(name_col) else None,
            "description": str(row_dict.get(desc_col)).strip() if desc_col and row_dict.get(desc_col) else None,
        }
        records.append(record)
    return records


def _extract_media_association_rows(data: TableData) -> List[Dict[str, Any]]:
    columns = data.columns
    media_col = _find_column(columns, ("mediaid", "media_id", "media"))
    owner_col = _find_column(columns, ("ownerid", "objectid", "personid", "familyid"), exclude=("media",))
    owner_type_col = _find_column(columns, ("ownertype", "objecttype", "type"), exclude=("mediatype",))
    if not media_col or not owner_col:
        return []
    records: List[Dict[str, Any]] = []
    for row in data.rows:
        row_dict = dict(zip(columns, row))
        media_id = row_dict.get(media_col)
        if media_id is None:
            continue
        owner_id = row_dict.get(owner_col)
        owner_type = None
        if owner_type_col:
            type_value = row_dict.get(owner_type_col)
            if isinstance(type_value, str):
                normalized = type_value.lower()
                if "person" in normalized:
                    owner_type = "person"
                elif "family" in normalized:
                    owner_type = "family"
            elif isinstance(type_value, int):
                owner_type = "person"
        if owner_id is None:
            continue
        if owner_type is None:
            if "person" in owner_col:
                owner_type = "person"
            elif "family" in owner_col:
                owner_type = "family"
        if owner_type not in ("person", "family"):
            continue
        records.append({"media_id": media_id, "owner_type": owner_type, "owner_id": owner_id})
    return records
