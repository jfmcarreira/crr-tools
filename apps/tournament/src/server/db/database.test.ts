import Database from 'better-sqlite3';
import { afterEach, describe, expect, it } from 'vitest';
import { initializeSchema, type SqliteDatabase } from './database.js';
import { getDisplaySettings } from '../services/state.js';

let database: SqliteDatabase | undefined;

afterEach(() => {
  database?.close();
  database = undefined;
});

describe('database initialization', () => {
  it('creates the current schema and its default rows', () => {
    database = new Database(':memory:');
    database.pragma('foreign_keys = ON');
    initializeSchema(database);

    expect(database.prepare('SELECT id, name, sort_order FROM league_groups').all()).toEqual([
      { id: 1, name: 'Grupo A', sort_order: 0 },
    ]);
    expect(database.prepare(`
      SELECT name, final_round_count, third_place_enabled, classification_mode
      FROM tournament_settings
    `).get()).toEqual({
      name: 'Torneio',
      final_round_count: null,
      third_place_enabled: 0,
      classification_mode: 'standard',
    });
    expect(database.prepare('SELECT id, active_panel, zoom_percent FROM display_settings').get()).toEqual({
      id: 1,
      active_panel: 'latest-results',
      zoom_percent: 100,
    });
    expect(database.prepare('SELECT * FROM league_rounds').all()).toEqual([]);
    expect(() => database!.prepare(`
      INSERT INTO teams (number, name, created_at, updated_at)
      VALUES (1, 'Sem grupo', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `).run()).toThrow('NOT NULL constraint failed');
  });

  it('enforces the current schema constraints', () => {
    database = new Database(':memory:');
    database.pragma('foreign_keys = ON');
    initializeSchema(database);

    database.prepare(`
      INSERT INTO teams (id, number, name, group_id, created_at, updated_at)
      VALUES (1, 1, 'Equipa 1', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `).run();
    expect(() => database!.prepare(`
      INSERT INTO league_matches (order_index, round_index, team_a_id, team_b_id)
      VALUES (1, 0, 1, 1)
    `).run()).toThrow('CHECK constraint failed');
    expect(() => database!.prepare(`
      UPDATE tournament_settings SET classification_mode = 'invalid' WHERE id = 1
    `).run()).toThrow('CHECK constraint failed');
    expect(() => database!.prepare(`
      UPDATE display_settings SET zoom_percent = 401 WHERE id = 1
    `).run()).toThrow('CHECK constraint failed');
    expect(() => database!.prepare(`
      INSERT INTO league_rounds (round_index, counts_toward_standings)
      VALUES (1, 2)
    `).run()).toThrow('CHECK constraint failed');
    expect(getDisplaySettings(database)).toEqual({ activePanel: 'latest-results', zoomPercent: 100 });
  });

});
