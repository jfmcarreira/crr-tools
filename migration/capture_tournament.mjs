// Runs against an isolated legacy checkout; produces synthetic compatibility fixtures.
import assert from 'node:assert/strict';
import { copyFileSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const source = resolve(process.env.MIGRATION_SOURCE_DIR ?? '.migration/tournament');
const output = resolve('migration/fixtures');
const { createApp } = await import(pathToFileURL(`${source}/src/server/app.ts`));
const { openDatabase } = await import(pathToFileURL(`${source}/src/server/db/database.ts`));
const authentication = {
  adminPassword: 'migration-fixture-password',
  sessionSecret: 'migration-fixture-secret-not-for-production',
};

if (process.argv.includes('--serve')) {
  const app = await createApp({
    databasePath: process.env.CAPTURE_DATABASE,
    staticRoot: `${source}/dist/client`, basePath: '/', authentication,
  });
  await app.listen({ host: '127.0.0.1', port: 18080 });
} else {
  mkdirSync(output, { recursive: true });
  mkdirSync(resolve('.migration'), { recursive: true });
  const temporary = mkdtempSync(resolve('.migration/capture-'));
  const databasePath = `${temporary}/tournament.sqlite`;
  const database = openDatabase({ path: databasePath });
  assert.equal(database.prepare('SELECT count(*) AS count FROM teams').get().count, 0);
  const app = await createApp({ database, authentication, basePath: '/jogo/' });
  const observations = [];
  let cookie;
  const save = (name, value) => writeFileSync(`${output}/${name}`, JSON.stringify(value, null, 2) + '\n');
  async function request(method, url, payload, status = 200, authorized = true) {
    const response = await app.inject({ method, url, payload,
      headers: authorized && cookie ? { cookie } : {} });
    assert.equal(response.statusCode, status, `${method} ${url}: ${response.body}`);
    const body = response.json();
    observations.push({ request: { method, url, ...(payload ? { payload } : {}), authorized },
      response: { status, body } });
    return { body, response };
  }
  try {
    await request('GET', '/api/auth/session', undefined, 200, false);
    await request('GET', '/api/admin/teams', undefined, 401, false);
    await request('POST', '/api/auth/login', { password: 'wrong' }, 401, false);
    const login = await request('POST', '/api/auth/login',
      { password: authentication.adminPassword }, 200, false);
    const session = login.response.cookies.find(item => item.name === 'tournament_admin_session');
    assert.ok(session);
    cookie = `${session.name}=${session.value}`;
    // Preserve cookie attributes, excluding the generated token.
    save('tournament-cookie.json', login.response.headers['set-cookie'].replace(session.value, '<token>'));
    await request('PUT', '/api/admin/settings', {
      name: 'Torneio de referência CRR', classificationMode: 'standard',
    });
    const teams = [];
    for (let number = 1; number <= 4; number++) {
      const team = (await request('POST', '/api/admin/teams', {
        number, name: `Equipa ${number}`, groupId: 1,
      }, 201)).body;
      teams.push(team);
      await request('POST', `/api/admin/teams/${team.id}/players`, { name: `Jogador ${number}` }, 201);
    }
    await request('POST', '/api/admin/teams', { number: 1, name: 'Duplicada', groupId: 1 }, 409);
    const calendar = (await request('POST', '/api/admin/calendar/generate', {
      generation: { legs: 1, teamOrder: teams.map(team => ({ teamId: team.id, groupId: 1 })) },
    })).body;
    assert.ok(calendar.matches.length > 0);
    await request('PUT', `/api/admin/matches/${calendar.matches[0].id}/result`, { scoreA: 3, scoreB: 1 });
    await request('PUT', '/api/admin/rounds/1/standings', { countsTowardStandings: true });
    await request('PUT', '/api/admin/final-stage/config', { roundCount: 2, thirdPlaceEnabled: true });
    await request('PUT', '/api/admin/final-stage/seeds', {
      seeds: teams.map((team, index) => ({ slotIndex: index + 1, teamId: team.id })),
    });
    await request('PUT', '/api/admin/final-stage/matches/1/1/result', { scoreA: 2, scoreB: 0 });
    await request('PUT', '/api/admin/final-stage/matches/1/2/result', { scoreA: 1, scoreB: 4 });
    await request('PUT', '/api/admin/final-stage/matches/2/1/result', { scoreA: 3, scoreB: 2 });
    await request('PUT', '/api/admin/final-stage/matches/2/2/result', { scoreA: 1, scoreB: 0 });
    await request('PUT', '/api/admin/display', { activePanel: 'classification', zoomPercent: 110 });
    // Freeze persisted timestamps so the final state and DB are stable across captures.
    for (const table of ['tournament_settings', 'display_settings', 'league_groups', 'teams']) {
      database.prepare(`UPDATE ${table} SET created_at = ?, updated_at = ?`)
        .run('2026-01-01 00:00:00', '2026-01-01 00:00:00');
    }
    save('tournament-state.json', (await request('GET', '/api/public/state')).body);
    await request('GET', '/api/admin/missing', undefined, 404);
    save('tournament-api.json', observations);
    const schema = database.prepare(
      "SELECT type, name, tbl_name, sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type, name",
    ).all();
    save('tournament-schema.json', schema);
    const tables = schema.filter(item => item.type === 'table').map(item => item.name);
    save('tournament-rows.json', Object.fromEntries(tables.map(table => [table,
      database.prepare(`SELECT * FROM ${table} ORDER BY rowid`).all()])));
    const routes = [...readFileSync(`${source}/src/server/app.ts`, 'utf8')
      .matchAll(/app\.(get|post|put|delete)\('(\/api\/[^']+)'/g)]
      .map(match => ({ method: match[1].toUpperCase(), path: match[2] }));
    save('tournament-routes.json', routes);
    assert.deepEqual(database.pragma('foreign_key_check'), []);
    assert.equal(database.pragma('integrity_check', { simple: true }), 'ok');
  } finally {
    await app.close();
    database.pragma('wal_checkpoint(TRUNCATE)');
    database.close();
  }
  copyFileSync(databasePath, `${output}/tournament.sqlite`);
  rmSync(temporary, { recursive: true });
  console.log(`Tournament baseline captured in ${output}`);
}
