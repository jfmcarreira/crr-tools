import type {
  AutoQualifiedTeam,
  ClassificationMode,
  ClassificationRow,
  FinalSeedAssignment,
  FinalSeedPreview,
  GroupStanding,
} from './types/tournament.js';

function isPowerOfTwo(value: number): boolean {
  return value > 0 && (value & (value - 1)) === 0;
}

/**
 * Returns the seed number occupying each bracket slot. For four slots the
 * order is [1, 4, 2, 3], producing the usual 1-v-4 and 2-v-3 semi-finals.
 */
export function standardBracketSeedOrder(slotCount: number): number[] {
  if (!Number.isInteger(slotCount) || !isPowerOfTwo(slotCount)) {
    throw new RangeError('O número de lugares da fase final tem de ser uma potência de dois.');
  }

  if (slotCount === 1) return [1];

  let order = [1, 2];
  for (let size = 4; size <= slotCount; size *= 2) {
    order = order.flatMap((seed) => [seed, size + 1 - seed]);
  }
  return order;
}

function buildPreview(
  qualifiers: AutoQualifiedTeam[],
  slotCount: number,
  mode: FinalSeedPreview['mode'],
  qualifiersPerGroup: number | null,
): FinalSeedPreview {
  if (qualifiers.length > slotCount) {
    throw new RangeError('Existem mais equipas apuradas do que lugares na fase final.');
  }

  const qualifierBySeed = new Map(qualifiers.map((qualifier) => [qualifier.seedNumber, qualifier]));
  const seeds: FinalSeedAssignment[] = standardBracketSeedOrder(slotCount).map((seedNumber, index) => ({
    slotIndex: index + 1,
    teamId: qualifierBySeed.get(seedNumber)?.team.id ?? null,
  }));

  return {
    mode,
    qualifiersPerGroup,
    qualifierCount: qualifiers.length,
    qualifiers,
    seeds,
  };
}

/**
 * Builds a preview that takes the top N teams from every non-empty group.
 * Teams are ranked by group position, then group order, and placed using
 * standard bracket seeding. This naturally crosses groups in a two-group
 * bracket (1st A v 2nd B, 1st B v 2nd A).
 */
export function buildGroupQualificationPreview(
  groupStandings: readonly GroupStanding[],
  qualifiersPerGroup: number,
  slotCount: number,
): FinalSeedPreview {
  if (!Number.isInteger(qualifiersPerGroup) || qualifiersPerGroup < 1) {
    throw new RangeError('O número de apurados por grupo tem de ser positivo.');
  }

  const standings = [...groupStandings]
    .filter((standing) => standing.rows.length > 0)
    .sort((first, second) => first.group.sortOrder - second.group.sortOrder || first.group.id - second.group.id);

  const qualifiers: AutoQualifiedTeam[] = [];
  for (let groupPosition = 1; groupPosition <= qualifiersPerGroup; groupPosition += 1) {
    for (const standing of standings) {
      const row = standing.rows[groupPosition - 1];
      if (row) {
        qualifiers.push({
          seedNumber: qualifiers.length + 1,
          groupPosition,
          team: row.team,
        });
      }
    }
  }

  return buildPreview(qualifiers, slotCount, 'per-group', qualifiersPerGroup);
}

function compareAcrossGroups(first: ClassificationRow, second: ClassificationRow, mode: ClassificationMode): number {
  if (mode === 'total-points') {
    return second.points - first.points || first.team.number - second.team.number;
  }

  return second.points - first.points ||
    second.goalDifference - first.goalDifference ||
    second.goalsFor - first.goalsFor ||
    first.team.number - second.team.number;
}

/**
 * Selects the best N teams across all groups. Standard mode compares points,
 * goal difference and goals scored; total-points mode compares points only.
 * Team number provides a deterministic cross-group fallback.
 */
export function buildOverallQualificationPreview(
  groupStandings: readonly GroupStanding[],
  qualifierCount: number,
  slotCount: number,
  classificationMode: ClassificationMode,
): FinalSeedPreview {
  if (!Number.isInteger(qualifierCount) || qualifierCount < 1) {
    throw new RangeError('O número total de apurados tem de ser positivo.');
  }

  const rankedRows = groupStandings
    .flatMap((standing) => standing.rows)
    .sort((first, second) => compareAcrossGroups(first, second, classificationMode));

  if (qualifierCount > rankedRows.length) {
    throw new RangeError('Não existem equipas suficientes para esse número de apurados.');
  }

  const qualifiers = rankedRows.slice(0, qualifierCount).map((row, index) => ({
    seedNumber: index + 1,
    groupPosition: row.position,
    team: row.team,
  }));

  return buildPreview(qualifiers, slotCount, 'overall', null);
}
