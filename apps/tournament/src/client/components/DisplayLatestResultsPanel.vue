<script setup lang="ts">
import { computed } from 'vue';
import DisplayFit from './DisplayFit.vue';
import { latestResultsRound, matchGroupLabel } from '../lib/format';
import type { PublicTournamentState } from '../types';

const props = defineProps<{ state: PublicTournamentState }>();
const round = computed(() => latestResultsRound(props.state.matches));
</script>

<template>
  <section class="display-panel display-panel--results" aria-labelledby="display-results-title">
    <header class="display-panel__heading">
      <div>
        <p class="eyebrow">Fase de liga</p>
        <h1 id="display-results-title">Últimos resultados</h1>
      </div>
      <p v-if="round" class="display-panel__context">Jornada {{ round.roundNumber }}</p>
    </header>

    <DisplayFit v-if="round">
      <div class="display-results-grid">
        <article v-for="match in round.matches" :key="match.id" class="display-match">
          <p class="display-match__meta">Jogo {{ match.gameNumber }} · {{ matchGroupLabel(match) }}</p>
          <div class="display-match__scoreline">
            <span class="display-match__team">{{ match.teamA.name }}</span>
            <strong>{{ match.scoreA ?? '-' }} <i>-</i> {{ match.scoreB ?? '-' }}</strong>
            <span class="display-match__team display-match__team--away">{{ match.teamB.name }}</span>
          </div>
        </article>
      </div>
    </DisplayFit>
    <p v-else class="display-empty">Ainda não existe calendário para a fase de liga.</p>
  </section>
</template>
