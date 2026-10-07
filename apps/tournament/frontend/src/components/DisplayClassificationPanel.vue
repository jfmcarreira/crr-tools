<script setup lang="ts">
import ClassificationTable from './ClassificationTable.vue';
import DisplayFit from './DisplayFit.vue';
import type { PublicTournamentState } from '../types';

defineProps<{ state: PublicTournamentState }>();
</script>

<template>
  <section class="display-panel display-panel--classification" aria-labelledby="display-classification-title">
    <header class="display-panel__heading">
      <div>
        <p class="eyebrow">Fase de liga</p>
        <h1 id="display-classification-title">Classificação</h1>
      </div>
    </header>

    <DisplayFit v-if="state.groupStandings.length">
      <div class="display-classification-grid">
        <section v-for="standing in state.groupStandings" :key="standing.group.id" class="display-standing">
          <h2>{{ standing.group.name }}</h2>
          <ClassificationTable
            v-if="standing.rows.length"
            :rows="standing.rows"
            :mode="state.tournament.classificationMode"
            compact
          />
          <p v-else class="display-standing__empty">Ainda não existem equipas neste grupo.</p>
        </section>
      </div>
    </DisplayFit>
    <p v-else class="display-empty">A classificação será apresentada quando existirem equipas.</p>
  </section>
</template>
