PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS persons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  xref TEXT UNIQUE,
  given TEXT,
  surname TEXT,
  sex TEXT,
  birth_date TEXT,
  birth_date_canonical TEXT,
  birth_date_confidence TEXT,
  birth_place TEXT,
  death_date TEXT,
  death_date_canonical TEXT,
  death_date_confidence TEXT,
  death_place TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS families (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  xref TEXT UNIQUE,
  husband_person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
  wife_person_id INTEGER REFERENCES persons(id) ON DELETE SET NULL,
  marriage_date TEXT,
  marriage_date_canonical TEXT,
  marriage_date_confidence TEXT,
  marriage_place TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS family_children (
  family_id INTEGER NOT NULL REFERENCES families(id) ON DELETE CASCADE,
  child_person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  PRIMARY KEY (family_id, child_person_id)
);

CREATE TABLE IF NOT EXISTS relationships (
  parent_person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  child_person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  rel_type TEXT NOT NULL DEFAULT 'parent',
  PRIMARY KEY (parent_person_id, child_person_id, rel_type)
);

CREATE TABLE IF NOT EXISTS notes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER REFERENCES persons(id) ON DELETE CASCADE,
  family_id INTEGER REFERENCES families(id) ON DELETE CASCADE,
  note_text TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  file_name TEXT NOT NULL,
  original_name TEXT,
  mime_type TEXT,
  sha256 TEXT,
  size_bytes INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS places (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical_name TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS place_variants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  variant_name TEXT NOT NULL,
  canonical_place_id INTEGER REFERENCES places(id) ON DELETE CASCADE,
  status TEXT NOT NULL DEFAULT 'pending',
  confidence_score REAL,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at TEXT
);

CREATE TABLE IF NOT EXISTS duplicate_candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person1_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  person2_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  similarity_score REAL NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  reviewed_at TEXT,
  UNIQUE(person1_id, person2_id)
);

CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(surname, given);
CREATE INDEX IF NOT EXISTS idx_rel_child ON relationships(child_person_id);
CREATE INDEX IF NOT EXISTS idx_place_variants_status ON place_variants(status);
CREATE INDEX IF NOT EXISTS idx_duplicate_candidates_status ON duplicate_candidates(status);
