<script setup lang="ts">
import { computed } from 'vue';
import { matchGroupLabel, unfinishedLeagueMatches } from '../lib/format';
import type { PublicTournamentState } from '../types';

const props = defineProps<{ state: PublicTournamentState }>();
const unfinished = computed(() => unfinishedLeagueMatches(props.state.matches));
const currentMatch = computed(() => unfinished.value[0] ?? null);
const followingMatch = computed(() => unfinished.value[1] ?? null);
</script>

<template>
  <section class="display-panel display-panel--next-match" aria-labelledby="display-next-match-title">
    <header class="display-panel__heading">
      <div>
        <p class="eyebrow">Fase de liga</p>
        <h1 id="display-next-match-title">Próximo jogo</h1>
      </div>
      <p v-if="currentMatch" class="display-panel__context">
        Jogo {{ currentMatch.gameNumber }} · Jornada {{ currentMatch.roundNumber }}
      </p>
    </header>

    <div v-if="currentMatch" class="display-next-match-layout">
      <article class="display-next-match-card">
        <p class="display-next-match-card__meta">{{ matchGroupLabel(currentMatch) }}</p>
        <div class="display-next-match-card__teams">
          <div>
            <span>Equipa {{ currentMatch.teamA.number }}</span>
            <strong>{{ currentMatch.teamA.name }}</strong>
          </div>
          <b>VS</b>
          <div class="display-next-match-card__team--away">
            <span>Equipa {{ currentMatch.teamB.number }}</span>
            <strong>{{ currentMatch.teamB.name }}</strong>
          </div>
        </div>
      </article>

      <article v-if="followingMatch" class="display-following-match">
        <div>
          <p>A seguir</p>
          <strong>Jogo {{ followingMatch.gameNumber }} · Jornada {{ followingMatch.roundNumber }}</strong>
        </div>
        <span>{{ followingMatch.teamA.name }} <i>vs</i> {{ followingMatch.teamB.name }}</span>
      </article>
    </div>

    <p v-else class="display-empty">Todos os jogos da fase de liga estão concluídos.</p>
  </section>
</template>
