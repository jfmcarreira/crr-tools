import type { LeagueMatch } from '../types';

export function groupMatches(matches: LeagueMatch[]): Array<{ roundNumber: number; matches: LeagueMatch[] }> {
  const groups = new Map<number, LeagueMatch[]>();
  for (const match of matches) {
    const current = groups.get(match.roundNumber) ?? [];
    current.push(match);
    groups.set(match.roundNumber, current);
  }

  return [...groups.entries()]
    .sort(([first], [second]) => first - second)
    .map(([roundNumber, groupedMatches]) => ({
      roundNumber,
      matches: [...groupedMatches].sort((first, second) => first.gameNumber - second.gameNumber),
    }));
}

export function unfinishedLeagueMatches(matches: readonly LeagueMatch[]): LeagueMatch[] {
  return matches
    .filter((match) => match.scoreA === null || match.scoreB === null)
    .sort((first, second) => first.gameNumber - second.gameNumber);
}

export function latestResultsRound(matches: LeagueMatch[]): { roundNumber: number; matches: LeagueMatch[] } | null {
  const rounds = groupMatches(matches);
  for (let index = rounds.length - 1; index >= 0; index -= 1) {
    if (rounds[index].matches.some((match) => match.scoreA !== null && match.scoreB !== null)) {
      return rounds[index];
    }
  }
  return rounds[0] ?? null;
}

export function matchGroupLabel(match: LeagueMatch): string {
  return match.group?.name ?? 'Entre grupos';
}

export function signedDifference(value: number): string {
  return value > 0 ? `+${value}` : String(value);
}
