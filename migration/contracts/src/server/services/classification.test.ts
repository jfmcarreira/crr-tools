import { describe, expect, it } from 'vitest';
import type { Group, TeamSummary } from '../../shared/types/tournament.js';
import { calculateClassification, type ClassificationMatch } from './classification.js';

const group: Group = { id: 1, name: 'Grupo A', sortOrder: 0 };
const team = (id: number, number = id): TeamSummary => ({ id, number, name: `Equipa ${number}`, group });
const teams = [team(1), team(2), team(3), team(4)];
const match = (teamA: TeamSummary, teamB: TeamSummary, scoreA: number | null, scoreB: number | null): ClassificationMatch => ({
  teamA,
  teamB,
  scoreA,
  scoreB,
});

describe('calculateClassification', () => {
  it('mantém a classificação standard como modo predefinido', () => {
    const matches = [
      match(teams[0], teams[1], 2, 0),
      match(teams[2], teams[1], 4, 1),
    ];

    const standard = calculateClassification(teams.slice(0, 3), matches, 'standard');
    expect(calculateClassification(teams.slice(0, 3), matches)).toEqual(standard);
    expect(standard.map((row) => ({ id: row.team.id, points: row.points }))).toEqual([
      { id: 3, points: 3 },
      { id: 1, points: 3 },
      { id: 2, points: 0 },
    ]);
  });

  it('calcula vitórias, empates, derrotas e ignora resultados incompletos', () => {
    const table = calculateClassification(teams.slice(0, 3), [
      match(teams[0], teams[1], 3, 1),
      match(teams[0], teams[2], 2, 2),
      match(teams[1], teams[2], null, null),
    ]);
    expect(table[0]).toMatchObject({ team: teams[0], played: 2, wins: 1, draws: 1, losses: 0, goalsFor: 5, goalsAgainst: 3, goalDifference: 2, points: 4 });
    expect(table.find((row) => row.team.id === 2)).toMatchObject({ played: 1, losses: 1, points: 0 });
    expect(table.find((row) => row.team.id === 3)).toMatchObject({ played: 1, draws: 1, points: 1 });
  });

  it('ordena por pontos, diferença de golos e golos marcados', () => {
    const table = calculateClassification(teams.slice(0, 3), [
      match(teams[0], teams[1], 2, 0),
      match(teams[2], teams[1], 4, 1),
    ]);
    expect(table.map((row) => row.team.id)).toEqual([3, 1, 2]);
  });

  it('usa confronto direto para equipas empatadas nos critérios principais', () => {
    const table = calculateClassification(teams, [
      match(teams[0], teams[1], 1, 0),
      match(teams[0], teams[2], 0, 1),
      match(teams[1], teams[3], 1, 0),
    ]);
    const teamOnePosition = table.findIndex((row) => row.team.id === 1);
    const teamTwoPosition = table.findIndex((row) => row.team.id === 2);
    expect(teamOnePosition).toBeLessThan(teamTwoPosition);
  });

  it('usa o número da equipa como último critério determinístico', () => {
    const reversed = [team(10, 9), team(11, 2)];
    expect(calculateClassification(reversed, []).map((row) => row.team.number)).toEqual([2, 9]);
  });

  describe('total-points', () => {
    it('soma os resultados marcados por cada equipa nos pontos', () => {
      const table = calculateClassification(teams.slice(0, 3), [
        match(teams[0], teams[1], 8, 5),
        match(teams[0], teams[2], 3, 4),
        match(teams[1], teams[2], 7, 6),
      ], 'total-points');

      expect(table.map((row) => ({ id: row.team.id, points: row.points }))).toEqual([
        { id: 2, points: 12 },
        { id: 1, points: 11 },
        { id: 3, points: 10 },
      ]);
      expect(table.find((row) => row.team.id === 1)).toMatchObject({
        played: 2,
        wins: 1,
        draws: 0,
        losses: 1,
        goalsFor: 11,
        goalsAgainst: 9,
        goalDifference: 2,
      });
    });

    it('resolve totais empatados pelo confronto direto, não pela diferença global', () => {
      const table = calculateClassification(teams, [
        match(teams[0], teams[1], 0, 1),
        match(teams[0], teams[2], 5, 0),
        match(teams[1], teams[3], 4, 10),
      ], 'total-points');

      expect(table.map((row) => row.team.id)).toEqual([4, 2, 1, 3]);
      expect(table.find((row) => row.team.id === 1)).toMatchObject({ points: 5, goalDifference: 4 });
      expect(table.find((row) => row.team.id === 2)).toMatchObject({ points: 5, goalDifference: -5 });
    });

    it('usa o número da equipa como fallback determinístico', () => {
      const reversed = [team(10, 9), team(11, 2), team(12, 5)];

      expect(calculateClassification(reversed, [], 'total-points').map((row) => row.team.number))
        .toEqual([2, 5, 9]);
    });

    it('ignora jogos incompletos sem acumular resultados ou estatísticas', () => {
      const table = calculateClassification(teams.slice(0, 3), [
        match(teams[0], teams[1], 7, 3),
        match(teams[0], teams[2], 9, null),
        match(teams[1], teams[2], null, 8),
      ], 'total-points');

      expect(table.find((row) => row.team.id === 1)).toMatchObject({ played: 1, points: 7, goalsFor: 7 });
      expect(table.find((row) => row.team.id === 2)).toMatchObject({ played: 1, points: 3, goalsFor: 3 });
      expect(table.find((row) => row.team.id === 3)).toMatchObject({ played: 0, points: 0, goalsFor: 0 });
    });
  });
});
