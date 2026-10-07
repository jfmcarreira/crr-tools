import type {
  ClassificationMode,
  ClassificationRow,
  LeagueMatch,
  TeamSummary,
} from '../../shared/types/tournament.js';

export type ClassificationMatch = Pick<LeagueMatch, 'teamA' | 'teamB' | 'scoreA' | 'scoreB'>;

type Statistics = Omit<ClassificationRow, 'position' | 'goalDifference'>;

interface HeadToHeadStatistics {
  points: number;
  goalsFor: number;
  goalsAgainst: number;
}

function goalDifference(statistics: Pick<Statistics, 'goalsFor' | 'goalsAgainst'>): number {
  return statistics.goalsFor - statistics.goalsAgainst;
}

function comparePrimary(a: Statistics, b: Statistics, mode: ClassificationMode): number {
  if (mode === 'total-points') {
    return b.points - a.points;
  }

  return (
    b.points - a.points ||
    goalDifference(b) - goalDifference(a) ||
    b.goalsFor - a.goalsFor
  );
}

function haveSamePrimaryValues(a: Statistics, b: Statistics, mode: ClassificationMode): boolean {
  if (mode === 'total-points') {
    return a.points === b.points;
  }

  return a.points === b.points &&
    goalDifference(a) === goalDifference(b) &&
    a.goalsFor === b.goalsFor;
}

function calculateHeadToHead(
  tiedTeams: readonly Statistics[],
  matches: readonly ClassificationMatch[],
): Map<number, HeadToHeadStatistics> {
  const ids = new Set(tiedTeams.map((team) => team.team.id));
  const statistics = new Map<number, HeadToHeadStatistics>(
    tiedTeams.map((team) => [team.team.id, { points: 0, goalsFor: 0, goalsAgainst: 0 }]),
  );

  for (const match of matches) {
    if (match.scoreA === null || match.scoreB === null || !ids.has(match.teamA.id) || !ids.has(match.teamB.id)) {
      continue;
    }

    const teamA = statistics.get(match.teamA.id)!;
    const teamB = statistics.get(match.teamB.id)!;
    teamA.goalsFor += match.scoreA;
    teamA.goalsAgainst += match.scoreB;
    teamB.goalsFor += match.scoreB;
    teamB.goalsAgainst += match.scoreA;
    if (match.scoreA > match.scoreB) {
      teamA.points += 3;
    } else if (match.scoreB > match.scoreA) {
      teamB.points += 3;
    } else {
      teamA.points += 1;
      teamB.points += 1;
    }
  }

  return statistics;
}

/**
 * Calculates the league table from completed matches. Standard classifications
 * use result points; total-points classifications use the teams' scored totals.
 */
export function calculateClassification(
  teams: readonly TeamSummary[],
  matches: readonly ClassificationMatch[],
  mode: ClassificationMode = 'standard',
): ClassificationRow[] {
  const statisticsByTeamId = new Map<number, Statistics>(
    teams.map((team) => [team.id, {
      team,
      played: 0,
      wins: 0,
      draws: 0,
      losses: 0,
      goalsFor: 0,
      goalsAgainst: 0,
      points: 0,
    }]),
  );

  for (const match of matches) {
    if (match.scoreA === null || match.scoreB === null) {
      continue;
    }
    const teamA = statisticsByTeamId.get(match.teamA.id);
    const teamB = statisticsByTeamId.get(match.teamB.id);
    if (!teamA || !teamB) {
      continue;
    }

    teamA.played += 1;
    teamB.played += 1;
    teamA.goalsFor += match.scoreA;
    teamA.goalsAgainst += match.scoreB;
    teamB.goalsFor += match.scoreB;
    teamB.goalsAgainst += match.scoreA;
    if (mode === 'total-points') {
      teamA.points += match.scoreA;
      teamB.points += match.scoreB;
    }
    if (match.scoreA > match.scoreB) {
      teamA.wins += 1;
      teamB.losses += 1;
      if (mode === 'standard') {
        teamA.points += 3;
      }
    } else if (match.scoreB > match.scoreA) {
      teamB.wins += 1;
      teamA.losses += 1;
      if (mode === 'standard') {
        teamB.points += 3;
      }
    } else {
      teamA.draws += 1;
      teamB.draws += 1;
      if (mode === 'standard') {
        teamA.points += 1;
        teamB.points += 1;
      }
    }
  }

  const primaryOrdered = [...statisticsByTeamId.values()].sort((a, b) => comparePrimary(a, b, mode));
  const ordered: Statistics[] = [];
  for (let start = 0; start < primaryOrdered.length;) {
    let end = start + 1;
    while (
      end < primaryOrdered.length &&
      haveSamePrimaryValues(primaryOrdered[start], primaryOrdered[end], mode)
    ) {
      end += 1;
    }

    const tiedGroup = primaryOrdered.slice(start, end);
    if (tiedGroup.length === 1) {
      ordered.push(tiedGroup[0]);
    } else {
      const headToHead = calculateHeadToHead(tiedGroup, matches);
      tiedGroup.sort((a, b) => {
        const aHeadToHead = headToHead.get(a.team.id)!;
        const bHeadToHead = headToHead.get(b.team.id)!;
        return (
          bHeadToHead.points - aHeadToHead.points ||
          (bHeadToHead.goalsFor - bHeadToHead.goalsAgainst) -
            (aHeadToHead.goalsFor - aHeadToHead.goalsAgainst) ||
          bHeadToHead.goalsFor - aHeadToHead.goalsFor ||
          a.team.number - b.team.number
        );
      });
      ordered.push(...tiedGroup);
    }
    start = end;
  }

  return ordered.map((statistics, index) => ({
    position: index + 1,
    team: statistics.team,
    played: statistics.played,
    wins: statistics.wins,
    draws: statistics.draws,
    losses: statistics.losses,
    goalsFor: statistics.goalsFor,
    goalsAgainst: statistics.goalsAgainst,
    goalDifference: goalDifference(statistics),
    points: statistics.points,
  }));
}
