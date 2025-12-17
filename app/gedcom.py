from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import re

@dataclass
class Indi:
    xref: str
    given: str = ""
    surname: str = ""
    sex: str = ""
    birth_date: str = ""
    birth_place: str = ""
    death_date: str = ""
    death_place: str = ""
    notes: List[str] = field(default_factory=list)

@dataclass
class Fam:
    xref: str
    husb: Optional[str] = None
    wife: Optional[str] = None
    chil: List[str] = field(default_factory=list)
    marriage_date: str = ""
    marriage_place: str = ""
    notes: List[str] = field(default_factory=list)

_line_re = re.compile(r"^(?P<lvl>\d+)\s+(?:(?P<xref>@[^@]+@)\s+)?(?P<tag>[A-Z0-9_]+)(?:\s+(?P<val>.*))?$")

def parse_gedcom(text: str) -> Tuple[Dict[str, Indi], Dict[str, Fam]]:
    indis: Dict[str, Indi] = {}
    fams: Dict[str, Fam] = {}

    lines = [ln.rstrip("\n\r") for ln in text.splitlines() if ln.strip() != ""]
    current_type = None
    current_xref = None
    current_event = None

    for ln in lines:
        m = _line_re.match(ln)
        if not m:
            continue

        lvl = int(m.group("lvl"))
        xref = m.group("xref")
        tag = m.group("tag")
        val = (m.group("val") or "").strip()

        if lvl == 0:
            current_event = None
            if xref and tag in ("INDI", "FAM"):
                current_type = tag
                current_xref = xref
                if tag == "INDI":
                    indis.setdefault(xref, Indi(xref=xref))
                else:
                    fams.setdefault(xref, Fam(xref=xref))
            else:
                current_type = None
                current_xref = None
            continue

        if current_type == "INDI" and current_xref in indis:
            indi = indis[current_xref]
            if tag == "NAME":
                if "/" in val:
                    parts = val.split("/")
                    indi.given = parts[0].strip()
                    indi.surname = parts[1].strip()
                else:
                    indi.given = val.strip()
            elif tag == "GIVN" and val:
                indi.given = val
            elif tag == "SURN" and val:
                indi.surname = val
            elif tag == "SEX":
                indi.sex = val
            elif tag in ("BIRT", "DEAT"):
                current_event = tag
            elif tag == "DATE" and current_event == "BIRT":
                indi.birth_date = val
            elif tag == "PLAC" and current_event == "BIRT":
                indi.birth_place = val
            elif tag == "DATE" and current_event == "DEAT":
                indi.death_date = val
            elif tag == "PLAC" and current_event == "DEAT":
                indi.death_place = val
            elif tag == "NOTE" and val:
                indi.notes.append(val)

        elif current_type == "FAM" and current_xref in fams:
            fam = fams[current_xref]
            if tag == "HUSB" and val:
                fam.husb = val
            elif tag == "WIFE" and val:
                fam.wife = val
            elif tag == "CHIL" and val:
                fam.chil.append(val)
            elif tag == "MARR":
                current_event = tag
            elif tag == "DATE" and current_event == "MARR":
                fam.marriage_date = val
            elif tag == "PLAC" and current_event == "MARR":
                fam.marriage_place = val
            elif tag == "NOTE" and val:
                fam.notes.append(val)

    for indi in indis.values():
        indi.given = (indi.given or "").strip()
        indi.surname = (indi.surname or "").strip()

    return indis, fams

def to_summary(indis: Dict[str, Indi], fams: Dict[str, Fam]) -> dict:
    return {
        "people": len(indis),
        "families": len(fams),
    }
