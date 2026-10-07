<script lang="ts">
export const layout = {
  id: 'four-scores',
  name: 'Resultado 4 partidas + Total',
  description: 'Quatro campos de resultado e um total para cada equipa.',
  order: 2,
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
        <div
          class="match-result-card__score-fields"
          style="--score-count: 4; --score-box-size: 2rem"
          :aria-label="`Quatro resultados da equipa ${side}`"
        >
          <span v-for="score in 4" :key="score"></span>
        </div>
        <div class="match-result-card__final-score" :aria-label="`Total da equipa ${side}`">
          <span></span>
          <small>Total</small>
        </div>
      </div>
    </template>
  </MatchResultCard>
</template>
