<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import {
  matchCardForFinalMatch,
  matchCardForLeagueMatch,
  matchCardForThirdPlaceMatch,
  matchCardTemplate,
  matchCardTemplates,
  type MatchCardTemplateId,
} from '../components/matchCards';
import { api, messageFor } from '../lib/api';
import type { PublicTournamentState } from '../types';

const state = ref<PublicTournamentState | null>(null);
const loading = ref(true);
const loadError = ref('');
const selectedTemplateId = ref<MatchCardTemplateId>('single-score');
const selectedMatchFilter = ref<'all' | 'final' | number>('all');

const rounds = computed(() => [...new Set(state.value?.matches.map((match) => match.roundNumber) ?? [])]
  .sort((first, second) => first - second));
const selectedTemplate = computed(() => matchCardTemplate(selectedTemplateId.value));
const leagueMatchCards = computed(() => (state.value?.matches ?? []).map(matchCardForLeagueMatch));
const finalMatchCards = computed(() => {
  const finalStage = state.value?.finalStage;
  if (!finalStage || finalStage.roundCount === null) return [];

  const cards = finalStage.rounds.flatMap((round) => (
    round.matches.map((match) => matchCardForFinalMatch(round, match))
  ));
  return finalStage.thirdPlaceMatch
    ? [...cards, matchCardForThirdPlaceMatch(finalStage.roundCount, finalStage.thirdPlaceMatch)]
    : cards;
});
const cardMatches = computed(() => [...leagueMatchCards.value, ...finalMatchCards.value]);
const matchesToPrint = computed(() => cardMatches.value.filter((match) => {
  if (selectedMatchFilter.value === 'all') return true;
  if (selectedMatchFilter.value === 'final') return match.phase === 'final';
  return match.phase === 'league' && match.roundNumber === selectedMatchFilter.value;
}));
const previewMatch = computed(() => matchesToPrint.value[0] ?? null);

async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    state.value = await api<PublicTournamentState>('/api/public/state');
  } catch (caught) {
    loadError.value = messageFor(caught);
  } finally {
    loading.value = false;
  }
}

function exportPdf() {
  window.print();
}

onMounted(load);
</script>

<template>
  <section class="admin-page match-cards-page">
    <div class="page-heading match-cards-page__heading">
      <div>
        <p class="eyebrow">Fase de liga e final</p>
        <h1>Cartões de jogo</h1>
        <p class="muted">Escolha o cartão adequado ao formato do torneio e imprima-o em A4.</p>
      </div>
    </div>

    <p v-if="loadError" class="notice notice--error" role="alert">{{ loadError }} <button class="text-button" @click="load">Tentar novamente</button></p>
    <p v-else-if="loading" class="loading-state">A carregar cartões...</p>
    <template v-else-if="state">
      <section v-if="cardMatches.length" class="panel match-card-controls" aria-labelledby="card-print-title">
        <div>
          <h2 id="card-print-title">Cartão e impressão</h2>
          <p class="muted">Escolha o tipo de cartão e os jogos a incluir. Cada página A4 tem cinco linhas e duas colunas.</p>
        </div>
        <div class="match-card-template-grid" role="radiogroup" aria-label="Tipo de cartão">
          <button
            v-for="template in matchCardTemplates"
            :key="template.id"
            class="match-card-template-option"
            :class="{ 'match-card-template-option--active': selectedTemplateId === template.id }"
            type="button"
            role="radio"
            :aria-checked="selectedTemplateId === template.id"
            @click="selectedTemplateId = template.id"
          >
            <strong>{{ template.name }}</strong>
            <span>{{ template.description }}</span>
          </button>
        </div>
        <div class="match-card-actions">
          <label>
            Jogos a incluir
            <select v-model="selectedMatchFilter">
              <option value="all">Todos os jogos ({{ cardMatches.length }} jogos)</option>
              <option v-for="round in rounds" :key="round" :value="round">Jornada {{ round }}</option>
              <option v-if="finalMatchCards.length" value="final">Fase final ({{ finalMatchCards.length }} jogos)</option>
            </select>
          </label>
          <button class="button" type="button" @click="exportPdf">Imprimir / guardar em PDF</button>
        </div>
        <p class="match-card-controls__hint">No diálogo de impressão, seleccione “Guardar como PDF” e desactive “Cabeçalhos e rodapés”.</p>
      </section>

      <section v-if="previewMatch" class="panel match-card-preview" aria-labelledby="match-card-preview-title">
        <div>
          <h2 id="match-card-preview-title">Pré-visualização à escala</h2>
          <p class="muted">Este cartão mede 93 × 52 mm, igual a cada posição na página impressa.</p>
        </div>
        <div class="match-card-preview__viewport">
          <div class="match-card-preview__card">
            <component
              :is="selectedTemplate.component"
              :tournament-name="state.tournament.name"
              :match="previewMatch"
            />
          </div>
        </div>
      </section>

      <section v-if="matchesToPrint.length" class="match-cards-print match-cards-print--rows-5" aria-label="Pré-visualização dos cartões">
        <div class="match-cards-print__heading">
          <div>
            <p class="eyebrow">Pré-visualização</p>
            <h2>{{ selectedTemplate.name }}</h2>
          </div>
          <span>{{ matchesToPrint.length }} {{ matchesToPrint.length === 1 ? 'cartão' : 'cartões' }}</span>
        </div>
        <div class="match-cards-print__grid">
          <component
            :is="selectedTemplate.component"
            v-for="match in matchesToPrint"
            :key="match.id"
            :tournament-name="state.tournament.name"
            :match="match"
          />
        </div>
      </section>
      <section v-else class="empty-state">
        <h2>Sem jogos nesta jornada</h2>
        <p>Seleccione outra jornada para criar os cartões de jogo.</p>
      </section>
    </template>
  </section>
</template>
