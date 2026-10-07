import { spawnSync } from 'node:child_process';

function call(name, args) {
  const result = spawnSync(process.env.TOURNAMENT_PYTHON, [process.env.TOURNAMENT_BRIDGE], {
    input: JSON.stringify({ name, args }), encoding: 'utf8', env: process.env,
  });
  if (result.status !== 0) throw new Error(result.stderr || 'Python bridge failed');
  const value = JSON.parse(result.stdout);
  if (value.error) throw new RangeError(value.error);
  return value.result;
}

export const generateRoundRobinSchedule = (...args) => call('calendar', args);
export const calculateClassification = (...args) => call('classification', args);
export const calculateBracket = (...args) => call('bracket', args);
export const downstreamMatches = (...args) => call('downstream', args);
export const standardBracketSeedOrder = (...args) => call('seed-order', args);
export const buildGroupQualificationPreview = (...args) => call('group-qualification', args);
export const buildOverallQualificationPreview = (...args) => call('overall-qualification', args);
