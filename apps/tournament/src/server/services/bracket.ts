import type {
  BracketMatch,
  BracketParticipant,
  BracketRound,
  FinalStage,
  TeamSummary,
} from '../../shared/types/tournament.js';

export interface BracketSeed {
  slotIndex: number;
  team: TeamSummary | null;
}

export interface BracketResult {
  roundIndex: number;
  matchIndex: number;
  scoreA: number | null;
  scoreB: number | null;
}

interface CalculatedMatch extends BracketMatch {
  canProduceWinner: boolean;
}

function roundName(roundCount: number, roundIndex: number): string {
  const participantCount = 2 ** (roundCount - roundIndex + 1);
  if (participantCount === 2) {
    return 'Final';
  }
  if (participantCount === 4) {
    return 'Meias-finais';
  }
  if (participantCount === 8) {
    return 'Quartos de final';
  }
  if (participantCount === 16) {
    return 'Oitavos de final';
  }
  return `Ronda de ${participantCount}`;
}

function participant(team: TeamSummary | null, pending = false): BracketParticipant {
  return { team, pending };
}

function resultFor(
  results: ReadonlyMap<string, BracketResult>,
  roundIndex: number,
  matchIndex: number,
): BracketResult | undefined {
  return results.get(`${roundIndex}:${matchIndex}`);
}

/** Builds a bracket exclusively from initial seeds and stored score rows. */
export function calculateBracket(
  roundCount: number | null,
  seeds: readonly BracketSeed[],
  results: readonly BracketResult[],
  thirdPlaceEnabled = false,
): FinalStage {
  if (roundCount === null) {
    return { roundCount: null, thirdPlaceEnabled: false, rounds: [], thirdPlaceMatch: null, champion: null };
  }
  if (!Number.isInteger(roundCount) || roundCount < 1 || roundCount > 8) {
    throw new RangeError('O número de rondas tem de estar entre 1 e 8.');
  }

  const seedsBySlot = new Map(seeds.map((seed) => [seed.slotIndex, seed.team]));
  const resultsByMatch = new Map(results.map((result) => [`${result.roundIndex}:${result.matchIndex}`, result]));
  const calculatedRounds: CalculatedMatch[][] = [];

  for (let roundIndex = 1; roundIndex <= roundCount; roundIndex += 1) {
    const matchCount = 2 ** (roundCount - roundIndex);
    const matches: CalculatedMatch[] = [];
    for (let matchIndex = 1; matchIndex <= matchCount; matchIndex += 1) {
      let teamA: BracketParticipant;
      let teamB: BracketParticipant;
      if (roundIndex === 1) {
        teamA = participant(seedsBySlot.get((matchIndex - 1) * 2 + 1) ?? null);
        teamB = participant(seedsBySlot.get((matchIndex - 1) * 2 + 2) ?? null);
      } else {
        const previousA = calculatedRounds[roundIndex - 2][(matchIndex - 1) * 2];
        const previousB = calculatedRounds[roundIndex - 2][(matchIndex - 1) * 2 + 1];
        teamA = previousA.winner
          ? participant(previousA.winner)
          : participant(null, previousA.canProduceWinner);
        teamB = previousB.winner
          ? participant(previousB.winner)
          : participant(null, previousB.canProduceWinner);
      }

      const result = resultFor(resultsByMatch, roundIndex, matchIndex);
      const scoresAreValid = result && result.scoreA !== null && result.scoreB !== null && result.scoreA !== result.scoreB;
      const hasBothTeams = teamA.team !== null && teamB.team !== null;
      const isBye = !teamA.pending && !teamB.pending && ((teamA.team === null) !== (teamB.team === null));
      const isEmpty = !teamA.pending && !teamB.pending && teamA.team === null && teamB.team === null;
      let winner: TeamSummary | null = null;
      if (isBye) {
        winner = teamA.team ?? teamB.team;
      } else if (hasBothTeams && scoresAreValid) {
        winner = result.scoreA! > result.scoreB! ? teamA.team : teamB.team;
      }

      matches.push({
        matchIndex,
        teamA,
        teamB,
        scoreA: hasBothTeams ? result?.scoreA ?? null : null,
        scoreB: hasBothTeams ? result?.scoreB ?? null : null,
        winner,
        isBye,
        canProduceWinner: !isEmpty && (winner !== null || teamA.pending || teamB.pending || hasBothTeams),
      });
    }
    calculatedRounds.push(matches);
  }

  const rounds: BracketRound[] = calculatedRounds.map((matches, index) => ({
    roundIndex: index + 1,
    name: roundName(roundCount, index + 1),
    matches: matches.map(({ canProduceWinner: _canProduceWinner, ...match }) => match),
  }));
  const finalMatch = calculatedRounds[calculatedRounds.length - 1][0];
  const thirdPlaceMatch = thirdPlaceEnabled && roundCount >= 2
    ? calculateThirdPlaceMatch(calculatedRounds[roundCount - 2], resultFor(resultsByMatch, roundCount, 2))
    : null;
  return { roundCount, thirdPlaceEnabled, rounds, thirdPlaceMatch, champion: finalMatch.winner };
}

export function getBracketMatch(finalStage: FinalStage, roundIndex: number, matchIndex: number): BracketMatch | null {
  if (finalStage.thirdPlaceMatch && roundIndex === finalStage.roundCount && matchIndex === finalStage.thirdPlaceMatch.matchIndex) {
    return finalStage.thirdPlaceMatch;
  }
  return finalStage.rounds[roundIndex - 1]?.matches[matchIndex - 1] ?? null;
}

function calculateThirdPlaceMatch(
  semiFinals: readonly CalculatedMatch[],
  result: BracketResult | undefined,
): BracketMatch {
  const teamA = loserOf(semiFinals[0]);
  const teamB = loserOf(semiFinals[1]);
  const hasBothTeams = teamA.team !== null && teamB.team !== null;
  const scoresAreValid = result && result.scoreA !== null && result.scoreB !== null && result.scoreA !== result.scoreB;
  const winner = hasBothTeams && scoresAreValid
    ? result.scoreA! > result.scoreB! ? teamA.team : teamB.team
    : null;
  return {
    matchIndex: 2,
    teamA,
    teamB,
    scoreA: hasBothTeams ? result?.scoreA ?? null : null,
    scoreB: hasBothTeams ? result?.scoreB ?? null : null,
    winner,
    isBye: false,
  };
}

function loserOf(match: CalculatedMatch): BracketParticipant {
  if (match.teamA.pending || match.teamB.pending) {
    return participant(null, true);
  }
  if (!match.teamA.team || !match.teamB.team || !match.winner) {
    return participant(null, Boolean(match.teamA.team && match.teamB.team));
  }
  return participant(match.winner.id === match.teamA.team.id ? match.teamB.team : match.teamA.team);
}

/** Lists all match result rows whose participants depend on a match. */
export function downstreamMatches(
  roundCount: number,
  roundIndex: number,
  matchIndex: number,
): Array<{ roundIndex: number; matchIndex: number }> {
  const matches: Array<{ roundIndex: number; matchIndex: number }> = [];
  let nextMatchIndex = matchIndex;
  for (let nextRound = roundIndex + 1; nextRound <= roundCount; nextRound += 1) {
    nextMatchIndex = Math.ceil(nextMatchIndex / 2);
    matches.push({ roundIndex: nextRound, matchIndex: nextMatchIndex });
  }
  return matches;
}
