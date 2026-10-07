<script lang="ts">
export const layout = {
  id: 'single-score',
  name: 'Resultado único',
  description: 'Registo simples do resultado final de cada jogo.',
  order: 1,
};
</script>

<script setup lang="ts">
import MatchResultCard from '../MatchResultCard.vue';
import type { MatchCardMatch } from '../matchCards';

const scoreSides = ['A', 'B'];

defineProps<{
  tournamentName: string;
  match: MatchCardMatch;
}>();
</script>

<template>
  <MatchResultCard :tournament-name="tournamentName" :match="match">
    <template #scores>
      <div v-for="side in scoreSides" :key="side" class="match-result-card__score-area">
        <div class="match-result-card__final-score" :aria-label="`Resultado da equipa ${side}`">
          <span></span>
          <small>Resultado</small>
        </div>
      </div>
    </template>
  </MatchResultCard>
</template>
