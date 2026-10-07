import cookie from '@fastify/cookie';
import fastifyStatic from '@fastify/static';
import Fastify, { type FastifyInstance, type FastifyReply, type FastifyRequest } from 'fastify';
import { randomInt } from 'node:crypto';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { z, ZodError, type ZodType } from 'zod';
import {
  createSessionToken,
  isSecureRequest,
  isValidSessionToken,
  LoginRateLimiter,
  passwordMatches,
  SESSION_COOKIE_NAME,
  type AuthenticationConfig,
} from './auth.js';
import { openDatabase, type SqliteDatabase } from './db/database.js';
import { AppError } from './errors.js';
import { StateChangeEvents } from './events.js';
import { downstreamMatches, getBracketMatch } from './services/bracket.js';
import { buildGroupQualificationPreview, buildOverallQualificationPreview } from '../shared/finalSeeding.js';
import { generateRoundRobinSchedule } from './services/calendar.js';
import {
  getFinalStage,
  getDisplaySettings,
  getGroups,
  getLeagueMatches,
  getPublicState,
  getSettings,
  getTeamSummaries,
  getTeamSummary,
} from './services/state.js';
import {
  CLASSIFICATION_MODES,
  DISPLAY_PANEL_TYPES,
  isDisplayZoomPercent,
  type CalendarGeneration,
  type Group,
  type Player,
  type Team,
  type TeamSummary,
} from '../shared/types/tournament.js';

const positiveIntegerSchema = z.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const positiveIdParameterSchema = z.coerce.number().int().positive().max(Number.MAX_SAFE_INTEGER);
const scoreSchema = z.number().int().min(0).max(Number.MAX_SAFE_INTEGER);
const teamInputSchema = z.object({
  number: positiveIntegerSchema,
  name: z.string().trim().min(1).max(200),
  groupId: positiveIdParameterSchema,
});
const teamCreateInputSchema = teamInputSchema.extend({ number: positiveIntegerSchema.optional() });
const groupInputSchema = z.object({
  name: z.string().trim().min(1).max(200),
});
const playerInputSchema = z.object({
  name: z.string().trim().min(1).max(200),
});
const settingsInputSchema = z.object({
  name: z.string().trim().min(1).max(200),
  classificationMode: z.enum(CLASSIFICATION_MODES),
});
const displaySettingsInputSchema = z.object({
  activePanel: z.enum(DISPLAY_PANEL_TYPES),
  zoomPercent: z.number().int().refine(isDisplayZoomPercent),
});
const resultInputSchema = z.object({ scoreA: scoreSchema, scoreB: scoreSchema });
const roundStandingsInputSchema = z.object({ countsTowardStandings: z.boolean() });
const confirmationSchema = z.object({ confirm: z.literal(true).optional() });
const calendarLegsSchema = z.union([z.literal(1), z.literal(2)]);
const calendarGenerationSchema = z.object({
  legs: calendarLegsSchema,
  teamOrder: z.array(z.object({
    teamId: positiveIdParameterSchema,
    groupId: positiveIdParameterSchema,
  })),
});
const calendarGenerationSaveSchema = z.object({
  generation: calendarGenerationSchema,
  confirmReplace: z.literal(true).optional(),
});
const finalConfigSchema = z.object({
  roundCount: positiveIntegerSchema.max(8),
  thirdPlaceEnabled: z.boolean().default(false),
  confirmClearResults: z.literal(true).optional(),
});
const autoSeedPreviewSchema = z.discriminatedUnion('mode', [
  z.object({
    mode: z.literal('per-group'),
    qualifiersPerGroup: positiveIntegerSchema,
  }),
  z.object({
    mode: z.literal('overall'),
    qualifierCount: positiveIntegerSchema,
  }),
]);
const finalSeedsSchema = z.object({
  seeds: z.array(z.object({
    slotIndex: positiveIntegerSchema,
    teamId: positiveIntegerSchema.nullable(),
  })),
  confirmClearResults: z.literal(true).optional(),
});

interface PlayerRow {
  id: number;
  team_id: number;
  name: string;
  sort_order: number;
}

export interface CreateAppOptions {
  database?: SqliteDatabase;
  databasePath?: string;
  authentication?: AuthenticationConfig;
  basePath?: string;
  staticRoot?: string;
  trustProxy?: boolean;
  logger?: boolean;
}

function parse<T>(schema: ZodType<T>, value: unknown): T {
  const result = schema.safeParse(value);
  if (!result.success) {
    throw new AppError(400, 'Os dados enviados não são válidos.');
  }
  return result.data;
}

function authenticationFromOptions(options: CreateAppOptions): AuthenticationConfig {
  const config = options.authentication ?? {
    adminPassword: process.env.ADMIN_PASSWORD ?? '',
    sessionSecret: process.env.SESSION_SECRET ?? '',
  };
  if (!config.adminPassword || !config.sessionSecret) {
    throw new Error('ADMIN_PASSWORD e SESSION_SECRET têm de estar definidos.');
  }
  return config;
}

function normalizedBasePath(basePath: string): string {
  if (!basePath.startsWith('/')) {
    throw new Error('APP_BASE_PATH tem de começar por "/".');
  }
  return basePath.endsWith('/') ? basePath : `${basePath}/`;
}

function cookieOptions(request: FastifyRequest, authentication: AuthenticationConfig, basePath: string) {
  return {
    path: basePath,
    httpOnly: true,
    sameSite: 'strict' as const,
    secure: isSecureRequest(request),
    maxAge: Math.floor((authentication.sessionLifetimeMs ?? 7 * 24 * 60 * 60 * 1000) / 1000),
  };
}

function clearCookieOptions(request: FastifyRequest, basePath: string) {
  return {
    path: basePath,
    httpOnly: true,
    sameSite: 'strict' as const,
    secure: isSecureRequest(request),
  };
}

function playerFromRow(row: PlayerRow): Player {
  return {
    id: row.id,
    teamId: row.team_id,
    name: row.name,
    sortOrder: row.sort_order,
  };
}

function getAdminTeams(database: SqliteDatabase): Team[] {
  const teams = getTeamSummaries(database).map((team) => ({ ...team, players: [] as Player[] }));
  const teamsById = new Map(teams.map((team) => [team.id, team]));
  const players = database.prepare(`
    SELECT id, team_id, name, sort_order
    FROM players
    ORDER BY team_id ASC, sort_order ASC, id ASC
  `).all() as PlayerRow[];
  for (const player of players) {
    teamsById.get(player.team_id)?.players.push(playerFromRow(player));
  }
  return teams;
}

function assertExistingTeam(database: SqliteDatabase, teamId: number): TeamSummary {
  const team = getTeamSummary(database, teamId);
  if (!team) {
    throw new AppError(404, 'A equipa não existe.');
  }
  return team;
}

function nextTeamNumber(database: SqliteDatabase): number {
  const row = database.prepare('SELECT COALESCE(MAX(number), 0) AS number FROM teams').get() as { number: number };
  if (row.number >= Number.MAX_SAFE_INTEGER) {
    throw new AppError(409, 'Não é possível atribuir outro número de equipa.');
  }
  return row.number + 1;
}

function assertExistingGroup(database: SqliteDatabase, groupId: number): Group {
  const group = database.prepare(`
    SELECT id, name, sort_order AS sortOrder
    FROM league_groups
    WHERE id = ?
  `).get(groupId) as Group | undefined;
  if (!group) {
    throw new AppError(404, 'O grupo não existe.');
  }
  return group;
}

function assertAvailableGroupName(database: SqliteDatabase, name: string, exceptId?: number): void {
  const group = database.prepare(`
    SELECT id FROM league_groups
    WHERE name = ? COLLATE NOCASE AND (? IS NULL OR id <> ?)
  `).get(name, exceptId ?? null, exceptId ?? null) as { id: number } | undefined;
  if (group) {
    throw new AppError(409, 'Já existe um grupo com esse nome.');
  }
}

function finalResultExists(database: SqliteDatabase): boolean {
  return database.prepare('SELECT 1 FROM final_match_results LIMIT 1').get() !== undefined;
}

function requireConfirmation(confirmed: boolean | undefined, message: string): void {
  if (!confirmed) {
    throw new AppError(409, message);
  }
}

function clearInvalidatedFinalResults(
  database: SqliteDatabase,
  roundCount: number,
  thirdPlaceEnabled: boolean,
  roundIndex: number,
  matchIndex: number,
  previousWinner: number | null,
): void {
  const nextWinner = getBracketMatch(
    getFinalStage(database, roundCount, thirdPlaceEnabled),
    roundIndex,
    matchIndex,
  )?.winner?.id ?? null;

  if (previousWinner === nextWinner) {
    return;
  }

  const clear = database.prepare('DELETE FROM final_match_results WHERE round_index = ? AND match_index = ?');
  downstreamMatches(roundCount, roundIndex, matchIndex)
    .forEach((downstream) => clear.run(downstream.roundIndex, downstream.matchIndex));

  if (thirdPlaceEnabled && roundIndex === roundCount - 1 && matchIndex <= 2) {
    clear.run(roundCount, 2);
  }
}

function teamsForGeneration(teams: readonly TeamSummary[], generation: CalendarGeneration): TeamSummary[] {
  if (generation.teamOrder.length !== teams.length) {
    throw new AppError(409, 'As equipas foram alteradas. Sorteie novamente o calendário.');
  }

  const teamsById = new Map(teams.map((team) => [team.id, team]));
  const seen = new Set<number>();
  return generation.teamOrder.map(({ teamId, groupId }) => {
    const team = teamsById.get(teamId);
    if (!team || team.group.id !== groupId || seen.has(teamId)) {
      throw new AppError(409, 'As equipas ou os grupos foram alterados. Sorteie novamente o calendário.');
    }
    seen.add(teamId);
    return team;
  });
}

function calendarSummary<T extends { roundNumber: number }>(matches: readonly T[]) {
  return {
    matches,
    matchCount: matches.length,
    roundCount: Math.max(0, ...matches.map((match) => match.roundNumber)),
  };
}

function shuffled<T>(values: readonly T[]): T[] {
  const result = [...values];
  for (let index = result.length - 1; index > 0; index -= 1) {
    const replacementIndex = randomInt(index + 1);
    [result[index], result[replacementIndex]] = [result[replacementIndex], result[index]];
  }
  return result;
}

export async function createApp(options: CreateAppOptions = {}): Promise<FastifyInstance> {
  const authentication = authenticationFromOptions(options);
  const basePath = normalizedBasePath(options.basePath ?? process.env.APP_BASE_PATH ?? '/');
  const ownsDatabase = !options.database;
  const database = options.database ?? openDatabase({
    path: options.databasePath,
  });
  const events = new StateChangeEvents();
  const loginRateLimiter = new LoginRateLimiter();
  const app = Fastify({
    logger: options.logger ?? false,
    trustProxy: options.trustProxy ?? process.env.TRUST_PROXY === 'true',
  });

  await app.register(cookie);

  app.setErrorHandler((error, _request, reply) => {
    if (error instanceof AppError) {
      return reply.status(error.statusCode).send({ error: error.message });
    }
    if (error instanceof ZodError) {
      return reply.status(400).send({ error: 'Os dados enviados não são válidos.' });
    }
    if ((error as { code?: string; message?: string }).code?.startsWith('SQLITE_CONSTRAINT_UNIQUE') &&
      (error as { message?: string }).message?.includes('league_groups.name')) {
      return reply.status(409).send({ error: 'Já existe um grupo com esse nome.' });
    }
    if ((error as { code?: string }).code?.startsWith('SQLITE_CONSTRAINT_UNIQUE')) {
      return reply.status(409).send({ error: 'Já existe uma equipa com esse número.' });
    }
    app.log.error(error);
    return reply.status(500).send({ error: 'Ocorreu um erro inesperado. Tente novamente.' });
  });

  app.setNotFoundHandler((_request, reply) => reply.status(404).send({ error: 'O recurso pedido não existe.' }));

  const requireAdmin = async (request: FastifyRequest): Promise<void> => {
    if (!isValidSessionToken(request.cookies[SESSION_COOKIE_NAME], authentication)) {
      throw new AppError(401, 'É necessário iniciar sessão para aceder à administração.');
    }
  };
  const stateChanged = () => events.broadcastStateChanged();

  app.post('/api/auth/login', async (request, reply) => {
    const body = parse(z.object({ password: z.string().min(1).max(1_000) }), request.body);
    const key = request.ip;
    if (loginRateLimiter.isLimited(key)) {
      throw new AppError(429, 'Foram feitas demasiadas tentativas. Tente novamente mais tarde.');
    }
    if (!passwordMatches(body.password, authentication.adminPassword)) {
      loginRateLimiter.recordFailure(key);
      throw new AppError(401, 'A palavra-passe está incorreta.');
    }
    loginRateLimiter.clear(key);
    reply.setCookie(SESSION_COOKIE_NAME, createSessionToken(authentication), cookieOptions(request, authentication, basePath));
    return { authenticated: true };
  });

  app.post('/api/auth/logout', async (request, reply) => {
    reply.clearCookie(SESSION_COOKIE_NAME, clearCookieOptions(request, basePath));
    return { authenticated: false };
  });

  app.get('/api/auth/session', async (request) => ({
    authenticated: isValidSessionToken(request.cookies[SESSION_COOKIE_NAME], authentication),
  }));

  app.get('/api/admin/settings', { preHandler: requireAdmin }, async () => getSettings(database));

  app.put('/api/admin/settings', { preHandler: requireAdmin }, async (request) => {
    const body = parse(settingsInputSchema, request.body);
    database.prepare(`
      UPDATE tournament_settings
      SET name = ?, classification_mode = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = 1
    `).run(body.name, body.classificationMode);
    stateChanged();
    return getSettings(database);
  });

  app.get('/api/admin/display', { preHandler: requireAdmin }, async () => getDisplaySettings(database));

  app.put('/api/admin/display', { preHandler: requireAdmin }, async (request) => {
    const body = parse(displaySettingsInputSchema, request.body);
    database.prepare(`
      UPDATE display_settings
      SET active_panel = ?, zoom_percent = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = 1
    `).run(body.activePanel, body.zoomPercent);
    stateChanged();
    return getDisplaySettings(database);
  });

  app.get('/api/admin/groups', { preHandler: requireAdmin }, async () => getGroups(database));

  app.post('/api/admin/groups', { preHandler: requireAdmin }, async (request, reply) => {
    const body = parse(groupInputSchema, request.body);
    assertAvailableGroupName(database, body.name);
    const result = database.prepare(`
      INSERT INTO league_groups (name, sort_order, created_at, updated_at)
      VALUES (?, COALESCE((SELECT MAX(sort_order) + 1 FROM league_groups), 0), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `).run(body.name);
    const group = assertExistingGroup(database, Number(result.lastInsertRowid));
    stateChanged();
    return reply.status(201).send(group);
  });

  app.put('/api/admin/groups/:id', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ id: positiveIdParameterSchema }), request.params);
    const body = parse(groupInputSchema, request.body);
    assertExistingGroup(database, params.id);
    assertAvailableGroupName(database, body.name, params.id);
    database.prepare(`
      UPDATE league_groups
      SET name = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `).run(body.name, params.id);
    stateChanged();
    return assertExistingGroup(database, params.id);
  });

  app.delete('/api/admin/groups/:id', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ id: positiveIdParameterSchema }), request.params);
    assertExistingGroup(database, params.id);
    if (database.prepare('SELECT 1 FROM teams WHERE group_id = ? LIMIT 1').get(params.id)) {
      throw new AppError(409, 'Não é possível eliminar um grupo com equipas.');
    }
    const groupCount = database.prepare('SELECT COUNT(*) AS count FROM league_groups').get() as { count: number };
    if (groupCount.count <= 1) {
      throw new AppError(409, 'Não é possível eliminar o último grupo.');
    }
    database.prepare('DELETE FROM league_groups WHERE id = ?').run(params.id);
    stateChanged();
    return replyEmpty();
  });

  app.get('/api/admin/teams', { preHandler: requireAdmin }, async () => getAdminTeams(database));

  app.post('/api/admin/teams/randomize', { preHandler: requireAdmin }, async (request) => {
    const body = parse(confirmationSchema, request.body ?? {});
    requireConfirmation(body.confirm, 'Confirme que pretende randomizar os números e os grupos das equipas.');
    const teams = getTeamSummaries(database);
    const groups = getGroups(database);
    const hasCalendar = database.prepare('SELECT 1 FROM league_matches LIMIT 1').get() !== undefined;

    database.transaction(() => {
      if (hasCalendar) {
        database.prepare('DELETE FROM league_matches').run();
        database.prepare('DELETE FROM league_rounds').run();
      }

      // Move unique numbers out of their current range before assigning the shuffled values.
      const maximumNumber = Math.max(0, ...teams.map((team) => team.number));
      const reserveNumber = database.prepare('UPDATE teams SET number = ? WHERE id = ?');
      teams.forEach((team, index) => reserveNumber.run(maximumNumber + index + 1, team.id));

      const assignedNumbers = shuffled(teams.map((team) => team.number));
      const assignedGroups = shuffled(groups);
      const updateTeam = database.prepare('UPDATE teams SET number = ?, group_id = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?');
      teams.forEach((team, index) => {
        updateTeam.run(assignedNumbers[index], assignedGroups[index % assignedGroups.length].id, team.id);
      });
    })();
    stateChanged();
    return {
      teams: getAdminTeams(database),
      calendarCleared: hasCalendar,
    };
  });

  app.post('/api/admin/teams', { preHandler: requireAdmin }, async (request, reply) => {
    const body = parse(teamCreateInputSchema, request.body);
    assertExistingGroup(database, body.groupId);
    const result = database.prepare(`
      INSERT INTO teams (number, name, group_id, created_at, updated_at)
      VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
    `).run(body.number ?? nextTeamNumber(database), body.name, body.groupId);
    const team = assertExistingTeam(database, Number(result.lastInsertRowid));
    stateChanged();
    return reply.status(201).send({ ...team, players: [] });
  });

  app.put('/api/admin/teams/:id', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ id: positiveIdParameterSchema }), request.params);
    const body = parse(teamInputSchema, request.body);
    const currentTeam = assertExistingTeam(database, params.id);
    assertExistingGroup(database, body.groupId);
    if (currentTeam.group.id !== body.groupId &&
      database.prepare('SELECT 1 FROM league_matches WHERE team_a_id = ? OR team_b_id = ? LIMIT 1').get(params.id, params.id)) {
      throw new AppError(409, 'Não é possível alterar o grupo de uma equipa utilizada no calendário. Limpe ou substitua o calendário primeiro.');
    }
    const result = database.prepare(`
      UPDATE teams
      SET number = ?, name = ?, group_id = ?, updated_at = CURRENT_TIMESTAMP
      WHERE id = ?
    `).run(body.number, body.name, body.groupId, params.id);
    if (result.changes === 0) {
      throw new AppError(404, 'A equipa não existe.');
    }
    stateChanged();
    return { ...assertExistingTeam(database, params.id), players: getAdminTeams(database).find((team) => team.id === params.id)?.players ?? [] };
  });

  app.delete('/api/admin/teams/:id', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ id: positiveIdParameterSchema }), request.params);
    assertExistingTeam(database, params.id);
    if (database.prepare('SELECT 1 FROM league_matches WHERE team_a_id = ? OR team_b_id = ? LIMIT 1').get(params.id, params.id)) {
      throw new AppError(409, 'Não é possível eliminar esta equipa porque está a ser utilizada no calendário.');
    }
    if (database.prepare('SELECT 1 FROM final_seeds WHERE team_id = ? LIMIT 1').get(params.id)) {
      throw new AppError(409, 'Não é possível eliminar esta equipa porque está a ser utilizada na fase final.');
    }
    database.prepare('DELETE FROM teams WHERE id = ?').run(params.id);
    stateChanged();
    return replyEmpty();
  });

  app.post('/api/admin/teams/:teamId/players', { preHandler: requireAdmin }, async (request, reply) => {
    const params = parse(z.object({ teamId: positiveIdParameterSchema }), request.params);
    const body = parse(playerInputSchema, request.body);
    assertExistingTeam(database, params.teamId);
    const result = database.prepare(`
      INSERT INTO players (team_id, name, sort_order)
      VALUES (?, ?, COALESCE((SELECT MAX(sort_order) + 1 FROM players WHERE team_id = ?), 0))
    `).run(params.teamId, body.name, params.teamId);
    const player = database.prepare('SELECT id, team_id, name, sort_order FROM players WHERE id = ?').get(result.lastInsertRowid) as PlayerRow;
    stateChanged();
    return reply.status(201).send(playerFromRow(player));
  });

  app.put('/api/admin/players/:id', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ id: positiveIdParameterSchema }), request.params);
    const body = parse(playerInputSchema, request.body);
    const result = database.prepare('UPDATE players SET name = ? WHERE id = ?').run(body.name, params.id);
    if (result.changes === 0) {
      throw new AppError(404, 'O jogador não existe.');
    }
    const player = database.prepare('SELECT id, team_id, name, sort_order FROM players WHERE id = ?').get(params.id) as PlayerRow;
    stateChanged();
    return playerFromRow(player);
  });

  app.delete('/api/admin/players/:id', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ id: positiveIdParameterSchema }), request.params);
    const result = database.prepare('DELETE FROM players WHERE id = ?').run(params.id);
    if (result.changes === 0) {
      throw new AppError(404, 'O jogador não existe.');
    }
    stateChanged();
    return replyEmpty();
  });

  app.get('/api/admin/calendar', { preHandler: requireAdmin }, async () => {
    return calendarSummary(getLeagueMatches(database));
  });

  app.post('/api/admin/calendar/generate-preview', { preHandler: requireAdmin }, async (request) => {
    const body = parse(z.object({ legs: calendarLegsSchema }), request.body);
    const teams = getTeamSummaries(database);
    const teamOrder = getGroups(database).flatMap((group) => shuffled(
      teams.filter((team) => team.group.id === group.id),
    ).map((team) => ({ teamId: team.id, groupId: group.id })));
    const generation = { legs: body.legs, teamOrder };
    const matches = generateRoundRobinSchedule(teamsForGeneration(teams, generation), generation.legs);
    if (matches.length === 0) {
      throw new AppError(409, 'São necessárias pelo menos duas equipas no mesmo grupo para gerar o calendário.');
    }
    return { generation, ...calendarSummary(matches) };
  });

  app.post('/api/admin/calendar/generate', { preHandler: requireAdmin }, async (request) => {
    const body = parse(calendarGenerationSaveSchema, request.body);
    const matchesToSave = generateRoundRobinSchedule(
      teamsForGeneration(getTeamSummaries(database), body.generation),
      body.generation.legs,
    );
    if (matchesToSave.length === 0) {
      throw new AppError(409, 'São necessárias pelo menos duas equipas no mesmo grupo para gerar o calendário.');
    }
    const hasScores = database.prepare('SELECT 1 FROM league_matches WHERE score_a IS NOT NULL LIMIT 1').get() !== undefined;
    if (hasScores) {
      requireConfirmation(body.confirmReplace, 'Já existem resultados registados. Confirme a substituição do calendário para eliminar esses resultados.');
    }
    database.transaction(() => {
      database.prepare('DELETE FROM league_matches').run();
      database.prepare('DELETE FROM league_rounds').run();
      const insertRound = database.prepare('INSERT INTO league_rounds (round_index) VALUES (?)');
      [...new Set(matchesToSave.map((match) => match.roundNumber))].forEach((roundNumber) => insertRound.run(roundNumber));
      const insert = database.prepare(`
        INSERT INTO league_matches (order_index, round_index, team_a_id, team_b_id, score_a, score_b)
        VALUES (?, ?, ?, ?, NULL, NULL)
      `);
      matchesToSave.forEach((match) => insert.run(
        match.gameNumber,
        match.roundNumber,
        match.teamA.id,
        match.teamB.id,
      ));
    })();
    stateChanged();
    return calendarSummary(getLeagueMatches(database));
  });

  app.delete('/api/admin/calendar', { preHandler: requireAdmin }, async (request) => {
    const body = parse(confirmationSchema, request.body ?? {});
    const hasMatches = database.prepare('SELECT 1 FROM league_matches LIMIT 1').get() !== undefined;
    if (hasMatches) {
      requireConfirmation(body.confirm, 'Confirme que pretende limpar o calendário e todos os seus resultados.');
      database.prepare('DELETE FROM league_matches').run();
      database.prepare('DELETE FROM league_rounds').run();
      stateChanged();
    }
    return replyEmpty();
  });

  app.put('/api/admin/matches/:id/result', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ id: positiveIdParameterSchema }), request.params);
    const body = parse(resultInputSchema, request.body);
    const result = database.prepare('UPDATE league_matches SET score_a = ?, score_b = ? WHERE id = ?').run(body.scoreA, body.scoreB, params.id);
    if (result.changes === 0) {
      throw new AppError(404, 'O jogo não existe.');
    }
    stateChanged();
    return getLeagueMatches(database).find((match) => match.id === params.id);
  });

  app.delete('/api/admin/matches/:id/result', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ id: positiveIdParameterSchema }), request.params);
    const result = database.prepare('UPDATE league_matches SET score_a = NULL, score_b = NULL WHERE id = ?').run(params.id);
    if (result.changes === 0) {
      throw new AppError(404, 'O jogo não existe.');
    }
    stateChanged();
    return replyEmpty();
  });

  app.put('/api/admin/rounds/:round/standings', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ round: positiveIdParameterSchema }), request.params);
    const body = parse(roundStandingsInputSchema, request.body);
    const result = database.prepare(`
      UPDATE league_rounds
      SET counts_toward_standings = ?
      WHERE round_index = ?
    `).run(body.countsTowardStandings ? 1 : 0, params.round);
    if (result.changes === 0) {
      throw new AppError(404, 'A jornada não existe.');
    }
    stateChanged();
    return { roundNumber: params.round, countsTowardStandings: body.countsTowardStandings };
  });

  app.get('/api/admin/final-stage', { preHandler: requireAdmin }, async () => getFinalStage(database));

  app.put('/api/admin/final-stage/config', { preHandler: requireAdmin }, async (request) => {
    const body = parse(finalConfigSchema, request.body);
    if (body.thirdPlaceEnabled && body.roundCount < 2) {
      throw new AppError(400, 'O jogo do 3.º lugar requer pelo menos duas rondas.');
    }
    const current = getSettings(database);
    const changed = current.finalRoundCount !== body.roundCount || current.thirdPlaceEnabled !== body.thirdPlaceEnabled;
    if (changed && current.finalRoundCount !== null) {
      requireConfirmation(body.confirmClearResults, 'Alterar a configuração elimina as equipas e os resultados da fase final. Confirme esta alteração.');
    }
    if (changed) {
      database.transaction(() => {
        database.prepare(`
          UPDATE tournament_settings
          SET final_round_count = ?, third_place_enabled = ?, updated_at = CURRENT_TIMESTAMP
          WHERE id = 1
        `).run(body.roundCount, body.thirdPlaceEnabled ? 1 : 0);
        database.prepare('DELETE FROM final_seeds').run();
        database.prepare('DELETE FROM final_match_results').run();
      })();
      stateChanged();
    }
    return getFinalStage(database);
  });

  app.delete('/api/admin/final-stage/config', { preHandler: requireAdmin }, async (request) => {
    const body = parse(confirmationSchema, request.body ?? {});
    const settings = getSettings(database);
    if (settings.finalRoundCount === null) {
      return getFinalStage(database);
    }
    requireConfirmation(body.confirm, 'Confirme que pretende limpar a configuração e todos os resultados da fase final.');
    database.transaction(() => {
      database.prepare(`
        UPDATE tournament_settings
        SET final_round_count = NULL, third_place_enabled = 0, updated_at = CURRENT_TIMESTAMP
        WHERE id = 1
      `).run();
      database.prepare('DELETE FROM final_seeds').run();
      database.prepare('DELETE FROM final_match_results').run();
    })();
    stateChanged();
    return getFinalStage(database);
  });

  app.post('/api/admin/final-stage/auto-seed-preview', { preHandler: requireAdmin }, async (request) => {
    const body = parse(autoSeedPreviewSchema, request.body);
    const settings = getSettings(database);
    if (settings.finalRoundCount === null) {
      throw new AppError(409, 'Configure primeiro o número de rondas da fase final.');
    }

    const tournamentState = getPublicState(database);
    const standings = tournamentState.groupStandings.filter((standing) => standing.rows.length > 0);
    if (standings.length === 0) {
      throw new AppError(409, 'Ainda não existem equipas classificadas para preencher a fase final.');
    }
    if (!standings.some((standing) => standing.rows.some((row) => row.played > 0))) {
      throw new AppError(409, 'Ainda não existem resultados contabilizados na classificação.');
    }
    if (tournamentState.matches.some(
      (match) => match.countsTowardStandings && (match.scoreA === null || match.scoreB === null),
    )) {
      throw new AppError(409, 'Conclua primeiro todos os jogos que contam para a classificação.');
    }

    const slotCount = 2 ** settings.finalRoundCount;
    if (body.mode === 'per-group') {
      const groupWithoutEnoughTeams = standings.find((standing) => standing.rows.length < body.qualifiersPerGroup);
      if (groupWithoutEnoughTeams) {
        throw new AppError(
          400,
          `${groupWithoutEnoughTeams.group.name} não tem ${body.qualifiersPerGroup} equipas para apurar.`,
        );
      }
      if (standings.length * body.qualifiersPerGroup > slotCount) {
        throw new AppError(400, `A fase final só tem ${slotCount} lugares. Reduza o número de apurados por grupo.`);
      }
      return buildGroupQualificationPreview(standings, body.qualifiersPerGroup, slotCount);
    }

    const classifiedTeamCount = standings.reduce((total, standing) => total + standing.rows.length, 0);
    if (body.qualifierCount > slotCount) {
      throw new AppError(400, `A fase final só tem ${slotCount} lugares. Reduza o número total de apurados.`);
    }
    if (body.qualifierCount > classifiedTeamCount) {
      throw new AppError(400, `Só existem ${classifiedTeamCount} equipas classificadas.`);
    }

    return buildOverallQualificationPreview(
      standings,
      body.qualifierCount,
      slotCount,
      tournamentState.tournament.classificationMode,
    );
  });

  app.put('/api/admin/final-stage/seeds', { preHandler: requireAdmin }, async (request) => {
    const body = parse(finalSeedsSchema, request.body);
    const settings = getSettings(database);
    const roundCount = settings.finalRoundCount;
    if (roundCount === null) {
      throw new AppError(409, 'Configure primeiro o número de rondas da fase final.');
    }
    const slotCount = 2 ** roundCount;
    const slotIndexes = new Set(body.seeds.map((seed) => seed.slotIndex));
    if (body.seeds.length !== slotCount || slotIndexes.size !== slotCount || [...slotIndexes].some((slot) => slot < 1 || slot > slotCount)) {
      throw new AppError(400, `Indique exatamente as ${slotCount} posições iniciais da fase final.`);
    }
    const assignedTeamIds = body.seeds.flatMap((seed) => seed.teamId === null ? [] : [seed.teamId]);
    if (new Set(assignedTeamIds).size !== assignedTeamIds.length) {
      throw new AppError(400, 'A mesma equipa não pode ser atribuída a mais do que uma posição.');
    }
    for (const teamId of assignedTeamIds) {
      assertExistingTeam(database, teamId);
    }

    const current = database.prepare('SELECT slot_index, team_id FROM final_seeds').all() as Array<{ slot_index: number; team_id: number | null }>;
    const currentBySlot = new Map(current.map((seed) => [seed.slot_index, seed.team_id]));
    const changed = body.seeds.some((seed) => (currentBySlot.get(seed.slotIndex) ?? null) !== seed.teamId) || current.length !== body.seeds.length;
    if (changed && finalResultExists(database)) {
      requireConfirmation(body.confirmClearResults, 'Alterar as equipas iniciais elimina todos os resultados da fase final. Confirme esta alteração.');
    }
    if (changed) {
      database.transaction(() => {
        database.prepare('DELETE FROM final_seeds').run();
        const insert = database.prepare('INSERT INTO final_seeds (slot_index, team_id) VALUES (?, ?)');
        body.seeds.forEach((seed) => insert.run(seed.slotIndex, seed.teamId));
        database.prepare('DELETE FROM final_match_results').run();
      })();
      stateChanged();
    }
    return getFinalStage(database, roundCount);
  });

  app.put('/api/admin/final-stage/matches/:round/:match/result', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ round: positiveIdParameterSchema, match: positiveIdParameterSchema }), request.params);
    const body = parse(resultInputSchema, request.body);
    if (body.scoreA === body.scoreB) {
      throw new AppError(400, 'Os jogos da fase final não podem terminar empatados.');
    }
    const settings = getSettings(database);
    const roundCount = settings.finalRoundCount;
    if (roundCount === null) {
      throw new AppError(409, 'A fase final ainda não está configurada.');
    }
    const before = getFinalStage(database, roundCount, settings.thirdPlaceEnabled);
    const match = getBracketMatch(before, params.round, params.match);
    if (!match) {
      throw new AppError(404, 'O jogo da fase final não existe.');
    }
    if (!match.teamA.team || !match.teamB.team || match.teamA.pending || match.teamB.pending) {
      throw new AppError(409, 'Só pode registar um resultado quando as duas equipas estiverem apuradas.');
    }
    const previousWinner = match.winner?.id ?? null;
    database.transaction(() => {
      database.prepare(`
        INSERT INTO final_match_results (round_index, match_index, score_a, score_b)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(round_index, match_index)
        DO UPDATE SET score_a = excluded.score_a, score_b = excluded.score_b
      `).run(params.round, params.match, body.scoreA, body.scoreB);
      clearInvalidatedFinalResults(
        database,
        roundCount,
        settings.thirdPlaceEnabled,
        params.round,
        params.match,
        previousWinner,
      );
    })();
    stateChanged();
    return getFinalStage(database, roundCount);
  });

  app.delete('/api/admin/final-stage/matches/:round/:match/result', { preHandler: requireAdmin }, async (request) => {
    const params = parse(z.object({ round: positiveIdParameterSchema, match: positiveIdParameterSchema }), request.params);
    const settings = getSettings(database);
    const roundCount = settings.finalRoundCount;
    if (roundCount === null) {
      throw new AppError(409, 'A fase final ainda não está configurada.');
    }
    const before = getFinalStage(database, roundCount, settings.thirdPlaceEnabled);
    const match = getBracketMatch(before, params.round, params.match);
    if (!match) {
      throw new AppError(404, 'O jogo da fase final não existe.');
    }
    const previousWinner = match.winner?.id ?? null;
    database.transaction(() => {
      database.prepare('DELETE FROM final_match_results WHERE round_index = ? AND match_index = ?').run(params.round, params.match);
      clearInvalidatedFinalResults(
        database,
        roundCount,
        settings.thirdPlaceEnabled,
        params.round,
        params.match,
        previousWinner,
      );
    })();
    stateChanged();
    return getFinalStage(database, roundCount);
  });

  app.get('/api/public/state', async () => getPublicState(database));

  app.get('/api/public/events', async (request, reply) => {
    reply.hijack();
    reply.raw.writeHead(200, {
      'Content-Type': 'text/event-stream; charset=utf-8',
      'Cache-Control': 'no-cache, no-transform',
      Connection: 'keep-alive',
      'X-Accel-Buffering': 'no',
    });
    events.add(reply.raw);
    request.raw.on('close', () => events.remove(reply.raw));
  });

  const staticRoot = options.staticRoot ?? process.env.CLIENT_DIST_PATH ?? resolve(process.cwd(), 'dist', 'client');
  if (existsSync(join(staticRoot, 'index.html'))) {
    await app.register(fastifyStatic, { root: staticRoot, prefix: '/' });
    const sendClientApplication = async (_request: FastifyRequest, reply: FastifyReply) => reply.sendFile('index.html');
    app.get('/results', sendClientApplication);
    app.get('/display', sendClientApplication);
    app.get('/display/', sendClientApplication);
    app.get('/admin', sendClientApplication);
    app.get('/admin/*', sendClientApplication);
  }

  app.addHook('onClose', async () => {
    events.close();
    if (ownsDatabase) {
      database.close();
    }
  });

  return app;
}

function replyEmpty(): { ok: true } {
  return { ok: true };
}
