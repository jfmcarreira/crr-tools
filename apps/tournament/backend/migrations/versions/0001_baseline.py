"""Initial Tournament database schema."""

from alembic import op

revision = "0001_baseline"
down_revision = None
branch_labels = None
depends_on = None

# Keep schema-changing SQL inside Alembic revisions.
SCHEMA = """
CREATE TABLE tournament_settings (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 name TEXT NOT NULL CHECK (length(trim(name)) > 0),
 final_round_count INTEGER CHECK (final_round_count IS NULL OR (final_round_count BETWEEN 1 AND 8)),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
 third_place_enabled INTEGER NOT NULL DEFAULT 0 CHECK (third_place_enabled IN (0, 1)),
 classification_mode TEXT NOT NULL DEFAULT 'standard' CHECK (classification_mode IN ('standard', 'total-points'))
);
CREATE TABLE display_settings (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 active_panel TEXT NOT NULL CHECK (length(trim(active_panel)) > 0),
 zoom_percent INTEGER NOT NULL DEFAULT 100 CHECK (zoom_percent BETWEEN 50 AND 400),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE league_groups (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 name TEXT NOT NULL COLLATE NOCASE UNIQUE CHECK (length(trim(name)) > 0),
 sort_order INTEGER NOT NULL UNIQUE CHECK (sort_order >= 0),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE teams (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 number INTEGER NOT NULL UNIQUE CHECK (number > 0),
 name TEXT NOT NULL CHECK (length(trim(name)) > 0),
 group_id INTEGER NOT NULL REFERENCES league_groups(id),
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE players (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 team_id INTEGER NOT NULL,
 name TEXT NOT NULL CHECK (length(trim(name)) > 0),
 sort_order INTEGER NOT NULL CHECK (sort_order >= 0),
 FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE
);
CREATE TABLE league_matches (
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 order_index INTEGER NOT NULL UNIQUE CHECK (order_index >= 1),
 round_index INTEGER NOT NULL CHECK (round_index >= 1),
 team_a_id INTEGER NOT NULL, team_b_id INTEGER NOT NULL, score_a INTEGER, score_b INTEGER,
 CHECK (team_a_id <> team_b_id),
 CHECK ((score_a IS NULL AND score_b IS NULL) OR (score_a IS NOT NULL AND score_b IS NOT NULL AND score_a >= 0 AND score_b >= 0)),
 FOREIGN KEY (team_a_id) REFERENCES teams(id), FOREIGN KEY (team_b_id) REFERENCES teams(id)
);
CREATE TABLE final_seeds (
 slot_index INTEGER PRIMARY KEY CHECK (slot_index >= 1),
 team_id INTEGER, FOREIGN KEY (team_id) REFERENCES teams(id)
);
CREATE TABLE final_match_results (
 round_index INTEGER NOT NULL CHECK (round_index >= 1),
 match_index INTEGER NOT NULL CHECK (match_index >= 1), score_a INTEGER, score_b INTEGER,
 PRIMARY KEY (round_index, match_index),
 CHECK ((score_a IS NULL AND score_b IS NULL) OR (score_a IS NOT NULL AND score_b IS NOT NULL AND score_a >= 0 AND score_b >= 0))
);
CREATE UNIQUE INDEX idx_final_seeds_unique_team ON final_seeds(team_id) WHERE team_id IS NOT NULL;
CREATE INDEX idx_teams_group ON teams(group_id);
CREATE INDEX idx_players_team_order ON players(team_id, sort_order);
CREATE INDEX idx_league_matches_order ON league_matches(order_index);
CREATE TABLE league_rounds (
 round_index INTEGER PRIMARY KEY CHECK (round_index >= 1),
 counts_toward_standings INTEGER NOT NULL DEFAULT 0 CHECK (counts_toward_standings IN (0, 1))
);
INSERT INTO tournament_settings (id, name, created_at, updated_at) VALUES (1, 'Torneio', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
INSERT INTO display_settings (id, active_panel, created_at, updated_at) VALUES (1, 'latest-results', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
INSERT INTO league_groups (id, name, sort_order, created_at, updated_at) VALUES (1, 'Grupo A', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
"""


def upgrade() -> None:
    for statement in SCHEMA.split(";"):
        if statement.strip():
            op.execute(statement)


def downgrade() -> None:
    for table in ["final_match_results", "final_seeds", "players", "league_matches", "league_rounds",
                  "teams", "league_groups", "display_settings", "tournament_settings"]:
        op.drop_table(table)
