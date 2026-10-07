import {
  isDisplayPanelType,
  isDisplayZoomPercent,
  type ClassificationMode,
  type DisplaySettings,
  type FinalStage,
  type Group,
  type GroupStanding,
  type LeagueMatch,
  type PublicTournamentState,
  type TeamSummary,
  type TournamentSettings,
} from '../../shared/types/tournament.js';
import type { SqliteDatabase } from '../db/database.js';
import { calculateBracket, type BracketResult, type BracketSeed } from './bracket.js';
import { calculateClassification } from './classification.js';

interface SettingsRow {
  name: string;
  classification_mode: ClassificationMode;
  final_round_count: number | null;
  third_place_enabled: number;
}

interface DisplaySettingsRow {
  active_panel: string;
  zoom_percent: number;
}

interface TeamRow {
  id: number;
  number: number;
  name: string;
  group_id: number;
  group_name: string;
  group_sort_order: number;
}

const TEAM_SUMMARY_SELECT = `
  SELECT
    teams.id,
    teams.number,
    teams.name,
    league_groups.id AS group_id,
    league_groups.name AS group_name,
    league_groups.sort_order AS group_sort_order
  FROM teams
  JOIN league_groups ON league_groups.id = teams.group_id
`;

interface LeagueMatchRow {
  id: number;
  order_index: number;
  round_index: number;
  counts_toward_standings: number;
  score_a: number | null;
  score_b: number | null;
  team_a_id: number;
  team_a_number: number;
  team_a_name: string;
  team_a_group_id: number;
  team_a_group_name: string;
  team_a_group_sort_order: number;
  team_b_id: number;
  team_b_number: number;
  team_b_name: string;
  team_b_group_id: number;
  team_b_group_name: string;
  team_b_group_sort_order: number;
}

function teamFromRow(row: TeamRow): TeamSummary {
  return {
    id: row.id,
    number: row.number,
    name: row.name,
    group: { id: row.group_id, name: row.group_name, sortOrder: row.group_sort_order },
  };
}

export function getSettings(database: SqliteDatabase): TournamentSettings {
  const row = database.prepare(
    'SELECT name, classification_mode, final_round_count, third_place_enabled FROM tournament_settings WHERE id = 1',
  ).get() as SettingsRow | undefined;
  if (!row) {
    throw new Error('As definições do torneio não foram inicializadas.');
  }
  return {
    name: row.name,
    classificationMode: row.classification_mode,
    finalRoundCount: row.final_round_count,
    thirdPlaceEnabled: Boolean(row.third_place_enabled),
  };
}

export function getDisplaySettings(database: SqliteDatabase): DisplaySettings {
  const row = database.prepare(
    'SELECT active_panel, zoom_percent FROM display_settings WHERE id = 1',
  ).get() as DisplaySettingsRow | undefined;
  if (!row) {
    throw new Error('As definições do ecrã não foram inicializadas.');
  }
  return {
    activePanel: isDisplayPanelType(row.active_panel) ? row.active_panel : 'latest-results',
    zoomPercent: isDisplayZoomPercent(row.zoom_percent) ? row.zoom_percent : 100,
  };
}

export function getTeamSummaries(database: SqliteDatabase): TeamSummary[] {
  const rows = database.prepare(`${TEAM_SUMMARY_SELECT} ORDER BY teams.number ASC`).all() as TeamRow[];
  return rows.map(teamFromRow);
}

export function getTeamSummary(database: SqliteDatabase, teamId: number): TeamSummary | null {
  const row = database.prepare(`${TEAM_SUMMARY_SELECT} WHERE teams.id = ?`).get(teamId) as TeamRow | undefined;
  return row ? teamFromRow(row) : null;
}

export function getGroups(database: SqliteDatabase): Group[] {
  return database.prepare(`
    SELECT id, name, sort_order AS sortOrder
    FROM league_groups
    ORDER BY sort_order ASC, id ASC
  `).all() as Group[];
}

export function getLeagueMatches(database: SqliteDatabase): LeagueMatch[] {
  const rows = database.prepare(`
    SELECT
      league_matches.id,
      league_matches.order_index,
      league_matches.round_index,
      league_rounds.counts_toward_standings,
      league_matches.score_a,
      league_matches.score_b,
      team_a.id AS team_a_id,
      team_a.number AS team_a_number,
      team_a.name AS team_a_name,
      team_a_group.id AS team_a_group_id,
      team_a_group.name AS team_a_group_name,
      team_a_group.sort_order AS team_a_group_sort_order,
      team_b.id AS team_b_id,
      team_b.number AS team_b_number,
      team_b.name AS team_b_name,
      team_b_group.id AS team_b_group_id,
      team_b_group.name AS team_b_group_name,
      team_b_group.sort_order AS team_b_group_sort_order
    FROM league_matches
    JOIN league_rounds ON league_rounds.round_index = league_matches.round_index
    JOIN teams AS team_a ON team_a.id = league_matches.team_a_id
    JOIN league_groups AS team_a_group ON team_a_group.id = team_a.group_id
    JOIN teams AS team_b ON team_b.id = league_matches.team_b_id
    JOIN league_groups AS team_b_group ON team_b_group.id = team_b.group_id
    ORDER BY league_matches.order_index ASC
  `).all() as LeagueMatchRow[];

  return rows.map((row) => {
    const teamA = {
      id: row.team_a_id,
      number: row.team_a_number,
      name: row.team_a_name,
      group: {
        id: row.team_a_group_id,
        name: row.team_a_group_name,
        sortOrder: row.team_a_group_sort_order,
      },
    };
    const teamB = {
      id: row.team_b_id,
      number: row.team_b_number,
      name: row.team_b_name,
      group: {
        id: row.team_b_group_id,
        name: row.team_b_group_name,
        sortOrder: row.team_b_group_sort_order,
      },
    };
    return {
      id: row.id,
      gameNumber: row.order_index,
      roundNumber: row.round_index,
      countsTowardStandings: Boolean(row.counts_toward_standings),
      group: teamA.group.id === teamB.group.id ? teamA.group : null,
      teamA,
      teamB,
      scoreA: row.score_a,
      scoreB: row.score_b,
    };
  });
}

export function getFinalStage(
  database: SqliteDatabase,
  roundCount?: number | null,
  thirdPlaceEnabled?: boolean,
): FinalStage {
  if (roundCount === undefined || thirdPlaceEnabled === undefined) {
    const settings = getSettings(database);
    if (roundCount === undefined) roundCount = settings.finalRoundCount;
    if (thirdPlaceEnabled === undefined) thirdPlaceEnabled = settings.thirdPlaceEnabled;
  }

  const teams = new Map(getTeamSummaries(database).map((team) => [team.id, team]));
  const seedRows = database.prepare('SELECT slot_index, team_id FROM final_seeds ORDER BY slot_index ASC').all() as Array<{
    slot_index: number;
    team_id: number | null;
  }>;
  const seeds: BracketSeed[] = seedRows.map((row) => ({
    slotIndex: row.slot_index,
    team: row.team_id === null ? null : teams.get(row.team_id) ?? null,
  }));
  const resultRows = database.prepare(`
    SELECT round_index, match_index, score_a, score_b
    FROM final_match_results
    ORDER BY round_index ASC, match_index ASC
  `).all() as Array<{
    round_index: number;
    match_index: number;
    score_a: number | null;
    score_b: number | null;
  }>;
  const results: BracketResult[] = resultRows.map((row) => ({
    roundIndex: row.round_index,
    matchIndex: row.match_index,
    scoreA: row.score_a,
    scoreB: row.score_b,
  }));
  return calculateBracket(roundCount, seeds, results, thirdPlaceEnabled);
}

export function getPublicState(database: SqliteDatabase): PublicTournamentState {
  const tournament = getSettings(database);
  const groups = getGroups(database);
  const teams = getTeamSummaries(database);
  const matches = getLeagueMatches(database);
  const groupStandings: GroupStanding[] = groups.map((group) => {
    const groupTeams = teams.filter((team) => team.group.id === group.id);
    const groupMatches = matches.filter(
      (match) => match.countsTowardStandings && match.teamA.group.id === group.id && match.teamB.group.id === group.id,
    );
    return {
      group,
      rows: calculateClassification(groupTeams, groupMatches, tournament.classificationMode),
    };
  });
  return {
    tournament,
    display: getDisplaySettings(database),
    groups,
    matches,
    groupStandings,
    finalStage: getFinalStage(database, tournament.finalRoundCount, tournament.thirdPlaceEnabled),
  };
}
