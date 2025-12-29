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
  status TEXT NOT NULL DEFAULT 'unassigned',
  source_path TEXT,
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
CREATE INDEX IF NOT EXISTS idx_media_assets_original_filename ON media_assets(original_filename);
CREATE INDEX IF NOT EXISTS idx_media_links_asset ON media_links(asset_id);
CREATE INDEX IF NOT EXISTS idx_media_links_person ON media_links(person_id);
CREATE INDEX IF NOT EXISTS idx_media_links_family ON media_links(family_id);

-- Person profile attributes (flexible key/value metadata)
CREATE TABLE IF NOT EXISTS person_attributes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  person_id INTEGER NOT NULL REFERENCES persons(id) ON DELETE CASCADE,
  key TEXT NOT NULL,
  value TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_person_attributes_person_key ON person_attributes(person_id, key);

-- Data Quality tables
CREATE TABLE IF NOT EXISTS dq_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  issue_type TEXT NOT NULL,
  severity TEXT NOT NULL DEFAULT 'warning',
  entity_type TEXT NOT NULL,
  entity_ids TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'open',
  confidence REAL,
  impact_score REAL,
  explanation_json TEXT,
  detected_at DATETIME NOT NULL DEFAULT (datetime('now')),
  resolved_at DATETIME
);
CREATE INDEX IF NOT EXISTS idx_dq_issue_type_status ON dq_issues(issue_type, status);
CREATE INDEX IF NOT EXISTS idx_dq_issue_detected ON dq_issues(detected_at);

CREATE TABLE IF NOT EXISTS dq_action_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  action_type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  undo_payload_json TEXT,
  created_at DATETIME NOT NULL DEFAULT (datetime('now')),
  applied_by TEXT
);
CREATE INDEX IF NOT EXISTS idx_dq_action_type ON dq_action_log(action_type);

-- Place normalization plan (saved approvals for bulk apply + rebuild replay)
CREATE TABLE IF NOT EXISTS place_normalization_rules (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  canonical TEXT NOT NULL UNIQUE,
  variants_json TEXT NOT NULL,
  approved INTEGER NOT NULL DEFAULT 0,
  source_issue_id INTEGER,
  authority_source TEXT,
  authority_id TEXT,
  latitude REAL,
  longitude REAL,
  notes TEXT,
  created_at DATETIME NOT NULL DEFAULT (datetime('now')),
  updated_at DATETIME NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_place_norm_rules_approved ON place_normalization_rules(approved);
CREATE INDEX IF NOT EXISTS idx_place_norm_rules_source_issue ON place_normalization_rules(source_issue_id);

CREATE TABLE IF NOT EXISTS date_normalizations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  entity_type TEXT NOT NULL,
  entity_id INTEGER NOT NULL,
  raw_value TEXT NOT NULL,
  normalized TEXT,
  precision TEXT,
  qualifier TEXT,
  confidence REAL,
  is_ambiguous INTEGER NOT NULL DEFAULT 0,
  detected_at DATETIME NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_date_norm_entity ON date_normalizations(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_date_norm_confidence ON date_normalizations(confidence);
-- Places (canonical + variants) with optional authority enrichment
CREATE TABLE IF NOT EXISTS places (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name_canonical TEXT NOT NULL UNIQUE,
  latitude REAL,
  longitude REAL,
  authority_source TEXT,
  authority_id TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_places_authority_source ON places(authority_source);
CREATE INDEX IF NOT EXISTS idx_places_authority_id ON places(authority_id);

CREATE TABLE IF NOT EXISTS place_variants (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  place_id INTEGER NOT NULL REFERENCES places(id) ON DELETE CASCADE,
  name_variant TEXT NOT NULL UNIQUE,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_place_variants_place_id ON place_variants(place_id);
