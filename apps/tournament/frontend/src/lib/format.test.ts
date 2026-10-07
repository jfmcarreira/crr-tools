import { describe, expect, it } from 'vitest';
import type { LeagueMatch } from '../types';
import { latestResultsRound, unfinishedLeagueMatches } from './format';

function match(id: number, roundNumber: number, scoreA: number | null, scoreB: number | null): LeagueMatch {
  const group = { id: 1, name: 'Grupo A', sortOrder: 0 };
  const teamANumber = id * 2 - 1;
  const teamBNumber = id * 2;
  return {
      id,
      gameNumber: id,
      roundNumber,
      countsTowardStandings: false,
      group,
    teamA: { id: teamANumber, number: teamANumber, name: `Equipa ${teamANumber}`, group },
    teamB: { id: teamBNumber, number: teamBNumber, name: `Equipa ${teamBNumber}`, group },
    scoreA,
    scoreB,
  };
}

describe('latestResultsRound', () => {
  it('returns null without a calendar', () => {
    expect(latestResultsRound([])).toBeNull();
  });

  it('shows the first scheduled round before results are entered', () => {
    const result = latestResultsRound([
      match(2, 2, null, null),
      match(1, 1, null, null),
    ]);

    expect(result?.roundNumber).toBe(1);
  });

  it('shows every match from the latest round containing a result', () => {
    const result = latestResultsRound([
      match(4, 3, null, null),
      match(3, 2, null, null),
      match(2, 2, 4, 2),
      match(1, 1, 1, 0),
    ]);

    expect(result?.roundNumber).toBe(2);
    expect(result?.matches.map((scheduledMatch) => scheduledMatch.id)).toEqual([2, 3]);
  });
});


describe('unfinishedLeagueMatches', () => {
  it('returns unfinished matches ordered by game number', () => {
    const result = unfinishedLeagueMatches([
      match(3, 2, null, null),
      match(1, 1, 2, 1),
      match(2, 1, null, null),
    ]);

    expect(result.map((scheduledMatch) => scheduledMatch.gameNumber)).toEqual([2, 3]);
  });
});
