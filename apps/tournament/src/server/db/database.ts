import Database from 'better-sqlite3';
import { mkdirSync } from 'node:fs';
import { dirname } from 'node:path';

export type SqliteDatabase = Database.Database;

export interface DatabaseOptions {
  path?: string;
}

const currentSchema = `
  CREATE TABLE IF NOT EXISTS tournament_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    final_round_count INTEGER CHECK (final_round_count IS NULL OR (final_round_count BETWEEN 1 AND 8)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    third_place_enabled INTEGER NOT NULL DEFAULT 0 CHECK (third_place_enabled IN (0, 1)),
    classification_mode TEXT NOT NULL DEFAULT 'standard' CHECK (classification_mode IN ('standard', 'total-points'))
  );

  INSERT OR IGNORE INTO tournament_settings (
    id, name, final_round_count, created_at, updated_at, third_place_enabled, classification_mode
  ) VALUES (1, 'Torneio', NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 0, 'standard');

  CREATE TABLE IF NOT EXISTS display_settings (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    active_panel TEXT NOT NULL CHECK (length(trim(active_panel)) > 0),
    zoom_percent INTEGER NOT NULL DEFAULT 100 CHECK (zoom_percent BETWEEN 50 AND 400),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  INSERT OR IGNORE INTO display_settings (id, active_panel, zoom_percent, created_at, updated_at)
  VALUES (1, 'latest-results', 100, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

  CREATE TABLE IF NOT EXISTS league_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(name)) > 0),
    sort_order INTEGER NOT NULL UNIQUE CHECK (sort_order >= 0),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  INSERT OR IGNORE INTO league_groups (id, name, sort_order, created_at, updated_at)
  VALUES (1, 'Grupo A', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);

  CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number INTEGER NOT NULL UNIQUE CHECK (number > 0),
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    group_id INTEGER NOT NULL REFERENCES league_groups(id),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
  );

  CREATE TABLE IF NOT EXISTS players (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    name TEXT NOT NULL CHECK (length(trim(name)) > 0),
    sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
    FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
  );

  CREATE TABLE IF NOT EXISTS league_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_index INTEGER NOT NULL UNIQUE CHECK (order_index >= 1),
    round_index INTEGER NOT NULL CHECK (round_index >= 1),
    team_a_id INTEGER NOT NULL,
    team_b_id INTEGER NOT NULL,
    score_a INTEGER,
    score_b INTEGER,
    CHECK (team_a_id <> team_b_id),
    CHECK (
      (score_a IS NULL AND score_b IS NULL) OR
      (score_a IS NOT NULL AND score_b IS NOT NULL AND score_a >= 0 AND score_b >= 0)
    ),
    FOREIGN KEY (team_a_id) REFERENCES teams(id),
    FOREIGN KEY (team_b_id) REFERENCES teams(id)
  );

  CREATE TABLE IF NOT EXISTS final_seeds (
    slot_index INTEGER PRIMARY KEY CHECK (slot_index >= 1),
    team_id INTEGER,
    FOREIGN KEY (team_id) REFERENCES teams(id)
  );

  CREATE TABLE IF NOT EXISTS final_match_results (
    round_index INTEGER NOT NULL CHECK (round_index >= 1),
    match_index INTEGER NOT NULL CHECK (match_index >= 1),
    score_a INTEGER,
    score_b INTEGER,
    PRIMARY KEY (round_index, match_index),
    CHECK (
      (score_a IS NULL AND score_b IS NULL) OR
      (score_a IS NOT NULL AND score_b IS NOT NULL AND score_a >= 0 AND score_b >= 0)
    )
  );

  CREATE UNIQUE INDEX IF NOT EXISTS idx_final_seeds_unique_team
  ON final_seeds(team_id)
  WHERE team_id IS NOT NULL;

  CREATE INDEX IF NOT EXISTS idx_teams_group ON teams(group_id);
  CREATE INDEX IF NOT EXISTS idx_players_team_order ON players(team_id, sort_order);
  CREATE INDEX IF NOT EXISTS idx_league_matches_order ON league_matches(order_index);

  CREATE TABLE IF NOT EXISTS league_rounds (
    round_index INTEGER PRIMARY KEY CHECK (round_index >= 1),
    counts_toward_standings INTEGER NOT NULL DEFAULT 0 CHECK (counts_toward_standings IN (0, 1))
  );
`;

function defaultDatabasePath(): string {
  return process.env.DATABASE_PATH ?? '/data/tournament.sqlite';
}

export function initializeSchema(database: SqliteDatabase): void {
  database.transaction(() => database.exec(currentSchema))();
}

/** Opens SQLite with the connection settings required for durable concurrent HTTP use. */
export function openDatabase(options: DatabaseOptions = {}): SqliteDatabase {
  const databasePath = options.path ?? defaultDatabasePath();
  if (databasePath !== ':memory:') {
    mkdirSync(dirname(databasePath), { recursive: true });
  }
  const database = new Database(databasePath);
  database.pragma('foreign_keys = ON');
  database.pragma('journal_mode = WAL');
  database.pragma('busy_timeout = 5000');
  initializeSchema(database);
  return database;
}
