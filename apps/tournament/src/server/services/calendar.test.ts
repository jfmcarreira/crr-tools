import { describe, expect, it } from 'vitest';
import type { Group, TeamSummary } from '../../shared/types/tournament.js';
import { generateRoundRobinSchedule } from './calendar.js';

const team = (id: number, group: Group): TeamSummary => ({
  id,
  number: id,
  name: `Equipa ${id}`,
  group,
});

function pairCounts(schedule: ReturnType<typeof generateRoundRobinSchedule>): Map<string, number> {
  const counts = new Map<string, number>();
  for (const game of schedule) {
    const key = [game.teamA.id, game.teamB.id].sort((a, b) => a - b).join('-');
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

describe('generateRoundRobinSchedule', () => {
  it('gera as três jornadas de um grupo par com quatro equipas', () => {
    const group: Group = { id: 1, name: 'Grupo A', sortOrder: 0 };
    const teams = [1, 2, 3, 4].map((id) => team(id, group));

    const schedule = generateRoundRobinSchedule(teams, 1);

    expect(schedule.map((game) => ({
      gameNumber: game.gameNumber,
      roundNumber: game.roundNumber,
      groupId: game.group.id,
      teams: [game.teamA.id, game.teamB.id],
    }))).toEqual([
      { gameNumber: 1, roundNumber: 1, groupId: 1, teams: [1, 4] },
      { gameNumber: 2, roundNumber: 1, groupId: 1, teams: [2, 3] },
      { gameNumber: 3, roundNumber: 2, groupId: 1, teams: [3, 1] },
      { gameNumber: 4, roundNumber: 2, groupId: 1, teams: [4, 2] },
      { gameNumber: 5, roundNumber: 3, groupId: 1, teams: [1, 2] },
      { gameNumber: 6, roundNumber: 3, groupId: 1, teams: [3, 4] },
    ]);
  });

  it('suporta um grupo ímpar através de uma folga por jornada', () => {
    const group: Group = { id: 1, name: 'Grupo A', sortOrder: 0 };
    const teams = [1, 2, 3].map((id) => team(id, group));

    const schedule = generateRoundRobinSchedule(teams, 1);

    expect(schedule.map((game) => [game.roundNumber, game.teamA.id, game.teamB.id])).toEqual([
      [1, 2, 3],
      [2, 3, 1],
      [3, 1, 2],
    ]);
    expect(schedule.map((game) => game.roundNumber)).toEqual([1, 2, 3]);
  });

  it('combina grupos ordenados nas mesmas jornadas sem cruzar nem repetir equipas', () => {
    const group2: Group = { id: 2, name: 'Grupo 2', sortOrder: 0 };
    const group1: Group = { id: 1, name: 'Grupo 1', sortOrder: 0 };
    const group3: Group = { id: 3, name: 'Grupo 3', sortOrder: 1 };
    const teams = [
      team(21, group2),
      team(11, group1),
      team(31, group3),
      team(22, group2),
      team(12, group1),
      team(32, group3),
      team(23, group2),
      team(13, group1),
      team(14, group1),
    ];

    const schedule = generateRoundRobinSchedule(teams, 1);

    expect(schedule.map((game) => [game.roundNumber, game.group.id])).toEqual([
      [1, 1], [1, 1], [1, 2], [1, 3],
      [2, 1], [2, 1], [2, 2],
      [3, 1], [3, 1], [3, 2],
    ]);
    expect(schedule.every((game) => (
      game.teamA.group.id === game.group.id && game.teamB.group.id === game.group.id
    ))).toBe(true);

    for (const roundNumber of [1, 2, 3]) {
      const participants = schedule
        .filter((game) => game.roundNumber === roundNumber)
        .flatMap((game) => [game.teamA.id, game.teamB.id]);
      expect(new Set(participants).size).toBe(participants.length);
    }
  });

  it('anexa uma segunda volta que espelha exatamente a primeira', () => {
    const group: Group = { id: 1, name: 'Grupo A', sortOrder: 0 };
    const teams = [1, 2, 3, 4].map((id) => team(id, group));
    const firstLeg = generateRoundRobinSchedule(teams, 1);

    const schedule = generateRoundRobinSchedule(teams, 2);

    expect(schedule.slice(0, firstLeg.length)).toEqual(firstLeg);
    expect(schedule.slice(firstLeg.length)).toEqual(firstLeg.map((game, index) => ({
      gameNumber: firstLeg.length + index + 1,
      roundNumber: game.roundNumber + 3,
      group: game.group,
      teamA: game.teamB,
      teamB: game.teamA,
    })));
  });

  it('agenda todos os pares uma vez por volta', () => {
    const group: Group = { id: 1, name: 'Grupo A', sortOrder: 0 };
    const teams = [1, 2, 3, 4].map((id) => team(id, group));
    const expectedPairs = ['1-2', '1-3', '1-4', '2-3', '2-4', '3-4'];

    expect(pairCounts(generateRoundRobinSchedule(teams, 1))).toEqual(
      new Map(expectedPairs.map((pair) => [pair, 1])),
    );
    expect(pairCounts(generateRoundRobinSchedule(teams, 2))).toEqual(
      new Map(expectedPairs.map((pair) => [pair, 2])),
    );
  });

  it('não altera a lista nem a ordem recebidas', () => {
    const groupA: Group = { id: 1, name: 'Grupo A', sortOrder: 1 };
    const groupB: Group = { id: 2, name: 'Grupo B', sortOrder: 0 };
    const teams = [team(1, groupA), team(4, groupB), team(3, groupA), team(2, groupB)];
    const snapshot = structuredClone(teams);

    generateRoundRobinSchedule(teams, 2);

    expect(teams).toEqual(snapshot);
    expect(teams.map(({ id }) => id)).toEqual([1, 4, 3, 2]);
  });

  it('rejeita um número de voltas inválido mesmo quando o tipo é contornado', () => {
    expect(() => generateRoundRobinSchedule([], 3 as 1 | 2)).toThrowError(RangeError);
    expect(() => generateRoundRobinSchedule([], 3 as 1 | 2)).toThrow('1 ou 2');
  });
});
