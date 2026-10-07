import type { CalendarPreviewMatch, Group, TeamSummary } from '../../shared/types/tournament.js';

export type ScheduledGame = CalendarPreviewMatch;

interface Pairing {
  teamA: TeamSummary;
  teamB: TeamSummary;
}

function generateGroupRounds(teams: readonly TeamSummary[]): Pairing[][] {
  if (teams.length < 2) {
    return [];
  }

  const rotation: Array<TeamSummary | null> = [...teams];
  if (rotation.length % 2 !== 0) {
    rotation.push(null);
  }

  const rounds: Pairing[][] = [];
  for (let roundIndex = 0; roundIndex < rotation.length - 1; roundIndex += 1) {
    const pairings: Pairing[] = [];
    for (let index = 0; index < rotation.length / 2; index += 1) {
      const teamA = rotation[index];
      const teamB = rotation[rotation.length - index - 1];
      if (teamA && teamB) {
        pairings.push(roundIndex % 2 === 1 && index === 0
          ? { teamA: teamB, teamB: teamA }
          : { teamA, teamB });
      }
    }
    rounds.push(pairings);

    const last = rotation.pop()!;
    rotation.splice(1, 0, last);
  }

  return rounds;
}

/** Builds a global round-robin calendar from the supplied per-group team order. */
export function generateRoundRobinSchedule(
  teams: readonly TeamSummary[],
  legs: 1 | 2,
): ScheduledGame[] {
  if (legs !== 1 && legs !== 2) {
    throw new RangeError('O número de voltas tem de ser 1 ou 2.');
  }

  const groupedTeams = new Map<number, { group: Group; teams: TeamSummary[] }>();
  for (const team of teams) {
    const existing = groupedTeams.get(team.group.id);
    if (existing) {
      existing.teams.push(team);
    } else {
      groupedTeams.set(team.group.id, { group: team.group, teams: [team] });
    }
  }

  const groups = [...groupedTeams.values()]
    .sort((first, second) => first.group.sortOrder - second.group.sortOrder || first.group.id - second.group.id)
    .map(({ group, teams: groupTeams }) => ({ group, rounds: generateGroupRounds(groupTeams) }));
  const firstLegRoundCount = Math.max(0, ...groups.map(({ rounds }) => rounds.length));
  const firstLeg: ScheduledGame[] = [];

  for (let roundIndex = 0; roundIndex < firstLegRoundCount; roundIndex += 1) {
    for (const { group, rounds } of groups) {
      for (const pairing of rounds[roundIndex] ?? []) {
        firstLeg.push({
          gameNumber: firstLeg.length + 1,
          roundNumber: roundIndex + 1,
          group,
          ...pairing,
        });
      }
    }
  }

  if (legs === 1) {
    return firstLeg;
  }

  return [
    ...firstLeg,
    ...firstLeg.map((game, index) => ({
      gameNumber: firstLeg.length + index + 1,
      roundNumber: game.roundNumber + firstLegRoundCount,
      group: game.group,
      teamA: game.teamB,
      teamB: game.teamA,
    })),
  ];
}
