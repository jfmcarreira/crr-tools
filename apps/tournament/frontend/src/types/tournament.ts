export interface Group {
  id: number;
  name: string;
  sortOrder: number;
}

export interface TeamSummary {
  id: number;
  number: number;
  name: string;
  group: Group;
}

export interface Player {
  id: number;
  teamId: number;
  name: string;
  sortOrder: number;
}

export interface Team extends TeamSummary {
  players: Player[];
}

export const CLASSIFICATION_MODES = ['standard', 'total-points'] as const;
export type ClassificationMode = typeof CLASSIFICATION_MODES[number];

export const DISPLAY_PANEL_TYPES = ['next-match', 'latest-results', 'classification'] as const;
export type DisplayPanelType = typeof DISPLAY_PANEL_TYPES[number];

export const DISPLAY_ZOOM_MIN_PERCENT = 50;
export const DISPLAY_ZOOM_MAX_PERCENT = 400;
export type DisplayZoomPercent = number;

export function isDisplayPanelType(value: string): value is DisplayPanelType {
  return (DISPLAY_PANEL_TYPES as readonly string[]).includes(value);
}

export function isDisplayZoomPercent(value: number): value is DisplayZoomPercent {
  return Number.isInteger(value) && value >= DISPLAY_ZOOM_MIN_PERCENT && value <= DISPLAY_ZOOM_MAX_PERCENT;
}

export interface DisplaySettings {
  activePanel: DisplayPanelType;
  zoomPercent: DisplayZoomPercent;
}

export interface TournamentSettings {
  name: string;
  classificationMode: ClassificationMode;
  finalRoundCount: number | null;
  thirdPlaceEnabled: boolean;
}

export interface LeagueMatch {
  id: number;
  gameNumber: number;
  roundNumber: number;
  /** Whether this round's results contribute to the group standings. */
  countsTowardStandings: boolean;
  /** The common group, or null for a match between groups. */
  group: Group | null;
  teamA: TeamSummary;
  teamB: TeamSummary;
  scoreA: number | null;
  scoreB: number | null;
}

export type CalendarLegs = 1 | 2;

export interface CalendarGeneration {
  legs: CalendarLegs;
  teamOrder: Array<{ teamId: number; groupId: number }>;
}

export interface CalendarPreviewMatch {
  gameNumber: number;
  roundNumber: number;
  group: Group;
  teamA: TeamSummary;
  teamB: TeamSummary;
}

export interface CalendarResponse {
  matches: LeagueMatch[];
  matchCount: number;
  roundCount: number;
}

export interface CalendarGenerationPreview {
  generation: CalendarGeneration;
  matches: CalendarPreviewMatch[];
  matchCount: number;
  roundCount: number;
}

export interface ClassificationRow {
  position: number;
  team: TeamSummary;
  played: number;
  wins: number;
  draws: number;
  losses: number;
  goalsFor: number;
  goalsAgainst: number;
  goalDifference: number;
  points: number;
}

export interface GroupStanding {
  group: Group;
  rows: ClassificationRow[];
}

export interface FinalSeedAssignment {
  slotIndex: number;
  teamId: number | null;
}

export const FINAL_QUALIFICATION_MODES = ['per-group', 'overall'] as const;
export type FinalQualificationMode = typeof FINAL_QUALIFICATION_MODES[number];

export interface AutoQualifiedTeam {
  seedNumber: number;
  groupPosition: number;
  team: TeamSummary;
}

export interface FinalSeedPreview {
  mode: FinalQualificationMode;
  qualifiersPerGroup: number | null;
  qualifierCount: number;
  qualifiers: AutoQualifiedTeam[];
  seeds: FinalSeedAssignment[];
}

export interface BracketParticipant {
  team: TeamSummary | null;
  pending: boolean;
}

export interface BracketMatch {
  matchIndex: number;
  teamA: BracketParticipant;
  teamB: BracketParticipant;
  scoreA: number | null;
  scoreB: number | null;
  winner: TeamSummary | null;
  isBye: boolean;
}

export interface BracketRound {
  roundIndex: number;
  name: string;
  matches: BracketMatch[];
}

export interface FinalStage {
  roundCount: number | null;
  thirdPlaceEnabled: boolean;
  rounds: BracketRound[];
  thirdPlaceMatch: BracketMatch | null;
  champion: TeamSummary | null;
}

export interface PublicTournamentState {
  tournament: TournamentSettings;
  display: DisplaySettings;
  groups: Group[];
  matches: LeagueMatch[];
  groupStandings: GroupStanding[];
  finalStage: FinalStage;
}
