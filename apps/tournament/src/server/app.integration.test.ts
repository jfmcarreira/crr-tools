import type { FastifyInstance } from 'fastify';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import type {
  CalendarGeneration,
  CalendarGenerationPreview,
  CalendarResponse,
  FinalSeedPreview,
  FinalStage,
  Group,
  LeagueMatch,
  PublicTournamentState,
  Team,
} from '../shared/types/tournament.js';
import { SESSION_COOKIE_NAME } from './auth.js';
import { createApp } from './app.js';

const authentication = {
  adminPassword: 'integration-test-password',
  sessionSecret: 'integration-test-session-secret',
};

let app: FastifyInstance | undefined;

function testApp(): FastifyInstance {
  if (!app) {
    throw new Error('The test application has not been created.');
  }
  return app;
}

async function login(): Promise<string> {
  const response = await testApp().inject({
    method: 'POST',
    url: '/api/auth/login',
    payload: { password: authentication.adminPassword },
  });

  expect(response.statusCode).toBe(200);
  expect(response.json()).toEqual({ authenticated: true });
  const session = response.cookies.find((cookie) => cookie.name === SESSION_COOKIE_NAME);
  if (!session) {
    throw new Error('The login response did not set a session cookie.');
  }
  return `${SESSION_COOKIE_NAME}=${session.value}`;
}

async function createTeam(session: string, number: number, name: string, groupId?: number): Promise<Team> {
  if (groupId === undefined) {
    const groupsResponse = await testApp().inject({
      method: 'GET',
      url: '/api/admin/groups',
      headers: { cookie: session },
    });
    expect(groupsResponse.statusCode).toBe(200);
    const [defaultGroup] = groupsResponse.json<Group[]>();
    groupId = defaultGroup.id;
  }
  const response = await testApp().inject({
    method: 'POST',
    url: '/api/admin/teams',
    headers: { cookie: session },
    payload: { number, name, groupId },
  });

  expect(response.statusCode).toBe(201);
  return response.json<Team>();
}

async function generatePreview(session: string, legs: 1 | 2): Promise<CalendarGenerationPreview> {
  const response = await testApp().inject({
    method: 'POST',
    url: '/api/admin/calendar/generate-preview',
    headers: { cookie: session },
    payload: { legs },
  });
  expect(response.statusCode).toBe(200);
  return response.json<CalendarGenerationPreview>();
}

async function saveGeneration(
  session: string,
  generation: CalendarGeneration,
  confirmReplace = false,
): Promise<CalendarResponse> {
  const response = await testApp().inject({
    method: 'POST',
    url: '/api/admin/calendar/generate',
    headers: { cookie: session },
    payload: { generation, ...(confirmReplace ? { confirmReplace: true } : {}) },
  });
  expect(response.statusCode).toBe(200);
  return response.json<CalendarResponse>();
}

async function includeRoundInStandings(session: string, roundNumber: number): Promise<void> {
  const response = await testApp().inject({
    method: 'PUT',
    url: `/api/admin/rounds/${roundNumber}/standings`,
    headers: { cookie: session },
    payload: { countsTowardStandings: true },
  });
  expect(response.statusCode).toBe(200);
  expect(response.json()).toEqual({ roundNumber, countsTowardStandings: true });
}

type SchedulableMatch = Pick<LeagueMatch, 'gameNumber' | 'roundNumber' | 'group' | 'teamA' | 'teamB'>;

function scheduleOf(matches: readonly SchedulableMatch[]) {
  return matches.map((match) => ({
    gameNumber: match.gameNumber,
    roundNumber: match.roundNumber,
    groupId: match.group?.id ?? null,
    teamAId: match.teamA.id,
    teamBId: match.teamB.id,
  }));
}

function unorderedPair(teamAId: number, teamBId: number): string {
  return [teamAId, teamBId].sort((first, second) => first - second).join('-');
}

async function readStreamChunk(reader: ReadableStreamDefaultReader<Uint8Array>): Promise<string> {
  let timeout: ReturnType<typeof setTimeout> | undefined;
  try {
    const result = await Promise.race([
      reader.read(),
      new Promise<never>((_resolve, reject) => {
        timeout = setTimeout(() => reject(new Error('Timed out waiting for the SSE event.')), 2_000);
      }),
    ]);
    return new TextDecoder().decode(result.value);
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

describe('tournament manager HTTP API', () => {
  beforeEach(async () => {
    app = await createApp({
      databasePath: ':memory:',
      authentication,
      basePath: '/jogo/',
    });
    await app.ready();
  });

  afterEach(async () => {
    if (app) {
      await app.close();
      app = undefined;
    }
  });

  it('rejects unauthenticated administration and accepts only the configured login password', async () => {
    const unauthenticated = await testApp().inject({
      method: 'GET',
      url: '/api/admin/teams',
    });
    expect(unauthenticated.statusCode).toBe(401);
    expect(unauthenticated.json()).toEqual({ error: expect.any(String) });

    const invalidLogin = await testApp().inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { password: 'incorrect-password' },
    });
    expect(invalidLogin.statusCode).toBe(401);
    expect(invalidLogin.json()).toEqual({ error: expect.any(String) });

    const session = await login();
    const authenticatedSession = await testApp().inject({
      method: 'GET',
      url: '/api/auth/session',
      headers: { cookie: session },
    });
    expect(authenticatedSession.statusCode).toBe(200);
    expect(authenticatedSession.json()).toEqual({ authenticated: true });
  });

  it('scopes the administration session cookie to the deployment path', async () => {
    const response = await testApp().inject({
      method: 'POST',
      url: '/api/auth/login',
      payload: { password: authentication.adminPassword },
    });

    expect(response.statusCode).toBe(200);
    expect(response.headers['set-cookie']).toContain('Path=/jogo/');
  });

  it('publishes the admin-selected panel and zoom to the public display state', async () => {
    const initialPublicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(initialPublicState.statusCode).toBe(200);
    expect(initialPublicState.json<PublicTournamentState>().display).toEqual({ activePanel: 'latest-results', zoomPercent: 100 });

    const unauthenticated = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/display',
      payload: { activePanel: 'classification', zoomPercent: 137 },
    });
    expect(unauthenticated.statusCode).toBe(401);

    const session = await login();
    const invalid = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/display',
      headers: { cookie: session },
      payload: { activePanel: 'unknown-panel', zoomPercent: 137 },
    });
    expect(invalid.statusCode).toBe(400);

    const invalidZoom = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/display',
      headers: { cookie: session },
      payload: { activePanel: 'classification', zoomPercent: 401 },
    });
    expect(invalidZoom.statusCode).toBe(400);

    const updated = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/display',
      headers: { cookie: session },
      payload: { activePanel: 'classification', zoomPercent: 137 },
    });
    expect(updated.statusCode).toBe(200);
    expect(updated.json()).toEqual({ activePanel: 'classification', zoomPercent: 137 });

    const adminSettings = await testApp().inject({
      method: 'GET',
      url: '/api/admin/display',
      headers: { cookie: session },
    });
    expect(adminSettings.statusCode).toBe(200);
    expect(adminSettings.json()).toEqual({ activePanel: 'classification', zoomPercent: 137 });

    const publicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(publicState.statusCode).toBe(200);
    expect(publicState.json<PublicTournamentState>().display).toEqual({ activePanel: 'classification', zoomPercent: 137 });
  });

  it('notifies connected displays when the selected panel changes', async () => {
    const session = await login();
    await testApp().listen({ host: '127.0.0.1', port: 0 });
    const address = testApp().server.address();
    if (!address || typeof address === 'string') throw new Error('The test server did not expose a TCP address.');

    const controller = new AbortController();
    const response = await fetch(`http://127.0.0.1:${address.port}/api/public/events`, { signal: controller.signal });
    expect(response.status).toBe(200);
    const reader = response.body?.getReader();
    if (!reader) throw new Error('The SSE response did not expose a readable stream.');

    try {
      expect(await readStreamChunk(reader)).toContain('retry: 3000');

      const updated = await testApp().inject({
        method: 'PUT',
        url: '/api/admin/display',
        headers: { cookie: session },
        payload: { activePanel: 'classification', zoomPercent: 137 },
      });
      expect(updated.statusCode).toBe(200);
      expect(await readStreamChunk(reader)).toContain('event: state-changed');
    } finally {
      await reader.cancel();
      controller.abort();
    }
  });

  it('creates teams in Grupo A and rejects globally duplicated team numbers', async () => {
    const session = await login();
    const created = await createTeam(session, 10, 'Falcons');
    expect(created).toMatchObject({
      id: expect.any(Number),
      number: 10,
      name: 'Falcons',
      group: expect.objectContaining({ id: expect.any(Number), name: 'Grupo A', sortOrder: 0 }),
      players: [],
    });

    const createdGroup = await testApp().inject({
      method: 'POST',
      url: '/api/admin/groups',
      headers: { cookie: session },
      payload: { name: 'Grupo B' },
    });
    expect(createdGroup.statusCode).toBe(201);
    const groupB = createdGroup.json<Group>();

    const duplicate = await testApp().inject({
      method: 'POST',
      url: '/api/admin/teams',
      headers: { cookie: session },
      payload: { number: 10, name: 'Duplicate Falcons', groupId: groupB.id },
    });
    expect(duplicate.statusCode).toBe(409);
    expect(duplicate.json()).toEqual({ error: expect.any(String) });

    const moved = await testApp().inject({
      method: 'PUT',
      url: `/api/admin/teams/${created.id}`,
      headers: { cookie: session },
      payload: { number: 10, name: 'Falcons', groupId: groupB.id },
    });
    expect(moved.statusCode).toBe(200);
    expect(moved.json<Team>()).toMatchObject({ id: created.id, group: groupB });

    const withoutGroup = await testApp().inject({
      method: 'POST',
      url: '/api/admin/teams',
      headers: { cookie: session },
      payload: { number: 11, name: 'No Group' },
    });
    expect(withoutGroup.statusCode).toBe(400);

    const unknownGroup = await testApp().inject({
      method: 'POST',
      url: '/api/admin/teams',
      headers: { cookie: session },
      payload: { number: 11, name: 'Unknown Group', groupId: 99_999 },
    });
    expect(unknownGroup.statusCode).toBe(404);
  });

  it('assigns the next team number when creating a team without one', async () => {
    const session = await login();
    const groupsResponse = await testApp().inject({
      method: 'GET',
      url: '/api/admin/groups',
      headers: { cookie: session },
    });
    const [group] = groupsResponse.json<Group[]>();

    const first = await testApp().inject({
      method: 'POST',
      url: '/api/admin/teams',
      headers: { cookie: session },
      payload: { name: 'Primeira', groupId: group.id },
    });
    const second = await testApp().inject({
      method: 'POST',
      url: '/api/admin/teams',
      headers: { cookie: session },
      payload: { name: 'Segunda', groupId: group.id },
    });

    expect(first.statusCode).toBe(201);
    expect(first.json<Team>()).toMatchObject({ number: 1, name: 'Primeira' });
    expect(second.statusCode).toBe(201);
    expect(second.json<Team>()).toMatchObject({ number: 2, name: 'Segunda' });
  });

  it('manages groups and prevents deleting nonempty or final groups', async () => {
    const session = await login();
    const initial = await testApp().inject({
      method: 'GET',
      url: '/api/admin/groups',
      headers: { cookie: session },
    });
    expect(initial.statusCode).toBe(200);
    const [groupA] = initial.json<Group[]>();
    expect(groupA).toMatchObject({ name: 'Grupo A' });

    const emptyName = await testApp().inject({
      method: 'POST',
      url: '/api/admin/groups',
      headers: { cookie: session },
      payload: { name: '  ' },
    });
    expect(emptyName.statusCode).toBe(400);

    const created = await testApp().inject({
      method: 'POST',
      url: '/api/admin/groups',
      headers: { cookie: session },
      payload: { name: 'Grupo B' },
    });
    expect(created.statusCode).toBe(201);
    const groupB = created.json<Group>();

    const duplicate = await testApp().inject({
      method: 'POST',
      url: '/api/admin/groups',
      headers: { cookie: session },
      payload: { name: 'grupo b' },
    });
    expect(duplicate.statusCode).toBe(409);

    const renamed = await testApp().inject({
      method: 'PUT',
      url: `/api/admin/groups/${groupB.id}`,
      headers: { cookie: session },
      payload: { name: 'Grupo Norte' },
    });
    expect(renamed.statusCode).toBe(200);
    expect(renamed.json<Group>()).toEqual({ id: groupB.id, name: 'Grupo Norte', sortOrder: groupB.sortOrder });

    const deleted = await testApp().inject({
      method: 'DELETE',
      url: `/api/admin/groups/${groupB.id}`,
      headers: { cookie: session },
    });
    expect(deleted.statusCode).toBe(200);

    const finalGroup = await testApp().inject({
      method: 'DELETE',
      url: `/api/admin/groups/${groupA.id}`,
      headers: { cookie: session },
    });
    expect(finalGroup.statusCode).toBe(409);
    expect(finalGroup.json()).toEqual({ error: 'Não é possível eliminar o último grupo.' });

    const anotherGroup = await testApp().inject({
      method: 'POST',
      url: '/api/admin/groups',
      headers: { cookie: session },
      payload: { name: 'Grupo Sul' },
    });
    expect(anotherGroup.statusCode).toBe(201);

    await createTeam(session, 1, 'Lions');
    const nonempty = await testApp().inject({
      method: 'DELETE',
      url: `/api/admin/groups/${groupA.id}`,
      headers: { cookie: session },
    });
    expect(nonempty.statusCode).toBe(409);
    expect(nonempty.json()).toEqual({ error: 'Não é possível eliminar um grupo com equipas.' });
  });

  it('previews and saves the exact one-leg schedule for four teams', async () => {
    const session = await login();
    const teams = [
      await createTeam(session, 1, 'Lions'),
      await createTeam(session, 2, 'Tigers'),
      await createTeam(session, 3, 'Bears'),
      await createTeam(session, 4, 'Wolves'),
    ];

    const preview = await generatePreview(session, 1);
    expect(preview).toMatchObject({ matchCount: 6, roundCount: 3 });
    expect(preview.generation.legs).toBe(1);
    expect([...preview.generation.teamOrder].sort((first, second) => first.teamId - second.teamId)).toEqual(
      teams
        .map((team) => ({ teamId: team.id, groupId: team.group.id }))
        .sort((first, second) => first.teamId - second.teamId),
    );

    const [firstId, secondId, thirdId, fourthId] = preview.generation.teamOrder.map(({ teamId }) => teamId);
    const groupId = teams[0].group.id;
    expect(scheduleOf(preview.matches)).toEqual([
      { gameNumber: 1, roundNumber: 1, groupId, teamAId: firstId, teamBId: fourthId },
      { gameNumber: 2, roundNumber: 1, groupId, teamAId: secondId, teamBId: thirdId },
      { gameNumber: 3, roundNumber: 2, groupId, teamAId: thirdId, teamBId: firstId },
      { gameNumber: 4, roundNumber: 2, groupId, teamAId: fourthId, teamBId: secondId },
      { gameNumber: 5, roundNumber: 3, groupId, teamAId: firstId, teamBId: secondId },
      { gameNumber: 6, roundNumber: 3, groupId, teamAId: thirdId, teamBId: fourthId },
    ]);

    const expectedPairs = teams.flatMap((team, index) => (
      teams.slice(index + 1).map((opponent) => unorderedPair(team.id, opponent.id))
    )).sort();
    expect(preview.matches.map((match) => unorderedPair(match.teamA.id, match.teamB.id)).sort()).toEqual(expectedPairs);
    for (const roundNumber of [1, 2, 3]) {
      const participants = preview.matches
        .filter((match) => match.roundNumber === roundNumber)
        .flatMap((match) => [match.teamA.id, match.teamB.id]);
      expect(new Set(participants).size).toBe(participants.length);
    }

    const saved = await saveGeneration(session, preview.generation);
    expect(saved).toMatchObject({ matchCount: 6, roundCount: 3 });
    expect(scheduleOf(saved.matches)).toEqual(scheduleOf(preview.matches));
    expect(saved.matches.every((match) => match.scoreA === null && match.scoreB === null)).toBe(true);

    const persisted = await testApp().inject({
      method: 'GET',
      url: '/api/admin/calendar',
      headers: { cookie: session },
    });
    expect(persisted.statusCode).toBe(200);
    expect(persisted.json<CalendarResponse>()).toEqual(saved);
  });

  it('rejects generation when no group can produce a match', async () => {
    const session = await login();
    await createTeam(session, 1, 'Only team');

    const response = await testApp().inject({
      method: 'POST',
      url: '/api/admin/calendar/generate-preview',
      headers: { cookie: session },
      payload: { legs: 1 },
    });

    expect(response.statusCode).toBe(409);
    expect(response.json()).toEqual({
      error: 'São necessárias pelo menos duas equipas no mesmo grupo para gerar o calendário.',
    });
  });

  it('keeps a round out of the standings until an administrator enables it', async () => {
    const session = await login();
    await createTeam(session, 1, 'Lions');
    await createTeam(session, 2, 'Tigers');
    const preview = await generatePreview(session, 1);
    const [match] = (await saveGeneration(session, preview.generation)).matches;
    expect(match.countsTowardStandings).toBe(false);

    const result = await testApp().inject({
      method: 'PUT',
      url: `/api/admin/matches/${match.id}/result`,
      headers: { cookie: session },
      payload: { scoreA: 4, scoreB: 1 },
    });
    expect(result.statusCode).toBe(200);
    expect(result.json<LeagueMatch>()).toMatchObject({
      id: match.id,
      scoreA: 4,
      scoreB: 1,
    });

    const publicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(publicState.statusCode).toBe(200);
    const disabledState = publicState.json<PublicTournamentState>();
    expect(disabledState.matches).toEqual([
      expect.objectContaining({ id: match.id, scoreA: 4, scoreB: 1, countsTowardStandings: false }),
    ]);
    expect(disabledState.groupStandings[0].rows).toEqual(expect.arrayContaining([
      expect.objectContaining({ team: expect.objectContaining({ id: match.teamA.id }), played: 0, points: 0 }),
      expect.objectContaining({ team: expect.objectContaining({ id: match.teamB.id }), played: 0, points: 0 }),
    ]));

    await includeRoundInStandings(session, match.roundNumber);

    const enabledPublicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(enabledPublicState.statusCode).toBe(200);
    expect(enabledPublicState.json<PublicTournamentState>()).toMatchObject({
      matches: [expect.objectContaining({ id: match.id, countsTowardStandings: true })],
      groupStandings: [{
        group: expect.objectContaining({ name: 'Grupo A' }),
        rows: [
          expect.objectContaining({
            position: 1,
            team: expect.objectContaining({ id: match.teamA.id }),
            played: 1,
            wins: 1,
            draws: 0,
            losses: 0,
            goalsFor: 4,
            goalsAgainst: 1,
            goalDifference: 3,
            points: 3,
          }),
          expect.objectContaining({
            position: 2,
            team: expect.objectContaining({ id: match.teamB.id }),
            played: 1,
            wins: 0,
            draws: 0,
            losses: 1,
            goalsFor: 1,
            goalsAgainst: 4,
            goalDifference: -3,
            points: 0,
          }),
        ],
      }],
    });
  });

  it('ranks total game points and resolves equal totals by the direct match', async () => {
    const session = await login();
    const teamA = await createTeam(session, 1, 'Lions');
    const teamB = await createTeam(session, 2, 'Tigers');
    const teamC = await createTeam(session, 3, 'Bears');
    const preview = await generatePreview(session, 1);
    const calendar = await saveGeneration(session, preview.generation);
    for (const roundNumber of new Set(calendar.matches.map((match) => match.roundNumber))) {
      await includeRoundInStandings(session, roundNumber);
    }

    const settings = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/settings',
      headers: { cookie: session },
      payload: { name: 'Torneio', classificationMode: 'total-points' },
    });
    expect(settings.statusCode).toBe(200);
    expect(settings.json()).toMatchObject({ classificationMode: 'total-points' });

    const results = [
      { teams: [teamA, teamB], scores: new Map([[teamA.id, 1], [teamB.id, 0]]) },
      { teams: [teamA, teamC], scores: new Map([[teamA.id, 4], [teamC.id, 10]]) },
      { teams: [teamB, teamC], scores: new Map([[teamB.id, 5], [teamC.id, 0]]) },
    ];
    for (const expected of results) {
      const pair = unorderedPair(expected.teams[0].id, expected.teams[1].id);
      const match = calendar.matches.find((candidate) => (
        unorderedPair(candidate.teamA.id!, candidate.teamB.id!) === pair
      ));
      expect(match).toBeDefined();
      const response = await testApp().inject({
        method: 'PUT',
        url: `/api/admin/matches/${match!.id}/result`,
        headers: { cookie: session },
        payload: {
          scoreA: expected.scores.get(match!.teamA.id!)!,
          scoreB: expected.scores.get(match!.teamB.id!)!,
        },
      });
      expect(response.statusCode).toBe(200);
    }

    const publicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(publicState.statusCode).toBe(200);
    const state = publicState.json<PublicTournamentState>();
    expect(state.tournament.classificationMode).toBe('total-points');
    expect(state.groupStandings[0].rows.map((row) => ({
      teamId: row.team.id,
      points: row.points,
      goalDifference: row.goalDifference,
    }))).toEqual([
      { teamId: teamC.id, points: 10, goalDifference: 1 },
      { teamId: teamA.id, points: 5, goalDifference: -5 },
      { teamId: teamB.id, points: 5, goalDifference: 4 },
    ]);
  });

  it('generates only intra-group games with persisted rounds and aligned public classifications', async () => {
    const session = await login();
    const groups = await testApp().inject({
      method: 'GET',
      url: '/api/admin/groups',
      headers: { cookie: session },
    });
    const [groupA] = groups.json<Group[]>();
    const createdGroup = await testApp().inject({
      method: 'POST',
      url: '/api/admin/groups',
      headers: { cookie: session },
      payload: { name: 'Grupo B' },
    });
    const groupB = createdGroup.json<Group>();
    const groupATeams = [
      await createTeam(session, 1, 'Lions', groupA.id),
      await createTeam(session, 2, 'Tigers', groupA.id),
      await createTeam(session, 3, 'Bears', groupA.id),
    ];
    const groupBTeams = [
      await createTeam(session, 4, 'Wolves', groupB.id),
      await createTeam(session, 5, 'Eagles', groupB.id),
    ];
    const allTeams = [...groupATeams, ...groupBTeams];

    const preview = await generatePreview(session, 1);
    expect(preview).toMatchObject({ matchCount: 4, roundCount: 3 });
    expect(preview.matches.map((match) => match.roundNumber)).toEqual([1, 1, 2, 3]);
    expect(preview.matches.every((match) => (
      match.group.id === match.teamA.group.id && match.group.id === match.teamB.group.id
    ))).toBe(true);

    const expectedPairs = [groupATeams, groupBTeams].flatMap((groupTeams) => (
      groupTeams.flatMap((team, index) => (
        groupTeams.slice(index + 1).map((opponent) => unorderedPair(team.id, opponent.id))
      ))
    )).sort();
    expect(preview.matches.map((match) => unorderedPair(match.teamA.id, match.teamB.id)).sort()).toEqual(expectedPairs);

    const calendar = await saveGeneration(session, preview.generation);
    expect(scheduleOf(calendar.matches)).toEqual(scheduleOf(preview.matches));
    for (const roundNumber of new Set(calendar.matches.map((match) => match.roundNumber))) {
      await includeRoundInStandings(session, roundNumber);
    }

    const attemptedReassignment = await testApp().inject({
      method: 'PUT',
      url: `/api/admin/teams/${groupATeams[0].id}`,
      headers: { cookie: session },
      payload: { number: groupATeams[0].number, name: groupATeams[0].name, groupId: groupB.id },
    });
    expect(attemptedReassignment.statusCode).toBe(409);
    expect(attemptedReassignment.json()).toEqual({
      error: 'Não é possível alterar o grupo de uma equipa utilizada no calendário. Limpe ou substitua o calendário primeiro.',
    });

    for (const match of calendar.matches) {
      const result = await testApp().inject({
        method: 'PUT',
        url: `/api/admin/matches/${match.id}/result`,
        headers: { cookie: session },
        payload: { scoreA: 2, scoreB: 0 },
      });
      expect(result.statusCode).toBe(200);
    }

    const publicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(publicState.statusCode).toBe(200);
    const state = publicState.json<PublicTournamentState>();
    expect(state.groups).toEqual([groupA, groupB]);
    expect(scheduleOf(state.matches)).toEqual(scheduleOf(calendar.matches));
    expect(state.matches.every((match) => match.scoreA === 2 && match.scoreB === 0)).toBe(true);

    for (const standing of state.groupStandings) {
      const groupTeams = allTeams.filter((team) => team.group.id === standing.group.id);
      const groupMatches = state.matches.filter((match) => match.group?.id === standing.group.id);
      expect(standing.rows.map((row) => row.team.id).sort((first, second) => first - second)).toEqual(
        groupTeams.map((team) => team.id).sort((first, second) => first - second),
      );
      for (const row of standing.rows) {
        const wins = groupMatches.filter((match) => match.teamA.id === row.team.id).length;
        const losses = groupMatches.filter((match) => match.teamB.id === row.team.id).length;
        expect(row).toMatchObject({
          played: wins + losses,
          wins,
          draws: 0,
          losses,
          goalsFor: wins * 2,
          goalsAgainst: losses * 2,
          goalDifference: (wins - losses) * 2,
          points: wins * 3,
        });
      }
      expect(standing.rows.reduce((total, row) => total + row.played, 0)).toBe(groupMatches.length * 2);
    }
  });

  it('previews a second leg that exactly mirrors the first with reversed venues', async () => {
    const session = await login();
    await createTeam(session, 1, 'Lions');
    await createTeam(session, 2, 'Tigers');
    await createTeam(session, 3, 'Bears');
    await createTeam(session, 4, 'Wolves');

    const preview = await generatePreview(session, 2);
    expect(preview).toMatchObject({ matchCount: 12, roundCount: 6 });
    expect(preview.generation.legs).toBe(2);

    const firstLegMatchCount = preview.matchCount / 2;
    const roundOffset = preview.roundCount / 2;
    const firstLeg = preview.matches.slice(0, firstLegMatchCount);
    const secondLeg = preview.matches.slice(firstLegMatchCount);
    expect(scheduleOf(secondLeg)).toEqual(firstLeg.map((match, index) => ({
      gameNumber: firstLegMatchCount + index + 1,
      roundNumber: match.roundNumber + roundOffset,
      groupId: match.group.id,
      teamAId: match.teamB.id,
      teamBId: match.teamA.id,
    })));
  });

  it('rejects tampered and stale calendar generation descriptors', async () => {
    const session = await login();
    await createTeam(session, 1, 'Lions');
    await createTeam(session, 2, 'Tigers');
    await createTeam(session, 3, 'Bears');
    await createTeam(session, 4, 'Wolves');
    const preview = await generatePreview(session, 1);

    const tamperedTeamOrder = preview.generation.teamOrder.map((entry, index) => (
      index === 1 ? { ...entry, ...preview.generation.teamOrder[0] } : entry
    ));
    const tampered = await testApp().inject({
      method: 'POST',
      url: '/api/admin/calendar/generate',
      headers: { cookie: session },
      payload: { generation: { ...preview.generation, teamOrder: tamperedTeamOrder } },
    });
    expect(tampered.statusCode).toBe(409);
    expect(tampered.json()).toEqual({
      error: 'As equipas ou os grupos foram alterados. Sorteie novamente o calendário.',
    });

    await createTeam(session, 5, 'Eagles');
    const stale = await testApp().inject({
      method: 'POST',
      url: '/api/admin/calendar/generate',
      headers: { cookie: session },
      payload: { generation: preview.generation },
    });
    expect(stale.statusCode).toBe(409);
    expect(stale.json()).toEqual({ error: 'As equipas foram alteradas. Sorteie novamente o calendário.' });
  });

  it('requires confirmation to replace a scored calendar and clears scores when confirmed', async () => {
    const session = await login();
    await createTeam(session, 1, 'Lions');
    await createTeam(session, 2, 'Tigers');
    await createTeam(session, 3, 'Bears');
    await createTeam(session, 4, 'Wolves');

    const initialPreview = await generatePreview(session, 1);
    const initialCalendar = await saveGeneration(session, initialPreview.generation);
    const scoredMatch = initialCalendar.matches[0];
    const result = await testApp().inject({
      method: 'PUT',
      url: `/api/admin/matches/${scoredMatch.id}/result`,
      headers: { cookie: session },
      payload: { scoreA: 3, scoreB: 1 },
    });
    expect(result.statusCode).toBe(200);

    const replacementPreview = await generatePreview(session, 1);
    const unconfirmed = await testApp().inject({
      method: 'POST',
      url: '/api/admin/calendar/generate',
      headers: { cookie: session },
      payload: { generation: replacementPreview.generation },
    });
    expect(unconfirmed.statusCode).toBe(409);
    expect(unconfirmed.json()).toEqual({
      error: 'Já existem resultados registados. Confirme a substituição do calendário para eliminar esses resultados.',
    });

    const unchanged = await testApp().inject({
      method: 'GET',
      url: '/api/admin/calendar',
      headers: { cookie: session },
    });
    expect(unchanged.statusCode).toBe(200);
    expect(unchanged.json<CalendarResponse>().matches.find((match) => match.id === scoredMatch.id)).toMatchObject({
      scoreA: 3,
      scoreB: 1,
    });

    const replaced = await saveGeneration(session, replacementPreview.generation, true);
    expect(scheduleOf(replaced.matches)).toEqual(scheduleOf(replacementPreview.matches));
    expect(replaced.matches.every((match) => match.scoreA === null && match.scoreB === null)).toBe(true);
  });

  it('randomizes existing team numbers and group assignments after confirmation', async () => {
    const session = await login();
    const groupsResponse = await testApp().inject({
      method: 'GET',
      url: '/api/admin/groups',
      headers: { cookie: session },
    });
    const [groupA] = groupsResponse.json<Group[]>();
    const groupBResponse = await testApp().inject({
      method: 'POST',
      url: '/api/admin/groups',
      headers: { cookie: session },
      payload: { name: 'Grupo B' },
    });
    const groupB = groupBResponse.json<Group>();
    const teams = await Promise.all([
      createTeam(session, 11, 'Lions'),
      createTeam(session, 24, 'Tigers'),
      createTeam(session, 37, 'Bears'),
    ]);
    const preview = await generatePreview(session, 1);
    const scheduled = await saveGeneration(session, preview.generation);
    expect(scheduled.matches.length).toBeGreaterThan(0);

    const unconfirmed = await testApp().inject({
      method: 'POST',
      url: '/api/admin/teams/randomize',
      headers: { cookie: session },
      payload: {},
    });
    expect(unconfirmed.statusCode).toBe(409);

    const randomized = await testApp().inject({
      method: 'POST',
      url: '/api/admin/teams/randomize',
      headers: { cookie: session },
      payload: { confirm: true },
    });
    expect(randomized.statusCode).toBe(200);
    const result = randomized.json<{ teams: Team[]; calendarCleared: boolean }>();
    expect(result.calendarCleared).toBe(true);
    expect(result.teams.map((team) => team.number).sort((a, b) => a - b)).toEqual([11, 24, 37]);
    expect(new Set(result.teams.map((team) => team.number)).size).toBe(3);
    expect(result.teams.map((team) => team.id).sort((a, b) => a - b)).toEqual(teams.map((team) => team.id).sort((a, b) => a - b));
    expect(result.teams.map((team) => team.group.id)).toEqual(expect.arrayContaining([groupA.id, groupB.id]));
    expect(Math.abs(
      result.teams.filter((team) => team.group.id === groupA.id).length -
      result.teams.filter((team) => team.group.id === groupB.id).length,
    )).toBeLessThanOrEqual(1);

    const calendar = await testApp().inject({
      method: 'GET',
      url: '/api/admin/calendar',
      headers: { cookie: session },
    });
    expect(calendar.json<CalendarResponse>().matches).toEqual([]);
  });

  it('configures and advances a final stage that is exposed through public state', async () => {
    const session = await login();
    const lions = await createTeam(session, 1, 'Lions');
    const tigers = await createTeam(session, 2, 'Tigers');
    const bears = await createTeam(session, 3, 'Bears');
    const wolves = await createTeam(session, 4, 'Wolves');

    const invalidThirdPlace = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/config',
      headers: { cookie: session },
      payload: { roundCount: 1, thirdPlaceEnabled: true },
    });
    expect(invalidThirdPlace.statusCode).toBe(400);
    expect(invalidThirdPlace.json()).toEqual({ error: 'O jogo do 3.º lugar requer pelo menos duas rondas.' });

    const configured = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/config',
      headers: { cookie: session },
      payload: { roundCount: 2, thirdPlaceEnabled: true },
    });
    expect(configured.statusCode).toBe(200);
    expect(configured.json<FinalStage>()).toMatchObject({
      roundCount: 2,
      thirdPlaceEnabled: true,
      champion: null,
      rounds: [
        { roundIndex: 1, name: 'Meias-finais', matches: [{ matchIndex: 1 }, { matchIndex: 2 }] },
        { roundIndex: 2, name: 'Final', matches: [{ matchIndex: 1 }] },
      ],
      thirdPlaceMatch: { matchIndex: 2 },
    });

    const seeded = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/seeds',
      headers: { cookie: session },
      payload: {
        seeds: [
          { slotIndex: 1, teamId: lions.id },
          { slotIndex: 2, teamId: tigers.id },
          { slotIndex: 3, teamId: bears.id },
          { slotIndex: 4, teamId: wolves.id },
        ],
      },
    });
    expect(seeded.statusCode).toBe(200);
    expect(seeded.json<FinalStage>().rounds[0].matches).toMatchObject([
      { teamA: { team: { id: lions.id } }, teamB: { team: { id: tigers.id } } },
      { teamA: { team: { id: bears.id } }, teamB: { team: { id: wolves.id } } },
    ]);

    const firstSemiFinal = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/matches/1/1/result',
      headers: { cookie: session },
      payload: { scoreA: 3, scoreB: 1 },
    });
    expect(firstSemiFinal.statusCode).toBe(200);
    expect(firstSemiFinal.json<FinalStage>().rounds[1].matches[0]).toMatchObject({
      teamA: { team: { id: lions.id }, pending: false },
      teamB: { team: null, pending: true },
    });

    const secondSemiFinal = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/matches/1/2/result',
      headers: { cookie: session },
      payload: { scoreA: 1, scoreB: 3 },
    });
    expect(secondSemiFinal.statusCode).toBe(200);
    expect(secondSemiFinal.json<FinalStage>().rounds[1].matches[0]).toMatchObject({
      teamA: { team: { id: lions.id } },
      teamB: { team: { id: wolves.id } },
    });

    const thirdPlace = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/matches/2/2/result',
      headers: { cookie: session },
      payload: { scoreA: 1, scoreB: 3 },
    });
    expect(thirdPlace.statusCode).toBe(200);
    expect(thirdPlace.json<FinalStage>().thirdPlaceMatch).toMatchObject({
      teamA: { team: { id: tigers.id } },
      teamB: { team: { id: bears.id } },
      scoreA: 1,
      scoreB: 3,
      winner: { id: bears.id },
    });

    const final = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/matches/2/1/result',
      headers: { cookie: session },
      payload: { scoreA: 2, scoreB: 1 },
    });
    expect(final.statusCode).toBe(200);
    const completedFinalStage = final.json<FinalStage>();
    expect(completedFinalStage.champion).toMatchObject({ id: lions.id, number: 1, name: 'Lions' });

    const publicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(publicState.statusCode).toBe(200);
    expect(publicState.json<PublicTournamentState>().finalStage).toEqual(completedFinalStage);

    const correctedSemiFinal = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/matches/1/1/result',
      headers: { cookie: session },
      payload: { scoreA: 1, scoreB: 3 },
    });
    expect(correctedSemiFinal.statusCode).toBe(200);
    const correctedFinalStage = correctedSemiFinal.json<FinalStage>();
    expect(correctedFinalStage.champion).toBeNull();
    expect(correctedFinalStage.rounds[0].matches[0]).toMatchObject({ winner: { id: tigers.id } });
    expect(correctedFinalStage.rounds[1].matches[0]).toMatchObject({
      teamA: { team: { id: tigers.id } },
      teamB: { team: { id: wolves.id } },
      scoreA: null,
      scoreB: null,
      winner: null,
    });
    expect(correctedFinalStage.thirdPlaceMatch).toMatchObject({
      teamA: { team: { id: lions.id } },
      teamB: { team: { id: bears.id } },
      scoreA: null,
      scoreB: null,
      winner: null,
    });

    const correctedPublicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(correctedPublicState.statusCode).toBe(200);
    expect(correctedPublicState.json<PublicTournamentState>().finalStage?.champion).toBeNull();

    const unconfirmedClear = await testApp().inject({
      method: 'DELETE',
      url: '/api/admin/final-stage/config',
      headers: { cookie: session },
      payload: {},
    });
    expect(unconfirmedClear.statusCode).toBe(409);

    const cleared = await testApp().inject({
      method: 'DELETE',
      url: '/api/admin/final-stage/config',
      headers: { cookie: session },
      payload: { confirm: true },
    });
    expect(cleared.statusCode).toBe(200);
    expect(cleared.json<FinalStage>()).toEqual({
      roundCount: null,
      thirdPlaceEnabled: false,
      rounds: [],
      thirdPlaceMatch: null,
      champion: null,
    });

    const clearedPublicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(clearedPublicState.statusCode).toBe(200);
    expect(clearedPublicState.json<PublicTournamentState>().finalStage).toEqual({
      roundCount: null,
      thirdPlaceEnabled: false,
      rounds: [],
      thirdPlaceMatch: null,
      champion: null,
    });
  });

  it('accepts the next-match display panel', async () => {
    const session = await login();
    const updated = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/display',
      headers: { cookie: session },
      payload: { activePanel: 'next-match', zoomPercent: 100 },
    });

    expect(updated.statusCode).toBe(200);
    expect(updated.json()).toEqual({ activePanel: 'next-match', zoomPercent: 100 });

    const publicState = await testApp().inject({ method: 'GET', url: '/api/public/state' });
    expect(publicState.json<PublicTournamentState>().display.activePanel).toBe('next-match');
  });

  it('previews automatic final-stage qualification from group standings', async () => {
    const session = await login();
    const groupsResponse = await testApp().inject({
      method: 'GET',
      url: '/api/admin/groups',
      headers: { cookie: session },
    });
    const [groupA] = groupsResponse.json<Group[]>();
    const groupBResponse = await testApp().inject({
      method: 'POST',
      url: '/api/admin/groups',
      headers: { cookie: session },
      payload: { name: 'Grupo B' },
    });
    const groupB = groupBResponse.json<Group>();

    const a1 = await createTeam(session, 1, 'A1', groupA.id);
    const a2 = await createTeam(session, 2, 'A2', groupA.id);
    const b1 = await createTeam(session, 3, 'B1', groupB.id);
    const b2 = await createTeam(session, 4, 'B2', groupB.id);

    const preview = await generatePreview(session, 1);
    const calendar = await saveGeneration(session, preview.generation);
    for (const roundNumber of new Set(calendar.matches.map((match) => match.roundNumber))) {
      await includeRoundInStandings(session, roundNumber);
    }

    for (const match of calendar.matches) {
      const preferredWinner = match.group?.id === groupA.id ? a1.id : b1.id;
      const response = await testApp().inject({
        method: 'PUT',
        url: `/api/admin/matches/${match.id}/result`,
        headers: { cookie: session },
        payload: {
          scoreA: match.teamA.id === preferredWinner ? 3 : 1,
          scoreB: match.teamB.id === preferredWinner ? 3 : 1,
        },
      });
      expect(response.statusCode).toBe(200);
    }

    const configured = await testApp().inject({
      method: 'PUT',
      url: '/api/admin/final-stage/config',
      headers: { cookie: session },
      payload: { roundCount: 2, thirdPlaceEnabled: false },
    });
    expect(configured.statusCode).toBe(200);

    const autoPreview = await testApp().inject({
      method: 'POST',
      url: '/api/admin/final-stage/auto-seed-preview',
      headers: { cookie: session },
      payload: { mode: 'per-group', qualifiersPerGroup: 2 },
    });
    expect(autoPreview.statusCode).toBe(200);
    expect(autoPreview.json<FinalSeedPreview>()).toMatchObject({
      mode: 'per-group',
      qualifiersPerGroup: 2,
      qualifierCount: 4,
      qualifiers: [
        { seedNumber: 1, groupPosition: 1, team: { id: a1.id } },
        { seedNumber: 2, groupPosition: 1, team: { id: b1.id } },
        { seedNumber: 3, groupPosition: 2, team: { id: a2.id } },
        { seedNumber: 4, groupPosition: 2, team: { id: b2.id } },
      ],
      seeds: [
        { slotIndex: 1, teamId: a1.id },
        { slotIndex: 2, teamId: b2.id },
        { slotIndex: 3, teamId: b1.id },
        { slotIndex: 4, teamId: a2.id },
      ],
    });

    const tooMany = await testApp().inject({
      method: 'POST',
      url: '/api/admin/final-stage/auto-seed-preview',
      headers: { cookie: session },
      payload: { mode: 'per-group', qualifiersPerGroup: 3 },
    });
    expect(tooMany.statusCode).toBe(400);

    const overallPreview = await testApp().inject({
      method: 'POST',
      url: '/api/admin/final-stage/auto-seed-preview',
      headers: { cookie: session },
      payload: { mode: 'overall', qualifierCount: 2 },
    });
    expect(overallPreview.statusCode).toBe(200);
    expect(overallPreview.json<FinalSeedPreview>()).toMatchObject({
      mode: 'overall',
      qualifiersPerGroup: null,
      qualifierCount: 2,
      qualifiers: [
        { seedNumber: 1, team: { id: a1.id } },
        { seedNumber: 2, team: { id: b1.id } },
      ],
      seeds: [
        { slotIndex: 1, teamId: a1.id },
        { slotIndex: 2, teamId: null },
        { slotIndex: 3, teamId: b1.id },
        { slotIndex: 4, teamId: null },
      ],
    });
  });

});
