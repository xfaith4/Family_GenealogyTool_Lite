"""
Date parsing service for GEDCOM dates.
Converts various GEDCOM date formats to canonical yyyy-MM-dd format.
"""
from __future__ import annotations
import re
from typing import Tuple, Optional
from datetime import datetime

# GEDCOM date patterns
MONTH_NAMES = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12
}

def parse_date(raw_date: str) -> Tuple[Optional[str], str]:
    """
    Parse a GEDCOM date string to canonical yyyy-MM-dd format.
    
    Returns:
        (canonical_date, confidence) where:
        - canonical_date: yyyy-MM-dd string or None if unparseable
        - confidence: 'exact', 'partial', 'ambiguous', or 'unparseable'
    
    Examples:
        "1 JAN 1900" -> ("1900-01-01", "exact")
        "JAN 1900" -> ("1900-01-01", "partial")  # day unknown, use 01
        "1900" -> ("1900-01-01", "partial")  # month/day unknown
        "ABT 1900" -> ("1900-01-01", "ambiguous")
        "BEF 1900" -> (None, "ambiguous")
        "invalid" -> (None, "unparseable")
    """
    if not raw_date or not raw_date.strip():
        return None, "unparseable"
    
    date_str = raw_date.strip().upper()
    
    # Remove common GEDCOM qualifiers and mark as ambiguous
    qualifiers = ["ABT", "ABOUT", "CAL", "CALCULATED", "EST", "ESTIMATED"]
    is_ambiguous = False
    for qualifier in qualifiers:
        if date_str.startswith(qualifier + " "):
            date_str = date_str[len(qualifier)+1:].strip()
            is_ambiguous = True
            break
    
    # Can't parse BEF/AFT/BET ranges to exact date
    if any(date_str.startswith(prefix) for prefix in ["BEF", "AFT", "BEFORE", "AFTER", "BET", "BETWEEN"]):
        return None, "ambiguous"
    
    # Pattern: DD MMM YYYY (e.g., "1 JAN 1900")
    m = re.match(r"^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$", date_str)
    if m:
        day, month_abbr, year = m.groups()
        month = MONTH_NAMES.get(month_abbr)
        if month:
            try:
                # Validate date
                datetime(int(year), month, int(day))
                canonical = f"{year}-{month:02d}-{int(day):02d}"
                return canonical, "ambiguous" if is_ambiguous else "exact"
            except ValueError:
                pass
    
    # Pattern: MMM YYYY (e.g., "JAN 1900")
    m = re.match(r"^([A-Z]{3})\s+(\d{4})$", date_str)
    if m:
        month_abbr, year = m.groups()
        month = MONTH_NAMES.get(month_abbr)
        if month:
            canonical = f"{year}-{month:02d}-01"
            return canonical, "ambiguous" if is_ambiguous else "partial"
    
    # Pattern: YYYY only (e.g., "1900")
    m = re.match(r"^(\d{4})$", date_str)
    if m:
        year = m.group(1)
        canonical = f"{year}-01-01"
        return canonical, "ambiguous" if is_ambiguous else "partial"
    
    # Pattern: DD/MM/YYYY or MM/DD/YYYY or YYYY-MM-DD
    # Try ISO format first
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", date_str)
    if m:
        year, month, day = m.groups()
        try:
            datetime(int(year), int(month), int(day))
            canonical = f"{year}-{int(month):02d}-{int(day):02d}"
            return canonical, "ambiguous" if is_ambiguous else "exact"
        except ValueError:
            pass
    
    # Try DD/MM/YYYY (common in Europe)
    m = re.match(r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})$", date_str)
    if m:
        part1, part2, year = m.groups()
        # Disambiguate DD/MM vs MM/DD
        # If part1 > 12, must be DD/MM. If part2 > 12, must be MM/DD.
        # Otherwise ambiguous, default to DD/MM
        if int(part1) > 12:
            day, month = int(part1), int(part2)
        elif int(part2) > 12:
            month, day = int(part1), int(part2)
        else:
            # Ambiguous case, assume DD/MM
            day, month = int(part1), int(part2)
        try:
            datetime(int(year), month, day)
            canonical = f"{year}-{month:02d}-{day:02d}"
            # Mark as ambiguous since format is unclear
            return canonical, "ambiguous"
        except ValueError:
            pass
    
    return None, "unparseable"
