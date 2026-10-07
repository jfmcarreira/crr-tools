import type { Component } from 'vue';
import type { BracketMatch, BracketParticipant, BracketRound, LeagueMatch } from '../types';

interface MatchCardLayoutMetadata {
  id: string;
  name: string;
  description: string;
  order: number;
}

interface MatchCardLayoutModule {
  default: Component;
  layout: MatchCardLayoutMetadata;
}

export interface MatchCardTemplate extends MatchCardLayoutMetadata {
  component: Component;
}

export interface MatchCardMatch {
  id: string;
  phase: 'league' | 'final';
  roundNumber: number | null;
  context: string;
  teamA: BracketParticipant;
  teamB: BracketParticipant;
}

export function matchCardForLeagueMatch(match: LeagueMatch): MatchCardMatch {
  return {
    id: `league-${match.id}`,
    phase: 'league',
    roundNumber: match.roundNumber,
    context: `Jornada ${match.roundNumber} · Jogo ${match.gameNumber} · ${match.group?.name ?? 'Fase de liga'}`,
    teamA: { team: match.teamA, pending: false },
    teamB: { team: match.teamB, pending: false },
  };
}

export function matchCardForFinalMatch(round: BracketRound, match: BracketMatch): MatchCardMatch {
  return {
    id: `final-${round.roundIndex}-${match.matchIndex}`,
    phase: 'final',
    roundNumber: null,
    context: `Fase final · ${round.name} · Jogo ${match.matchIndex}`,
    teamA: match.teamA,
    teamB: match.teamB,
  };
}

export function matchCardForThirdPlaceMatch(roundIndex: number, match: BracketMatch): MatchCardMatch {
  return {
    id: `final-${roundIndex}-${match.matchIndex}`,
    phase: 'final',
    roundNumber: null,
    context: 'Fase final · Jogo do 3.º lugar',
    teamA: match.teamA,
    teamB: match.teamB,
  };
}

// A layout becomes selectable by exporting `layout` from any Vue file in this folder.
const modules = import.meta.glob<MatchCardLayoutModule>('./match-cards/*.vue', { eager: true });
const templates = Object.values(modules)
  .map(({ default: component, layout }) => ({ ...layout, component }))
  .sort((first, second) => first.order - second.order || first.name.localeCompare(second.name, 'pt-PT'));

if (!templates.length || new Set(templates.map((template) => template.id)).size !== templates.length) {
  throw new Error('Os layouts de cartões têm de ter identificadores únicos.');
}

export const matchCardTemplates: readonly MatchCardTemplate[] = templates;
export type MatchCardTemplateId = string;

export function matchCardTemplate(id: MatchCardTemplateId): MatchCardTemplate {
  return matchCardTemplates.find((template) => template.id === id) ?? matchCardTemplates[0];
}
