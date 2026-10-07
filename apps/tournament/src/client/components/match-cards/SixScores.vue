<script lang="ts">
export const layout = {
  id: 'six-scores',
  name: 'Resultado 6 partidas + Total',
  description: 'Seis campos de resultado e um total para cada equipa.',
  order: 3,
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
          style="--score-count: 6; --score-box-size: 1.55rem"
          :aria-label="`Seis resultados da equipa ${side}`"
        >
          <span v-for="score in 6" :key="score"></span>
        </div>
        <div class="match-result-card__final-score" :aria-label="`Total da equipa ${side}`">
          <span></span>
          <small>Total</small>
        </div>
      </div>
    </template>
  </MatchResultCard>
</template>
