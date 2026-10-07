export interface ScoreDraft {
  scoreA: string;
  scoreB: string;
}

export interface ScorePair {
  scoreA: number;
  scoreB: number;
}

export function parseScoreDraft(draft: ScoreDraft): ScorePair | null {
  if (!/^\d+$/.test(draft.scoreA) || !/^\d+$/.test(draft.scoreB)) {
    return null;
  }

  return {
    scoreA: Number(draft.scoreA),
    scoreB: Number(draft.scoreB),
  };
}
