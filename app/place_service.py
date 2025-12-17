"""
Place normalization service.
Provides fuzzy matching for place names to standardize location data.
"""
from __future__ import annotations
from typing import List, Dict
from rapidfuzz import fuzz
import sqlite3

# Default similarity threshold for fuzzy matching (0-100)
DEFAULT_SIMILARITY_THRESHOLD = 80

def generate_place_suggestions(db: sqlite3.Connection, threshold: int = DEFAULT_SIMILARITY_THRESHOLD) -> int:
    """
    Generate place variant suggestions by fuzzy-matching unstandardized places.
    
    Args:
        db: Database connection
        threshold: Minimum similarity score (0-100) to consider a match
    
    Returns:
        Number of suggestions generated
    """
    # Get all unique place names from persons and families
    places_set = set()
    
    birth_places = db.execute("SELECT DISTINCT birth_place FROM persons WHERE birth_place IS NOT NULL AND birth_place != ''").fetchall()
    for row in birth_places:
        places_set.add(row[0].strip())
    
    death_places = db.execute("SELECT DISTINCT death_place FROM persons WHERE death_place IS NOT NULL AND death_place != ''").fetchall()
    for row in death_places:
        places_set.add(row[0].strip())
    
    marriage_places = db.execute("SELECT DISTINCT marriage_place FROM families WHERE marriage_place IS NOT NULL AND marriage_place != ''").fetchall()
    for row in marriage_places:
        places_set.add(row[0].strip())
    
    if not places_set:
        return 0
    
    places = sorted(places_set)
    
    # Get existing canonical places
    canonical_rows = db.execute("SELECT id, canonical_name FROM places").fetchall()
    canonical_places = {row[1]: row[0] for row in canonical_rows}
    
    # If no canonical places exist, create one from the most common place
    if not canonical_places and places:
        # Use the first place alphabetically as initial canonical
        first_place = places[0]
        cursor = db.execute("INSERT INTO places (canonical_name) VALUES (?)", (first_place,))
        canonical_places[first_place] = cursor.lastrowid
    
    suggestions_added = 0
    
    # For each unstandardized place, find best match among canonical places
    for place in places:
        if place in canonical_places:
            # Already canonical, skip
            continue
        
        best_score = 0
        best_canonical_id = None
        
        for canonical_name, canonical_id in canonical_places.items():
            score = fuzz.ratio(place.lower(), canonical_name.lower())
            if score > best_score:
                best_score = score
                best_canonical_id = canonical_id
        
        # If similarity is above threshold, suggest it
        if best_score >= threshold and best_canonical_id:
            # Check if suggestion already exists
            existing = db.execute(
                "SELECT id FROM place_variants WHERE variant_name = ? AND canonical_place_id = ?",
                (place, best_canonical_id)
            ).fetchone()
            
            if not existing:
                db.execute(
                    """
                    INSERT INTO place_variants (variant_name, canonical_place_id, confidence_score, status)
                    VALUES (?, ?, ?, 'pending')
                    """,
                    (place, best_canonical_id, best_score / 100.0)
                )
                suggestions_added += 1
        elif best_score < threshold:
            # No good match, create new canonical place
            # Use INSERT OR IGNORE to handle race conditions
            cursor = db.execute("INSERT OR IGNORE INTO places (canonical_name) VALUES (?)", (place,))
            if cursor.rowcount > 0:
                canonical_places[place] = cursor.lastrowid
            else:
                # Place was inserted by another process, fetch it
                row = db.execute("SELECT id FROM places WHERE canonical_name = ?", (place,)).fetchone()
                if row:
                    canonical_places[place] = row[0]
    
    db.commit()
    return suggestions_added

def get_unstandardized_places(db: sqlite3.Connection, limit: int = 100) -> List[Dict]:
    """
    Get list of place variants that are pending review.
    
    Returns:
        List of dicts with variant info
    """
    rows = db.execute(
        """
        SELECT pv.id, pv.variant_name, p.canonical_name, pv.confidence_score, pv.created_at
        FROM place_variants pv
        JOIN places p ON p.id = pv.canonical_place_id
        WHERE pv.status = 'pending'
        ORDER BY pv.confidence_score DESC, pv.variant_name
        LIMIT ?
        """,
        (limit,)
    ).fetchall()
    
    return [
        {
            "id": r[0],
            "variant_name": r[1],
            "suggested_canonical": r[2],
            "confidence": r[3],
            "created_at": r[4],
        }
        for r in rows
    ]

def approve_place_variant(db: sqlite3.Connection, variant_id: int) -> bool:
    """
    Approve a place variant suggestion.
    Updates all occurrences of the variant to use the canonical name.
    
    Returns:
        True if approved successfully
    """
    # Get variant info
    row = db.execute(
        """
        SELECT pv.variant_name, p.canonical_name
        FROM place_variants pv
        JOIN places p ON p.id = pv.canonical_place_id
        WHERE pv.id = ?
        """,
        (variant_id,)
    ).fetchone()
    
    if not row:
        return False
    
    variant_name, canonical_name = row
    
    # Update all persons with this place
    db.execute(
        "UPDATE persons SET birth_place = ? WHERE birth_place = ?",
        (canonical_name, variant_name)
    )
    db.execute(
        "UPDATE persons SET death_place = ? WHERE death_place = ?",
        (canonical_name, variant_name)
    )
    
    # Update all families
    db.execute(
        "UPDATE families SET marriage_place = ? WHERE marriage_place = ?",
        (canonical_name, variant_name)
    )
    
    # Mark variant as approved
    db.execute(
        "UPDATE place_variants SET status = 'approved', reviewed_at = datetime('now') WHERE id = ?",
        (variant_id,)
    )
    
    db.commit()
    return True
