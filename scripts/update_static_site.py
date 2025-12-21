#!/usr/bin/env python3
"""
Update static site with latest database data.

This script:
1. Checks if the database exists
2. Exports all tables to JSON files
3. Shows a summary of changes
"""

import sys
from pathlib import Path
from export_to_json import export_database_to_json

def main():
    # Get repository root
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    
    # Paths
    db_path = repo_root / "data" / "family_tree.sqlite"
    output_dir = repo_root / "docs" / "data"
    
    print("=" * 70)
    print("Update GitHub Pages Static Site")
    print("=" * 70)
    print()
    
    if not db_path.exists():
        print("❌ Error: Database not found at", db_path)
        print()
        print("Please run the application and import data first:")
        print("  1. Start the app: python run.py")
        print("  2. Import GEDCOM or RMTree data")
        print("  3. Run this script again")
        sys.exit(1)
    
    print(f"✓ Found database: {db_path}")
    print(f"  Size: {db_path.stat().st_size / 1024:.1f} KB")
    print()
    
    # Export
    print("Exporting data to JSON files...")
    print()
    export_database_to_json(db_path, output_dir)
    
    print()
    print("=" * 70)
    print("✓ Update complete!")
    print("=" * 70)
    print()
    print("Next steps:")
    print("  1. Review the changes: git status")
    print("  2. Commit the changes: git add docs/data/*.json && git commit -m 'Update data'")
    print("  3. Push to GitHub: git push")
    print("  4. Your site will update automatically at:")
    print("     https://yourusername.github.io/repo-name/")
    print()

if __name__ == "__main__":
    main()
