import type { Component } from 'vue';
import { DISPLAY_PANEL_TYPES, type DisplayPanelType } from './types/tournament';
import DisplayClassificationPanel from './components/DisplayClassificationPanel.vue';
import DisplayLatestResultsPanel from './components/DisplayLatestResultsPanel.vue';
import DisplayNextMatchPanel from './components/DisplayNextMatchPanel.vue';

export interface DisplayPanelDefinition {
  label: string;
  description: string;
  component: Component;
}

const panels = {
  'next-match': {
    label: 'Próximo jogo',
    description: 'Mostra o próximo jogo por disputar e qual vem a seguir.',
    component: DisplayNextMatchPanel,
  },
  'latest-results': {
    label: 'Últimos resultados',
    description: 'Mostra a jornada mais recente com resultados registados.',
    component: DisplayLatestResultsPanel,
  },
  classification: {
    label: 'Classificação',
    description: 'Mostra a classificação actual de todos os grupos.',
    component: DisplayClassificationPanel,
  },
} satisfies Record<DisplayPanelType, DisplayPanelDefinition>;

export const displayPanelDefinitions = DISPLAY_PANEL_TYPES.map((type) => ({ type, ...panels[type] }));

export function displayPanelDefinition(type: DisplayPanelType): DisplayPanelDefinition {
  return panels[type] ?? panels['latest-results'];
}
