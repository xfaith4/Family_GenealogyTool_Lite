#!/usr/bin/env python3
"""
Export SQLite database tables to JSON files for GitHub Pages hosting.
This script reads the Family Genealogy Tool database and exports each table
as a separate JSON file.
"""

import sys
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

def export_table_to_json(cursor: sqlite3.Cursor, table_name: str) -> List[Dict[str, Any]]:
    """
    Export a single table to a list of dictionaries.
    
    Args:
        cursor: SQLite cursor
        table_name: Name of the table to export
        
    Returns:
        List of dictionaries representing rows
    """
    cursor.execute(f"SELECT * FROM {table_name}")
    columns = [description[0] for description in cursor.description]
    rows = cursor.fetchall()
    
    result = []
    for row in rows:
        row_dict = {}
        for i, value in enumerate(row):
            # Convert datetime strings to ISO format if needed
            if isinstance(value, str) and columns[i].endswith('_at'):
                row_dict[columns[i]] = value
            else:
                row_dict[columns[i]] = value
        result.append(row_dict)
    
    return result

def get_all_tables(cursor: sqlite3.Cursor) -> List[str]:
    """Get list of all tables in the database."""
    cursor.execute("""
        SELECT name FROM sqlite_master 
        WHERE type='table' 
        AND name NOT LIKE 'sqlite_%'
        AND name NOT LIKE 'alembic_%'
        ORDER BY name
    """)
    return [row[0] for row in cursor.fetchall()]

def export_database_to_json(db_path: Path, output_dir: Path) -> None:
    """
    Export all tables from the database to JSON files.
    
    Args:
        db_path: Path to the SQLite database file
        output_dir: Directory where JSON files will be written
    """
    if not db_path.exists():
        print(f"Error: Database file not found at {db_path}")
        sys.exit(1)
    
    # Create output directory if it doesn't exist
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    
    # Get all tables
    tables = get_all_tables(cursor)
    print(f"Found {len(tables)} tables to export")
    
    # Export each table
    exported = {}
    for table_name in tables:
        print(f"Exporting {table_name}...", end=" ")
        try:
            data = export_table_to_json(cursor, table_name)
            output_file = output_dir / f"{table_name}.json"
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            
            exported[table_name] = len(data)
            print(f"✓ ({len(data)} rows)")
        except Exception as e:
            print(f"✗ Error: {e}")
    
    conn.close()
    
    # Create a metadata file
    metadata = {
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "database_path": str(db_path),
        "tables": exported,
        "total_rows": sum(exported.values())
    }
    
    metadata_file = output_dir / "_metadata.json"
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✓ Export complete!")
    print(f"  Total tables: {len(exported)}")
    print(f"  Total rows: {metadata['total_rows']}")
    print(f"  Output directory: {output_dir}")

def main():
    """Main entry point."""
    # Get repository root
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    
    # Default paths
    db_path = repo_root / "data" / "family_tree.sqlite"
    output_dir = repo_root / "docs" / "data"
    
    # Allow overriding paths via command line
    if len(sys.argv) > 1:
        db_path = Path(sys.argv[1])
    if len(sys.argv) > 2:
        output_dir = Path(sys.argv[2])
    
    print("=" * 60)
    print("Family Genealogy Tool - Database to JSON Exporter")
    print("=" * 60)
    print(f"Database: {db_path}")
    print(f"Output:   {output_dir}")
    print("=" * 60)
    print()
    
    export_database_to_json(db_path, output_dir)

if __name__ == "__main__":
    main()
