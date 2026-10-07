<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { displayPanelDefinition } from '../displayPanels';
import { matchGroupLabel, unfinishedLeagueMatches } from '../lib/format';
import { api, messageFor } from '../lib/api';
import { parseScoreDraft, type ScoreDraft } from '../lib/score';
import { usePublicTournamentState } from '../lib/usePublicTournamentState';
import type { LeagueMatch } from '../types';

const { initialLoading, refreshError, refreshState, state } = usePublicTournamentState();
const scoreDraft = ref<ScoreDraft>({ scoreA: '', scoreB: '' });
const scoreError = ref('');
const scoreSuccess = ref('');
const savingScore = ref(false);
const displayError = ref('');
const displaySuccess = ref('');
const updatingDisplay = ref(false);

const unfinishedMatches = computed(() => unfinishedLeagueMatches(state.value?.matches ?? []));
const currentMatch = computed(() => unfinishedMatches.value[0] ?? null);
const upcomingMatches = computed(() => unfinishedMatches.value.slice(1, 6));
const completedMatchCount = computed(() => (state.value?.matches ?? [])
  .filter((match) => match.scoreA !== null && match.scoreB !== null).length);
const totalMatchCount = computed(() => state.value?.matches.length ?? 0);
const progressPercent = computed(() => totalMatchCount.value === 0
  ? 0
  : Math.round((completedMatchCount.value / totalMatchCount.value) * 100));
const currentDisplay = computed(() => state.value
  ? displayPanelDefinition(state.value.display.activePanel)
  : null);
const groupLeaders = computed(() => (state.value?.groupStandings ?? [])
  .map((standing) => ({ group: standing.group, leader: standing.rows[0] ?? null })));
const finalStageStatus = computed(() => {
  if (!state.value) return '';
  if (state.value.finalStage.champion) return `Campeão: ${state.value.finalStage.champion.name}`;
  if (state.value.finalStage.roundCount) return 'Fase final configurada';
  if (totalMatchCount.value > 0 && unfinishedMatches.value.length === 0) return 'A fase de liga terminou. Pode configurar a fase final.';
  return 'Fase final ainda não configurada';
});

watch(() => currentMatch.value?.id ?? null, () => {
  scoreDraft.value = { scoreA: '', scoreB: '' };
  scoreError.value = '';
  scoreSuccess.value = '';
}, { immediate: true });

async function saveCurrentResult(match: LeagueMatch) {
  const score = parseScoreDraft(scoreDraft.value);
  if (!score) {
    scoreError.value = 'Introduza dois resultados inteiros iguais ou superiores a zero.';
    return;
  }

  savingScore.value = true;
  scoreError.value = '';
  scoreSuccess.value = '';
  try {
    await api(`/api/admin/matches/${match.id}/result`, {
      method: 'PUT',
      body: JSON.stringify(score),
    });
    scoreSuccess.value = 'Resultado guardado.';
    await refreshState();
  } catch (caught) {
    scoreError.value = messageFor(caught);
  } finally {
    savingScore.value = false;
  }
}

async function showNextMatchOnDisplay() {
  if (!state.value || updatingDisplay.value) return;
  updatingDisplay.value = true;
  displayError.value = '';
  displaySuccess.value = '';
  try {
    await api('/api/admin/display', {
      method: 'PUT',
      body: JSON.stringify({
        activePanel: 'next-match',
        zoomPercent: state.value.display.zoomPercent,
      }),
    });
    displaySuccess.value = 'O próximo jogo está agora no ecrã.';
    await refreshState();
  } catch (caught) {
    displayError.value = messageFor(caught);
  } finally {
    updatingDisplay.value = false;
  }
}
</script>

<template>
  <section class="admin-page dashboard-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">Controlo do torneio</p>
        <h1>Dashboard</h1>
        <p class="muted">Acompanhe o progresso, introduza o próximo resultado e controle rapidamente o ecrã.</p>
      </div>
      <RouterLink class="button button--quiet" to="/results" target="_blank">Ver página pública</RouterLink>
    </div>

    <p v-if="initialLoading && !state" class="loading-state">A carregar o torneio...</p>
    <p v-else-if="!state" class="notice notice--error" role="alert">
      {{ refreshError || 'Não foi possível carregar o estado do torneio.' }}
      <button class="text-button" type="button" @click="refreshState">Tentar novamente</button>
    </p>

    <template v-else>
      <p v-if="refreshError" class="notice notice--error" role="status">A mostrar a última actualização. {{ refreshError }}</p>

      <div class="dashboard-summary-grid">
        <article class="panel dashboard-stat">
          <p>Jogos concluídos</p>
          <strong>{{ completedMatchCount }} / {{ totalMatchCount }}</strong>
          <div class="dashboard-progress" aria-hidden="true"><span :style="{ width: `${progressPercent}%` }"></span></div>
          <small>{{ progressPercent }}% da fase de liga</small>
        </article>
        <article class="panel dashboard-stat">
          <p>Jogos por disputar</p>
          <strong>{{ unfinishedMatches.length }}</strong>
          <small>{{ unfinishedMatches.length ? `Próximo: jogo ${currentMatch?.gameNumber}` : 'Fase de liga concluída' }}</small>
        </article>
        <article class="panel dashboard-stat">
          <p>Fase final</p>
          <strong>{{ state.finalStage.roundCount ? `${state.finalStage.roundCount} rondas` : '—' }}</strong>
          <small>{{ finalStageStatus }}</small>
        </article>
        <article class="panel dashboard-stat">
          <p>Ecrã actual</p>
          <strong>{{ currentDisplay?.label }}</strong>
          <small>Zoom {{ state.display.zoomPercent }}%</small>
        </article>
      </div>

      <div class="dashboard-main-grid">
        <section class="panel dashboard-current" aria-labelledby="dashboard-current-title">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Operação rápida</p>
              <h2 id="dashboard-current-title">Próximo jogo</h2>
            </div>
            <button
              v-if="currentMatch"
              class="button button--quiet button--small"
              type="button"
              :disabled="updatingDisplay"
              @click="showNextMatchOnDisplay"
            >
              {{ updatingDisplay ? 'A actualizar...' : 'Mostrar no ecrã' }}
            </button>
          </div>

          <template v-if="currentMatch">
            <p class="dashboard-current__meta">
              Jogo {{ currentMatch.gameNumber }} · Jornada {{ currentMatch.roundNumber }} · {{ matchGroupLabel(currentMatch) }}
            </p>
            <div class="dashboard-current__teams">
              <div><span>Equipa {{ currentMatch.teamA.number }}</span><strong>{{ currentMatch.teamA.name }}</strong></div>
              <b>VS</b>
              <div class="dashboard-current__away"><span>Equipa {{ currentMatch.teamB.number }}</span><strong>{{ currentMatch.teamB.name }}</strong></div>
            </div>
            <form class="dashboard-score-form" @submit.prevent="saveCurrentResult(currentMatch)">
              <label>
                {{ currentMatch.teamA.name }}
                <input v-model="scoreDraft.scoreA" inputmode="numeric" aria-label="Resultado da equipa A">
              </label>
              <span>-</span>
              <label>
                {{ currentMatch.teamB.name }}
                <input v-model="scoreDraft.scoreB" inputmode="numeric" aria-label="Resultado da equipa B">
              </label>
              <button class="button" type="submit" :disabled="savingScore">
                {{ savingScore ? 'A guardar...' : 'Guardar resultado' }}
              </button>
            </form>
            <p v-if="scoreError" class="form-error" role="alert">{{ scoreError }}</p>
            <p v-else-if="scoreSuccess" class="form-success" role="status">{{ scoreSuccess }}</p>
            <p v-if="displayError" class="form-error" role="alert">{{ displayError }}</p>
            <p v-else-if="displaySuccess" class="form-success" role="status">{{ displaySuccess }}</p>
          </template>
          <div v-else class="empty-state dashboard-current__empty">
            <h3>Fase de liga concluída</h3>
            <p>Todos os jogos do calendário têm resultado registado.</p>
          </div>
        </section>

        <section class="panel dashboard-upcoming" aria-labelledby="dashboard-upcoming-title">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Fila de jogos</p>
              <h2 id="dashboard-upcoming-title">A seguir</h2>
            </div>
            <RouterLink class="text-button" to="/admin/results">Todos os resultados</RouterLink>
          </div>
          <ol v-if="upcomingMatches.length" class="dashboard-upcoming-list">
            <li v-for="match in upcomingMatches" :key="match.id">
              <span>Jogo {{ match.gameNumber }}</span>
              <strong>{{ match.teamA.name }} <i>vs</i> {{ match.teamB.name }}</strong>
              <small>Jornada {{ match.roundNumber }} · {{ matchGroupLabel(match) }}</small>
            </li>
          </ol>
          <p v-else class="empty-inline">Não existem mais jogos na fila.</p>
        </section>
      </div>

      <section class="panel dashboard-leaders" aria-labelledby="dashboard-leaders-title">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Classificação actual</p>
            <h2 id="dashboard-leaders-title">Líderes dos grupos</h2>
          </div>
          <RouterLink class="text-button" to="/admin/results">Ver classificação completa</RouterLink>
        </div>
        <div class="dashboard-leader-grid">
          <article v-for="entry in groupLeaders" :key="entry.group.id" class="dashboard-leader-card">
            <p>{{ entry.group.name }}</p>
            <template v-if="entry.leader">
              <strong>{{ entry.leader.team.name }}</strong>
              <span>{{ entry.leader.points }} pontos · {{ entry.leader.played }} jogos</span>
            </template>
            <span v-else>Sem equipas</span>
          </article>
        </div>
      </section>

      <p v-if="totalMatchCount > 0 && unfinishedMatches.length > 0 && state.finalStage.roundCount" class="notice dashboard-warning">
        Ainda existem {{ unfinishedMatches.length }} jogos da fase de liga por concluir. A fase final já está configurada; confirme a classificação antes de preencher os apurados.
      </p>
    </template>
  </section>
</template>
