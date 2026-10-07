import { describe, expect, it } from 'vitest';
import type { Group, TeamSummary } from '../../shared/types/tournament.js';
import { calculateBracket, downstreamMatches } from './bracket.js';

const group: Group = { id: 1, name: 'Grupo A', sortOrder: 0 };
const team = (id: number): TeamSummary => ({ id, number: id, name: `Equipa ${id}`, group });
const seeds = [1, 2, 3, 4].map((slotIndex) => ({ slotIndex, team: team(slotIndex) }));

describe('calculateBracket', () => {
  it('faz avançar vencedores entre várias rondas e determina o campeão', () => {
    const bracket = calculateBracket(2, seeds, [
      { roundIndex: 1, matchIndex: 1, scoreA: 5, scoreB: 2 },
      { roundIndex: 1, matchIndex: 2, scoreA: 1, scoreB: 3 },
      { roundIndex: 2, matchIndex: 1, scoreA: 4, scoreB: 2 },
    ]);
    expect(bracket.rounds[1].matches[0].teamA.team?.id).toBe(1);
    expect(bracket.rounds[1].matches[0].teamB.team?.id).toBe(4);
    expect(bracket.champion?.id).toBe(1);
  });

  it('não faz avançar um empate que a API deve rejeitar', () => {
    const bracket = calculateBracket(1, seeds.slice(0, 2), [
      { roundIndex: 1, matchIndex: 1, scoreA: 3, scoreB: 3 },
    ]);
    expect(bracket.rounds[0].matches[0].winner).toBeNull();
    expect(bracket.champion).toBeNull();
  });

  it('faz avançar uma equipa automaticamente num bye e deixa jogos vazios por apurar', () => {
    const bracket = calculateBracket(2, [
      { slotIndex: 1, team: team(1) },
      { slotIndex: 2, team: null },
      { slotIndex: 3, team: null },
      { slotIndex: 4, team: null },
    ], []);
    expect(bracket.rounds[0].matches[0]).toMatchObject({ isBye: true, winner: team(1) });
    expect(bracket.rounds[0].matches[1].winner).toBeNull();
    expect(bracket.rounds[1].matches[0].teamA.team?.id).toBe(1);
    expect(bracket.rounds[1].matches[0].teamB.pending).toBe(false);
  });

  it('cria o jogo do 3.º lugar com os derrotados das meias-finais', () => {
    const bracket = calculateBracket(2, seeds, [
      { roundIndex: 1, matchIndex: 1, scoreA: 5, scoreB: 2 },
      { roundIndex: 1, matchIndex: 2, scoreA: 1, scoreB: 3 },
      { roundIndex: 2, matchIndex: 2, scoreA: 2, scoreB: 4 },
    ], true);
    expect(bracket.thirdPlaceEnabled).toBe(true);
    expect(bracket.thirdPlaceMatch).toMatchObject({
      matchIndex: 2,
      teamA: { team: { id: 2 } },
      teamB: { team: { id: 3 } },
      scoreA: 2,
      scoreB: 4,
      winner: { id: 3 },
    });
  });

  it('identifica todos os resultados a invalidar após mudar um jogo a montante', () => {
    expect(downstreamMatches(4, 1, 3)).toEqual([
      { roundIndex: 2, matchIndex: 2 },
      { roundIndex: 3, matchIndex: 1 },
      { roundIndex: 4, matchIndex: 1 },
    ]);
  });
});
