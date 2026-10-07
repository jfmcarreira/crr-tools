<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AppLogo from '../components/AppLogo.vue';
import ClassificationTable from '../components/ClassificationTable.vue';
import FinalBracket from '../components/FinalBracket.vue';
import { groupMatches, matchGroupLabel } from '../lib/format';
import { usePublicTournamentState } from '../lib/usePublicTournamentState';
import type { TeamSummary } from '../types';

const route = useRoute();
const router = useRouter();
const { connection, initialLoading, lastUpdated, refreshError, refreshState, state } = usePublicTournamentState();

const allTeams = computed(() => (state.value?.groupStandings ?? [])
  .flatMap((standing) => standing.rows.map((row) => row.team))
  .sort((first, second) => first.number - second.number));
const selectedTeamNumber = computed(() => {
  const raw = Array.isArray(route.query.team) ? route.query.team[0] : route.query.team;
  if (!raw) return null;
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed > 0 ? parsed : null;
});
const selectedTeam = computed(() => allTeams.value.find((team) => team.number === selectedTeamNumber.value) ?? null);
const selectedTeamMatches = computed(() => {
  const matches = state.value?.matches ?? [];
  const team = selectedTeam.value;
  return team
    ? matches.filter((match) => match.teamA.id === team.id || match.teamB.id === team.id)
    : matches;
});
const groupedMatches = computed(() => groupMatches(selectedTeamMatches.value));
const groupStandings = computed(() => {
  const standings = state.value?.groupStandings ?? [];
  return selectedTeam.value
    ? standings.filter((standing) => standing.group.id === selectedTeam.value?.group.id)
    : standings;
});
const selectedStanding = computed(() => {
  const team = selectedTeam.value;
  if (!team) return null;
  return state.value?.groupStandings
    .find((standing) => standing.group.id === team.group.id)
    ?.rows.find((row) => row.team.id === team.id) ?? null;
});
const nextTeamMatch = computed(() => selectedTeam.value
  ? [...selectedTeamMatches.value]
      .sort((first, second) => first.gameNumber - second.gameNumber)
      .find((match) => match.scoreA === null || match.scoreB === null) ?? null
  : null);
const completedTeamMatches = computed(() => selectedTeam.value
  ? selectedTeamMatches.value.filter((match) => match.scoreA !== null && match.scoreB !== null).length
  : 0);
const displayUpdatedAt = computed(() => lastUpdated.value
  ? new Intl.DateTimeFormat('pt-PT', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(lastUpdated.value)
  : '');

function showTeam(team: TeamSummary) {
  void router.replace({ query: { ...route.query, team: String(team.number) } });
}

function selectTeamFromControl(event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  if (!value) {
    clearTeamFilter();
    return;
  }
  const team = allTeams.value.find((entry) => entry.number === Number(value));
  if (team) showTeam(team);
}

function clearTeamFilter() {
  const query = { ...route.query };
  delete query.team;
  void router.replace({ query });
}
</script>

<template>
  <main class="public-page">
    <header class="public-hero">
      <AppLogo large light />
      <div class="public-hero__title">
        <p class="eyebrow">Resultados em directo</p>
        <h1>{{ state?.tournament.name || 'Torneio' }}</h1>
      </div>
      <div class="live-status" :class="{ 'live-status--waiting': connection !== 'connected' }" aria-live="polite">
        <span class="live-status__dot" aria-hidden="true"></span>
        <span>{{ connection === 'connected' ? 'Em directo' : 'A tentar restabelecer ligação...' }}</span>
      </div>
    </header>

    <div v-if="initialLoading && !state" class="public-loading">A carregar resultados...</div>
    <div v-else-if="!state" class="public-unavailable">
      <h2>Resultados temporariamente indisponíveis</h2>
      <p>{{ refreshError || 'Não foi possível carregar o estado do torneio.' }}</p>
      <button class="button" type="button" @click="refreshState">Tentar novamente</button>
    </div>
    <div v-else class="public-content">
      <p v-if="refreshError" class="public-offline-notice" role="status">A mostrar a última actualização. {{ refreshError }}</p>
      <p v-else-if="displayUpdatedAt" class="updated-at">Actualizado às {{ displayUpdatedAt }}</p>

      <section class="public-team-filter" aria-label="Filtrar por equipa">
        <label>
          Ver uma equipa
          <select :value="selectedTeam?.number ?? ''" @change="selectTeamFromControl">
            <option value="">Todas as equipas</option>
            <option v-for="team in allTeams" :key="team.id" :value="team.number">
              Equipa {{ team.number }} · {{ team.name }}
            </option>
          </select>
        </label>
        <button v-if="selectedTeam" class="button button--quiet button--small" type="button" @click="clearTeamFilter">
          Ver todas
        </button>
      </section>

      <section v-if="selectedTeam" class="public-team-summary" aria-labelledby="selected-team-title">
        <div>
          <p class="eyebrow">Equipa {{ selectedTeam.number }}</p>
          <h2 id="selected-team-title">{{ selectedTeam.name }}</h2>
          <p>{{ selectedTeam.group.name }}</p>
        </div>
        <div class="public-team-summary__stats">
          <article>
            <span>Posição</span>
            <strong>{{ selectedStanding ? `${selectedStanding.position}.º` : '—' }}</strong>
          </article>
          <article>
            <span>Pontos</span>
            <strong>{{ selectedStanding?.points ?? '—' }}</strong>
          </article>
          <article>
            <span>Jogos concluídos</span>
            <strong>{{ completedTeamMatches }} / {{ selectedTeamMatches.length }}</strong>
          </article>
        </div>
        <div v-if="nextTeamMatch" class="public-team-summary__next">
          <span>Próximo jogo</span>
          <strong>Jogo {{ nextTeamMatch.gameNumber }} · Jornada {{ nextTeamMatch.roundNumber }}</strong>
          <p>
            {{ nextTeamMatch.teamA.id === selectedTeam.id ? nextTeamMatch.teamB.name : nextTeamMatch.teamA.name }}
            · {{ matchGroupLabel(nextTeamMatch) }}
          </p>
        </div>
        <div v-else class="public-team-summary__next">
          <span>Próximo jogo</span>
          <strong>Fase de liga concluída</strong>
        </div>
      </section>

      <section class="public-section" aria-labelledby="public-results-title">
        <div class="public-section__heading">
          <p class="eyebrow">Fase de liga</p>
          <h2 id="public-results-title">{{ selectedTeam ? `Jogos de ${selectedTeam.name}` : 'Resultados' }}</h2>
        </div>
        <div v-if="groupedMatches.length" class="public-rounds">
          <section v-for="group in groupedMatches" :key="group.roundNumber" class="public-round">
            <h3>Jornada {{ group.roundNumber }}</h3>
            <article v-for="match in group.matches" :key="match.id" class="public-match">
              <p class="public-match__group">{{ matchGroupLabel(match) }}</p>
              <button class="public-match__team public-team-link" type="button" @click="showTeam(match.teamA)">
                {{ match.teamA.name }}
              </button>
              <strong class="public-match__score">{{ match.scoreA ?? '-' }} <i>-</i> {{ match.scoreB ?? '-' }}</strong>
              <button class="public-match__team public-match__team--away public-team-link" type="button" @click="showTeam(match.teamB)">
                {{ match.teamB.name }}
              </button>
            </article>
          </section>
        </div>
        <p v-else class="public-empty">Ainda não existe calendário para a fase de liga.</p>
      </section>

      <section class="public-section" aria-labelledby="public-classification-title">
        <div class="public-section__heading">
          <p class="eyebrow">Fase de liga</p>
          <h2 id="public-classification-title">{{ selectedTeam ? `Classificação · ${selectedTeam.group.name}` : 'Classificação' }}</h2>
        </div>
        <div v-if="groupStandings.length" class="public-group-standings">
          <section v-for="standing in groupStandings" :key="standing.group.id" class="public-group-standing">
            <h3>{{ standing.group.name }}</h3>
            <ClassificationTable
              :rows="standing.rows"
              :mode="state.tournament.classificationMode"
              :highlight-team-id="selectedTeam?.id ?? null"
              selectable
              @select-team="showTeam"
            />
          </section>
        </div>
        <p v-else class="public-empty">A classificação por grupo será apresentada quando existirem equipas.</p>
      </section>

      <section v-if="state.finalStage?.roundCount" class="public-section public-section--final" aria-labelledby="public-final-title">
        <div class="public-section__heading">
          <p class="eyebrow">Eliminação directa</p>
          <h2 id="public-final-title">Fase Final</h2>
        </div>
        <FinalBracket :stage="state.finalStage" />
      </section>

      <section v-if="state.finalStage?.champion" class="public-champion" aria-labelledby="champion-title">
        <p id="champion-title">Campeão</p>
        <strong>{{ state.finalStage.champion.name }}</strong>
      </section>
    </div>
  </main>
</template>
