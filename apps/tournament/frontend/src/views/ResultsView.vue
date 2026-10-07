<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import AppModal from '../components/AppModal.vue';
import ClassificationTable from '../components/ClassificationTable.vue';
import { groupMatches, matchGroupLabel } from '../lib/format';
import { api, messageFor } from '../lib/api';
import { parseScoreDraft, type ScoreDraft } from '../lib/score';
import type { LeagueMatch, PublicTournamentState } from '../types';


const state = ref<PublicTournamentState | null>(null);
const loading = ref(true);
const loadError = ref('');
const scoreDrafts = ref<Record<number, ScoreDraft>>({});
const matchErrors = ref<Record<number, string>>({});
const matchSuccess = ref<Record<number, string>>({});
const savingMatch = ref<number | null>(null);
const pendingClear = ref<LeagueMatch | null>(null);
const clearing = ref(false);
const roundErrors = ref<Record<number, string>>({});
const savingRound = ref<number | null>(null);

const groupedMatches = computed(() => groupMatches(state.value?.matches ?? []));
const groupStandings = computed(() => state.value?.groupStandings ?? []);

function prepareDrafts(matches: LeagueMatch[]) {
  scoreDrafts.value = Object.fromEntries(matches.map((match) => [match.id, {
    scoreA: match.scoreA === null ? '' : String(match.scoreA),
    scoreB: match.scoreB === null ? '' : String(match.scoreB),
  }]));
}

async function load() {
  const isInitialLoad = state.value === null;
  if (isInitialLoad) loading.value = true;
  loadError.value = '';
  try {
    state.value = await api<PublicTournamentState>('/api/public/state');
    prepareDrafts(state.value.matches);
  } catch (caught) {
    loadError.value = messageFor(caught);
  } finally {
    if (isInitialLoad) loading.value = false;
  }
}

async function saveResult(match: LeagueMatch) {
  const draft = scoreDrafts.value[match.id];
  const score = draft ? parseScoreDraft(draft) : null;
  if (!score) {
    matchErrors.value[match.id] = 'Introduza dois resultados inteiros iguais ou superiores a zero.';
    return;
  }

  savingMatch.value = match.id;
  matchErrors.value[match.id] = '';
  matchSuccess.value[match.id] = '';
  try {
    await api(`/api/admin/matches/${match.id}/result`, {
      method: 'PUT',
      body: JSON.stringify(score),
    });
    matchSuccess.value[match.id] = 'Resultado guardado.';
    await load();
  } catch (caught) {
    matchErrors.value[match.id] = messageFor(caught);
  } finally {
    savingMatch.value = null;
  }
}

async function clearResult() {
  const match = pendingClear.value;
  if (!match) return;
  clearing.value = true;
  matchErrors.value[match.id] = '';
  try {
    await api(`/api/admin/matches/${match.id}/result`, { method: 'DELETE' });
    pendingClear.value = null;
    await load();
  } catch (caught) {
    matchErrors.value[match.id] = messageFor(caught);
    pendingClear.value = null;
  } finally {
    clearing.value = false;
  }
}

function roundCountsTowardStandings(roundNumber: number): boolean {
  return state.value?.matches.find((match) => match.roundNumber === roundNumber)?.countsTowardStandings ?? false;
}

async function updateRoundStandings(roundNumber: number) {
  const countsTowardStandings = !roundCountsTowardStandings(roundNumber);
  savingRound.value = roundNumber;
  roundErrors.value[roundNumber] = '';
  try {
    await api(`/api/admin/rounds/${roundNumber}/standings`, {
      method: 'PUT',
      body: JSON.stringify({ countsTowardStandings }),
    });
    await load();
  } catch (caught) {
    roundErrors.value[roundNumber] = messageFor(caught);
  } finally {
    savingRound.value = null;
  }
}

onMounted(load);
</script>

<template>
  <section class="admin-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">Fase de liga</p>
        <h1>Resultados</h1>
        <p class="muted">Introduza, corrija ou limpe os resultados de cada jogo.</p>
      </div>
    </div>

    <p v-if="loadError" class="notice notice--error" role="alert">{{ loadError }} <button class="text-button" @click="load">Tentar novamente</button></p>
    <p v-else-if="loading" class="loading-state">A carregar resultados...</p>
    <template v-else-if="state">
      <div v-if="groupedMatches.length" class="result-rounds">
        <section v-for="group in groupedMatches" :key="group.roundNumber" class="result-round panel">
          <div class="section-heading">
            <h2>Jornada {{ group.roundNumber }}</h2>
            <button
              class="result-round__standings"
              :class="{ 'result-round__standings--enabled': roundCountsTowardStandings(group.roundNumber) }"
              type="button"
              :aria-pressed="roundCountsTowardStandings(group.roundNumber)"
              :disabled="savingRound === group.roundNumber"
              @click="updateRoundStandings(group.roundNumber)"
            >
              {{ roundCountsTowardStandings(group.roundNumber) ? 'A contabilizar na classificação' : 'Não contabilizar na classificação' }}
            </button>
          </div>
          <p v-if="roundErrors[group.roundNumber]" class="form-error" role="alert">{{ roundErrors[group.roundNumber] }}</p>
          <article v-for="match in group.matches" :key="match.id" class="result-editor">
            <p class="game-number">Jogo {{ match.gameNumber }} <span class="match-group-label">{{ matchGroupLabel(match) }}</span></p>
            <form @submit.prevent="saveResult(match)">
              <div class="score-entry">
                <label class="score-entry__team"><span>{{ match.teamA.name }}</span><input v-model="scoreDrafts[match.id].scoreA" inputmode="numeric" aria-label="Resultado da equipa A" /></label>
                <span class="score-separator">-</span>
                <label class="score-entry__team score-entry__team--away"><input v-model="scoreDrafts[match.id].scoreB" inputmode="numeric" aria-label="Resultado da equipa B" /><span>{{ match.teamB.name }}</span></label>
              </div>
              <div class="result-editor__actions">
                <button class="button button--small" type="submit" :disabled="savingMatch === match.id">{{ savingMatch === match.id ? 'A guardar...' : 'Guardar' }}</button>
                <button v-if="match.scoreA !== null && match.scoreB !== null" class="button button--quiet button--small" type="button" @click="pendingClear = match">Limpar resultado</button>
              </div>
            </form>
            <p v-if="matchErrors[match.id]" class="form-error" role="alert">{{ matchErrors[match.id] }}</p>
            <p v-else-if="matchSuccess[match.id]" class="form-success">{{ matchSuccess[match.id] }}</p>
          </article>
        </section>
      </div>
      <section v-else class="empty-state">
        <h2>Sem jogos no calendário</h2>
        <p>Sorteie o calendário antes de introduzir resultados.</p>
        <RouterLink class="button" to="/admin/calendar">Ir para o calendário</RouterLink>
      </section>

      <section class="classification-section" aria-labelledby="classification-title">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Actualizada automaticamente</p>
            <h2 id="classification-title">Classificação</h2>
          </div>
        </div>
        <div v-if="groupStandings.length" class="group-standings">
          <section v-for="standing in groupStandings" :key="standing.group.id" class="group-standing">
            <h3>{{ standing.group.name }}</h3>
            <ClassificationTable :rows="standing.rows" :mode="state.tournament.classificationMode" />
          </section>
        </div>
        <p v-else class="empty-inline">A classificação por grupo aparece depois de as equipas estarem criadas.</p>
      </section>
    </template>

    <AppModal
      :open="Boolean(pendingClear)"
      title="Limpar resultado"
      confirm-label="Limpar resultado"
      destructive
      :busy="clearing"
      @close="pendingClear = null"
      @confirm="clearResult"
    >
      <p>Tem a certeza de que pretende limpar o resultado do jogo {{ pendingClear?.gameNumber }}?</p>
      <p class="muted">A classificação será atualizada conforme a definição da jornada.</p>
    </AppModal>
  </section>
</template>
