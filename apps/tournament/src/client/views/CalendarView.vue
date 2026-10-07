<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import AppModal from '../components/AppModal.vue';
import { groupMatches, matchGroupLabel } from '../lib/format';
import { api, messageFor } from '../lib/api';
import type {
  CalendarGenerationPreview,
  CalendarLegs,
  CalendarPreviewMatch,
  CalendarResponse,
  LeagueMatch,
  TournamentSettings,
} from '../types';

const settings = ref<TournamentSettings>({
  name: '',
  classificationMode: 'standard',
  finalRoundCount: null,
  thirdPlaceEnabled: false,
});
const matches = ref<LeagueMatch[]>([]);
const legs = ref<CalendarLegs>(1);
const preview = ref<CalendarGenerationPreview | null>(null);
const loading = ref(true);
const loadError = ref('');
const settingsError = ref('');
const settingsSaved = ref(false);
const savingSettings = ref(false);
const generationError = ref('');
const generating = ref(false);
const savingCalendar = ref(false);
const showReplaceConfirmation = ref(false);
const showClearConfirmation = ref(false);
const clearing = ref(false);

const groupedExistingMatches = computed(() => groupMatches(matches.value));
const completedMatchCount = computed(() => matches.value.filter(
  (match) => match.scoreA !== null && match.scoreB !== null,
).length);
const previewGroups = computed(() => {
  const groups = new Map<number, CalendarPreviewMatch[]>();
  for (const match of preview.value?.matches ?? []) {
    const round = groups.get(match.roundNumber) ?? [];
    round.push(match);
    groups.set(match.roundNumber, round);
  }
  return [...groups.entries()].map(([roundNumber, roundMatches]) => ({
    roundNumber,
    matches: roundMatches,
  }));
});

async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    const [settingsResponse, calendarResponse] = await Promise.all([
      api<TournamentSettings>('/api/admin/settings'),
      api<CalendarResponse>('/api/admin/calendar'),
    ]);
    settings.value = settingsResponse;
    matches.value = calendarResponse.matches;
  } catch (caught) {
    loadError.value = messageFor(caught);
  } finally {
    loading.value = false;
  }
}

async function saveSettings() {
  settingsError.value = '';
  settingsSaved.value = false;
  if (!settings.value.name.trim()) {
    settingsError.value = 'O nome do torneio é obrigatório.';
    return;
  }

  savingSettings.value = true;
  try {
    await api('/api/admin/settings', {
      method: 'PUT',
      body: JSON.stringify({
        name: settings.value.name.trim(),
        classificationMode: settings.value.classificationMode,
      }),
    });
    settingsSaved.value = true;
  } catch (caught) {
    settingsError.value = messageFor(caught);
  } finally {
    savingSettings.value = false;
  }
}

async function generatePreview() {
  generating.value = true;
  generationError.value = '';
  try {
    preview.value = await api<CalendarGenerationPreview>('/api/admin/calendar/generate-preview', {
      method: 'POST',
      body: JSON.stringify({ legs: legs.value }),
    });
  } catch (caught) {
    preview.value = null;
    generationError.value = messageFor(caught);
  } finally {
    generating.value = false;
  }
}

function cancelPreview() {
  preview.value = null;
  generationError.value = '';
}

function requestSave() {
  if (!preview.value) return;
  generationError.value = '';
  if (completedMatchCount.value) {
    showReplaceConfirmation.value = true;
    return;
  }
  saveCalendar();
}

async function saveCalendar(confirmed = false) {
  if (!preview.value) return;
  savingCalendar.value = true;
  try {
    await api('/api/admin/calendar/generate', {
      method: 'POST',
      body: JSON.stringify({
        generation: preview.value.generation,
        ...(confirmed ? { confirmReplace: true } : {}),
      }),
    });
    showReplaceConfirmation.value = false;
    cancelPreview();
    await load();
  } catch (caught) {
    generationError.value = messageFor(caught);
    showReplaceConfirmation.value = false;
  } finally {
    savingCalendar.value = false;
  }
}

async function clearCalendar(confirmed = false) {
  clearing.value = true;
  generationError.value = '';
  try {
    await api('/api/admin/calendar', {
      method: 'DELETE',
      body: JSON.stringify({ ...(confirmed ? { confirm: true } : {}) }),
    });
    showClearConfirmation.value = false;
    await load();
  } catch (caught) {
    generationError.value = messageFor(caught);
    showClearConfirmation.value = false;
  } finally {
    clearing.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="admin-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">Organização da fase de liga</p>
        <h1>Calendário</h1>
        <p class="muted">Sorteie um calendário de todos contra todos para as equipas de cada grupo.</p>
      </div>
    </div>

    <p v-if="loadError" class="notice notice--error" role="alert">{{ loadError }} <button class="text-button" @click="load">Tentar novamente</button></p>
    <p v-else-if="loading" class="loading-state">A carregar calendário...</p>
    <template v-else>
      <section class="panel settings-panel" aria-labelledby="settings-title">
        <div>
          <h2 id="settings-title">Definições do torneio</h2>
          <p class="muted">O nome é apresentado na área pública do torneio.</p>
        </div>
        <form class="inline-form" @submit.prevent="saveSettings">
          <label class="inline-form__grow">
            Nome do torneio
            <input v-model="settings.name" maxlength="150" />
          </label>
          <label class="inline-form__grow">
            Modo da classificação
            <select v-model="settings.classificationMode">
              <option value="standard">Vitórias, empates e derrotas</option>
              <option value="total-points">Total de pontos marcados</option>
            </select>
          </label>
          <button class="button" type="submit" :disabled="savingSettings">{{ savingSettings ? 'A guardar...' : 'Guardar definições' }}</button>
        </form>
        <p class="muted">No modo de total de pontos, a classificação mostra apenas os pontos marcados. Empates são decididos pelo confronto direto.</p>
        <p v-if="settingsError" class="form-error" role="alert">{{ settingsError }}</p>
        <p v-else-if="settingsSaved" class="form-success">Definições guardadas.</p>
      </section>

      <section class="panel generation-panel" aria-labelledby="generation-title">
        <div>
          <h2 id="generation-title">Sortear calendário</h2>
          <p class="muted">Cada equipa joga contra todas as outras equipas do seu grupo, no máximo uma vez por jornada.</p>
        </div>
        <div class="inline-form">
          <label class="inline-form__grow">
            Formato da fase de liga
            <select v-model="legs" @change="cancelPreview">
              <option :value="1">Uma volta</option>
              <option :value="2">Duas voltas (casa e fora)</option>
            </select>
          </label>
          <button class="button" type="button" :disabled="generating || savingCalendar" @click="generatePreview">
            {{ generating ? 'A sortear...' : preview ? 'Sortear novamente' : 'Sortear calendário' }}
          </button>
        </div>
        <p v-if="generationError" class="form-error" role="alert">{{ generationError }}</p>

        <div v-if="preview" class="calendar-preview">
          <div class="preview-summary">
            <strong>{{ preview.matchCount }} {{ preview.matchCount === 1 ? 'jogo sorteado' : 'jogos sorteados' }}</strong>
            <span>{{ preview.roundCount }} {{ preview.roundCount === 1 ? 'jornada' : 'jornadas' }}</span>
          </div>
          <div class="calendar-groups calendar-groups--preview">
            <section v-for="group in previewGroups" :key="group.roundNumber" class="round-card">
              <h3>Jornada {{ group.roundNumber }}</h3>
              <ol>
                <li v-for="match in group.matches" :key="match.gameNumber" class="calendar-match">
                  <span class="game-number">Jogo {{ match.gameNumber }} <span class="match-group-label">{{ match.group.name }}</span></span>
                  <span class="calendar-match__team" :title="match.teamA.name">{{ match.teamA.name }}</span>
                  <b class="calendar-match__versus">vs</b>
                  <span class="calendar-match__team" :title="match.teamB.name">{{ match.teamB.name }}</span>
                </li>
              </ol>
            </section>
          </div>
          <div class="card-actions">
            <button class="button button--quiet" type="button" :disabled="savingCalendar" @click="cancelPreview">Cancelar</button>
            <button class="button" type="button" :disabled="savingCalendar" @click="requestSave">
              {{ savingCalendar ? 'A guardar...' : 'Guardar calendário' }}
            </button>
          </div>
        </div>
      </section>

      <section class="calendar-current" aria-labelledby="current-calendar-title">
        <div class="section-heading">
          <div>
            <p class="eyebrow">Calendário actual</p>
            <h2 id="current-calendar-title">Jogos agendados</h2>
          </div>
          <button v-if="matches.length" class="button button--danger" type="button" @click="showClearConfirmation = true">Limpar calendário</button>
        </div>
        <div v-if="groupedExistingMatches.length" class="calendar-groups">
          <section v-for="group in groupedExistingMatches" :key="group.roundNumber" class="round-card">
            <h3>Jornada {{ group.roundNumber }}</h3>
            <ol>
              <li v-for="match in group.matches" :key="match.id" class="calendar-match">
                <span class="game-number">Jogo {{ match.gameNumber }} <span class="match-group-label">{{ matchGroupLabel(match) }}</span></span>
                <span class="calendar-match__team" :title="match.teamA.name">{{ match.teamA.name }}</span>
                <b class="calendar-match__versus">vs</b>
                <span class="calendar-match__team" :title="match.teamB.name">{{ match.teamB.name }}</span>
              </li>
            </ol>
          </section>
        </div>
        <div v-else class="empty-state">
          <h3>Sem calendário</h3>
          <p>Sorteie os jogos da fase de liga quando as equipas e os grupos estiverem prontos.</p>
        </div>
      </section>
    </template>

    <AppModal
      :open="showReplaceConfirmation"
      title="Substituir calendário"
      confirm-label="Substituir calendário"
      destructive
      :busy="savingCalendar"
      @close="showReplaceConfirmation = false"
      @confirm="() => saveCalendar(true)"
    >
      <p><strong>Já existem resultados registados.</strong></p>
      <p>Ao substituir o calendário serão eliminados todos os resultados da fase de liga.</p>
    </AppModal>
    <AppModal
      :open="showClearConfirmation"
      title="Limpar calendário"
      confirm-label="Limpar calendário"
      destructive
      :busy="clearing"
      @close="showClearConfirmation = false"
      @confirm="() => clearCalendar(true)"
    >
      <p>Esta operação elimina todos os jogos e resultados da fase de liga.</p>
      <p class="muted">As equipas, jogadores e a configuração da fase final não são alterados.</p>
    </AppModal>
  </section>
</template>
