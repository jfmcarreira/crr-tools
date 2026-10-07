import { describe, expect, it } from 'vitest';
import { parseScoreDraft } from './score';

describe('parseScoreDraft', () => {
  it('parses non-negative integer scores', () => {
    expect(parseScoreDraft({ scoreA: '0', scoreB: '12' })).toEqual({ scoreA: 0, scoreB: 12 });
  });

  it.each([
    { scoreA: '', scoreB: '1' },
    { scoreA: '-1', scoreB: '1' },
    { scoreA: '1.5', scoreB: '2' },
    { scoreA: 'a', scoreB: '2' },
  ])('rejects invalid score drafts: %o', (draft) => {
    expect(parseScoreDraft(draft)).toBeNull();
  });
});
