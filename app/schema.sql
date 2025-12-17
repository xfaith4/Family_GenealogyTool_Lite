PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS persons (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  xref TEXT UNIQUE,
  given TEXT,
  surname TEXT,
  sex TEXT,
  birth_date TEXT,
  birth_place TEXT,
  death_date TEXT,
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

CREATE TABLE IF NOT EXISTS media_assets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  path TEXT NOT NULL UNIQUE,
  sha256 TEXT NOT NULL,
  original_filename TEXT,
  mime_type TEXT,
  size_bytes INTEGER,
  thumbnail_path TEXT,
  thumb_width INTEGER,
  thumb_height INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS media_links (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id INTEGER NOT NULL REFERENCES media_assets(id) ON DELETE CASCADE,
  person_id INTEGER REFERENCES persons(id) ON DELETE CASCADE,
  family_id INTEGER REFERENCES families(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL DEFAULT (datetime('now')),
  CHECK ((person_id IS NOT NULL AND family_id IS NULL) OR (person_id IS NULL AND family_id IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS idx_persons_name ON persons(surname, given);
CREATE INDEX IF NOT EXISTS idx_rel_child ON relationships(child_person_id);
CREATE INDEX IF NOT EXISTS idx_media_assets_sha256 ON media_assets(sha256);
CREATE INDEX IF NOT EXISTS idx_media_links_asset ON media_links(asset_id);
CREATE INDEX IF NOT EXISTS idx_media_links_person ON media_links(person_id);
CREATE INDEX IF NOT EXISTS idx_media_links_family ON media_links(family_id);
