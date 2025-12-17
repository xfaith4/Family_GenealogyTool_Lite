"""
Person deduplication service.
Identifies potential duplicate person records based on name and date similarity.
"""
from __future__ import annotations
from typing import List, Dict
from rapidfuzz import fuzz
import sqlite3

def generate_duplicate_candidates(db: sqlite3.Connection, threshold: float = 0.75) -> int:
    """
    Generate duplicate person candidate suggestions.
    
    Args:
        db: Database connection
        threshold: Minimum similarity score (0.0-1.0) to consider as duplicate
    
    Returns:
        Number of candidate pairs generated
    """
    # Get all persons
    persons = db.execute(
        "SELECT id, given, surname, birth_date, birth_place FROM persons ORDER BY id"
    ).fetchall()
    
    if len(persons) < 2:
        return 0
    
    candidates_added = 0
    
    # Compare each pair
    for i in range(len(persons)):
        for j in range(i + 1, len(persons)):
            p1 = persons[i]
            p2 = persons[j]
            
            # Calculate similarity
            score = calculate_person_similarity(p1, p2)
            
            if score >= threshold:
                # Check if already exists
                existing = db.execute(
                    """
                    SELECT id FROM duplicate_candidates 
                    WHERE (person1_id = ? AND person2_id = ?) 
                       OR (person1_id = ? AND person2_id = ?)
                    """,
                    (p1[0], p2[0], p2[0], p1[0])
                ).fetchone()
                
                if not existing:
                    db.execute(
                        """
                        INSERT INTO duplicate_candidates (person1_id, person2_id, similarity_score, status)
                        VALUES (?, ?, ?, 'pending')
                        """,
                        (p1[0], p2[0], score)
                    )
                    candidates_added += 1
    
    db.commit()
    return candidates_added

def calculate_person_similarity(p1: tuple, p2: tuple) -> float:
    """
    Calculate similarity score between two person records.
    
    Args:
        p1, p2: Person tuples (id, given, surname, birth_date, birth_place)
    
    Returns:
        Similarity score from 0.0 to 1.0
    """
    # Extract fields
    _, given1, surname1, birth_date1, birth_place1 = p1
    _, given2, surname2, birth_date2, birth_place2 = p2
    
    # Name similarity (weighted heavily)
    given1 = (given1 or "").strip().lower()
    given2 = (given2 or "").strip().lower()
    surname1 = (surname1 or "").strip().lower()
    surname2 = (surname2 or "").strip().lower()
    
    if not given1 and not surname1:
        return 0.0
    if not given2 and not surname2:
        return 0.0
    
    # Calculate name scores
    given_score = fuzz.ratio(given1, given2) / 100.0 if given1 and given2 else 0.0
    surname_score = fuzz.ratio(surname1, surname2) / 100.0 if surname1 and surname2 else 0.0
    
    # Average name score (surname weighted more)
    name_score = (given_score * 0.4 + surname_score * 0.6) if surname1 and surname2 else given_score
    
    # Birth date similarity
    date_score = 0.0
    birth_date1 = (birth_date1 or "").strip()
    birth_date2 = (birth_date2 or "").strip()
    if birth_date1 and birth_date2:
        if birth_date1 == birth_date2:
            date_score = 1.0
        else:
            # Partial match on year
            year1 = extract_year(birth_date1)
            year2 = extract_year(birth_date2)
            if year1 and year2 and year1 == year2:
                date_score = 0.5
    
    # Birth place similarity
    place_score = 0.0
    birth_place1 = (birth_place1 or "").strip().lower()
    birth_place2 = (birth_place2 or "").strip().lower()
    if birth_place1 and birth_place2:
        place_score = fuzz.ratio(birth_place1, birth_place2) / 100.0
    
    # Weighted average: name is most important
    # Name: 70%, Date: 20%, Place: 10%
    if birth_date1 and birth_date2 and birth_place1 and birth_place2:
        return name_score * 0.7 + date_score * 0.2 + place_score * 0.1
    elif birth_date1 and birth_date2:
        return name_score * 0.8 + date_score * 0.2
    elif birth_place1 and birth_place2:
        return name_score * 0.9 + place_score * 0.1
    else:
        return name_score

def extract_year(date_str: str) -> str | None:
    """Extract year from date string."""
    import re
    # Look for 4-digit year
    m = re.search(r'\b(\d{4})\b', date_str)
    return m.group(1) if m else None

def get_duplicate_candidates(db: sqlite3.Connection, limit: int = 100) -> List[Dict]:
    """
    Get list of duplicate candidates pending review.
    
    Returns:
        List of dicts with candidate info
    """
    rows = db.execute(
        """
        SELECT dc.id, dc.person1_id, dc.person2_id, dc.similarity_score, dc.created_at,
               p1.given as p1_given, p1.surname as p1_surname, p1.birth_date as p1_birth_date,
               p2.given as p2_given, p2.surname as p2_surname, p2.birth_date as p2_birth_date
        FROM duplicate_candidates dc
        JOIN persons p1 ON p1.id = dc.person1_id
        JOIN persons p2 ON p2.id = dc.person2_id
        WHERE dc.status = 'pending'
        ORDER BY dc.similarity_score DESC
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    
    return [
        {
            "id": r[0],
            "person1_id": r[1],
            "person2_id": r[2],
            "similarity_score": r[3],
            "created_at": r[4],
            "person1": {
                "given": r[5],
                "surname": r[6],
                "birth_date": r[7],
            },
            "person2": {
                "given": r[8],
                "surname": r[9],
                "birth_date": r[10],
            },
        }
        for r in rows
    ]

def mark_duplicate_reviewed(db: sqlite3.Connection, candidate_id: int, status: str) -> bool:
    """
    Mark a duplicate candidate as reviewed.
    
    Args:
        db: Database connection
        candidate_id: ID of the duplicate candidate
        status: 'ignored' or 'merged' (merging not implemented in this phase)
    
    Returns:
        True if marked successfully
    """
    if status not in ['ignored', 'merged']:
        return False
    
    result = db.execute(
        "UPDATE duplicate_candidates SET status = ?, reviewed_at = datetime('now') WHERE id = ?",
        (status, candidate_id)
    )
    
    db.commit()
    return result.rowcount > 0
