import { describe, expect, it } from 'vitest';
import type { GroupStanding, TeamSummary } from './types/tournament';
import { buildGroupQualificationPreview, buildOverallQualificationPreview, standardBracketSeedOrder } from './finalSeeding';

function team(id: number, number: number, name: string, groupId: number, groupName: string): TeamSummary {
  return { id, number, name, group: { id: groupId, name: groupName, sortOrder: groupId - 1 } };
}

function standing(groupId: number, groupName: string, teams: TeamSummary[]): GroupStanding {
  return {
    group: { id: groupId, name: groupName, sortOrder: groupId - 1 },
    rows: teams.map((entry, index) => ({
      position: index + 1,
      team: entry,
      played: 1,
      wins: index === 0 ? 1 : 0,
      draws: 0,
      losses: index === 0 ? 0 : 1,
      goalsFor: index === 0 ? 3 : 1,
      goalsAgainst: index === 0 ? 1 : 3,
      goalDifference: index === 0 ? 2 : -2,
      points: index === 0 ? 3 : 0,
    })),
  };
}

describe('final seeding', () => {
  it('uses standard bracket seed placement', () => {
    expect(standardBracketSeedOrder(2)).toEqual([1, 2]);
    expect(standardBracketSeedOrder(4)).toEqual([1, 4, 2, 3]);
    expect(standardBracketSeedOrder(8)).toEqual([1, 8, 4, 5, 2, 7, 3, 6]);
  });

  it('crosses the top two teams from two groups in the semi-finals', () => {
    const a1 = team(1, 1, 'A1', 1, 'Grupo A');
    const a2 = team(2, 2, 'A2', 1, 'Grupo A');
    const b1 = team(3, 3, 'B1', 2, 'Grupo B');
    const b2 = team(4, 4, 'B2', 2, 'Grupo B');

    const preview = buildGroupQualificationPreview([
      standing(1, 'Grupo A', [a1, a2]),
      standing(2, 'Grupo B', [b1, b2]),
    ], 2, 4);

    expect(preview).toMatchObject({ mode: 'per-group', qualifiersPerGroup: 2, qualifierCount: 4 });
    expect(preview.qualifiers.map((qualifier) => qualifier.team.id)).toEqual([a1.id, b1.id, a2.id, b2.id]);
    expect(preview.seeds).toEqual([
      { slotIndex: 1, teamId: a1.id },
      { slotIndex: 2, teamId: b2.id },
      { slotIndex: 3, teamId: b1.id },
      { slotIndex: 4, teamId: a2.id },
    ]);
  });

  it('leaves lower seeds empty when the bracket has extra slots', () => {
    const a1 = team(1, 1, 'A1', 1, 'Grupo A');
    const b1 = team(2, 2, 'B1', 2, 'Grupo B');

    const preview = buildGroupQualificationPreview([
      standing(1, 'Grupo A', [a1]),
      standing(2, 'Grupo B', [b1]),
    ], 1, 4);

    expect(preview.seeds).toEqual([
      { slotIndex: 1, teamId: a1.id },
      { slotIndex: 2, teamId: null },
      { slotIndex: 3, teamId: b1.id },
      { slotIndex: 4, teamId: null },
    ]);
  });

  it('can select the best teams across all groups', () => {
    const a1 = team(1, 1, 'A1', 1, 'Grupo A');
    const a2 = team(2, 2, 'A2', 1, 'Grupo A');
    const b1 = team(3, 3, 'B1', 2, 'Grupo B');
    const b2 = team(4, 4, 'B2', 2, 'Grupo B');
    const groupA = standing(1, 'Grupo A', [a1, a2]);
    const groupB = standing(2, 'Grupo B', [b1, b2]);
    groupB.rows[0].points = 6;
    groupB.rows[0].goalDifference = 4;

    const preview = buildOverallQualificationPreview([groupA, groupB], 2, 4, 'standard');

    expect(preview).toMatchObject({ mode: 'overall', qualifiersPerGroup: null, qualifierCount: 2 });
    expect(preview.qualifiers.map((qualifier) => qualifier.team.id)).toEqual([b1.id, a1.id]);
    expect(preview.seeds).toEqual([
      { slotIndex: 1, teamId: b1.id },
      { slotIndex: 2, teamId: null },
      { slotIndex: 3, teamId: a1.id },
      { slotIndex: 4, teamId: null },
    ]);
  });

});
