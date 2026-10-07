<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import AppModal from '../components/AppModal.vue';
import FinalBracket from '../components/FinalBracket.vue';
import { api, messageFor } from '../lib/api';
import { parseScoreDraft, type ScoreDraft } from '../lib/score';
import type { FinalQualificationMode, FinalSeedPreview, FinalStage, PublicTournamentState, Team } from '../types';

type MatchLocation = { roundIndex: number; matchIndex: number };

const emptyStage = (): FinalStage => ({
  roundCount: null,
  rounds: [],
  champion: null,
  thirdPlaceEnabled: false,
  thirdPlaceMatch: null,
});
const stage = ref<FinalStage>(emptyStage());
const teams = ref<Team[]>([]);
const publicState = ref<PublicTournamentState | null>(null);
const loading = ref(true);
const loadError = ref('');
const roundCountDraft = ref('');
const thirdPlaceEnabledDraft = ref(false);
const configError = ref('');
const seedError = ref('');
const configSaving = ref(false);
const clearingConfig = ref(false);
const seedsSaving = ref(false);
const showConfigConfirmation = ref(false);
const showClearConfigConfirmation = ref(false);
const showSeedsConfirmation = ref(false);
const seedDraft = ref<Record<number, number | null>>({});
const savedSeeds = ref<Record<number, number | null>>({});
const resultErrors = ref<Record<string, string>>({});
const resultSuccess = ref<Record<string, string>>({});
const savingResultKey = ref<string | null>(null);
const pendingClear = ref<MatchLocation | null>(null);
const clearingResult = ref(false);
const autoSeedMode = ref<FinalQualificationMode>('per-group');
const autoQualifiersPerGroup = ref(1);
const autoQualifierCount = ref(1);
const autoSeedPreview = ref<FinalSeedPreview | null>(null);
const autoSeedLoading = ref(false);
const autoSeedError = ref('');

const firstRound = computed(() => stage.value.rounds[0] ?? null);
const firstRoundLabel = computed(() => firstRound.value?.name ?? '');
const slotCount = computed(() => stage.value.roundCount ? 2 ** stage.value.roundCount : 0);
const standingsWithTeams = computed(() => (publicState.value?.groupStandings ?? []).filter((standing) => standing.rows.length > 0));
const maxAutoQualifiersPerGroup = computed(() => {
  if (!slotCount.value || standingsWithTeams.value.length === 0) return 0;
  const bracketLimit = Math.floor(slotCount.value / standingsWithTeams.value.length);
  const teamLimit = Math.min(...standingsWithTeams.value.map((standing) => standing.rows.length));
  return Math.min(bracketLimit, teamLimit);
});
const maxAutoQualifierCount = computed(() => Math.min(
  slotCount.value,
  standingsWithTeams.value.reduce((total, standing) => total + standing.rows.length, 0),
));
const seedPairs = computed(() => Array.from({ length: Math.ceil(slotCount.value / 2) }, (_, index) => ({
  matchIndex: index + 1,
  slotA: index * 2 + 1,
  slotB: index * 2 + 2,
})));
const canEnableThirdPlace = computed(() => Number(roundCountDraft.value) >= 2);
const hasChangedConfig = computed(() => Number(roundCountDraft.value) !== stage.value.roundCount
  || thirdPlaceEnabledDraft.value !== stage.value.thirdPlaceEnabled);
const hasResults = computed(() => stage.value.rounds.some((round) => round.matches.some((match) => match.scoreA !== null && match.scoreB !== null))
  || Boolean(stage.value.thirdPlaceMatch
    && stage.value.thirdPlaceMatch.scoreA !== null
    && stage.value.thirdPlaceMatch.scoreB !== null));
const hasChangedSeeds = computed(() => Array.from({ length: slotCount.value }, (_, index) => index + 1)
  .some((slot) => (seedDraft.value[slot] ?? null) !== (savedSeeds.value[slot] ?? null)));

watch(canEnableThirdPlace, (enabled) => {
  if (!enabled) thirdPlaceEnabledDraft.value = false;
});

watch(autoSeedMode, () => {
  autoSeedPreview.value = null;
  autoSeedError.value = '';
});

function resultKey(location: MatchLocation): string {
  return `${location.roundIndex}-${location.matchIndex}`;
}

function initialiseSeeds() {
  const seeds: Record<number, number | null> = {};
  for (let slot = 1; slot <= slotCount.value; slot += 1) seeds[slot] = null;
  for (const match of firstRound.value?.matches ?? []) {
    const slotA = (match.matchIndex - 1) * 2 + 1;
    const slotB = slotA + 1;
    seeds[slotA] = match.teamA.team?.id ?? null;
    seeds[slotB] = match.teamB.team?.id ?? null;
  }
  seedDraft.value = { ...seeds };
  savedSeeds.value = { ...seeds };
  autoSeedPreview.value = null;
  autoSeedError.value = '';
}

function initialiseConfigDraft() {
  roundCountDraft.value = stage.value.roundCount ? String(stage.value.roundCount) : '';
  thirdPlaceEnabledDraft.value = stage.value.roundCount && stage.value.roundCount >= 2
    ? stage.value.thirdPlaceEnabled
    : false;
}

async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    const [stageResponse, teamsResponse, publicStateResponse] = await Promise.all([
      api<FinalStage>('/api/admin/final-stage'),
      api<Team[]>('/api/admin/teams'),
      api<PublicTournamentState>('/api/public/state'),
    ]);
    stage.value = stageResponse;
    teams.value = teamsResponse;
    publicState.value = publicStateResponse;
    initialiseConfigDraft();
    initialiseSeeds();
    autoQualifiersPerGroup.value = Math.min(2, Math.max(1, maxAutoQualifiersPerGroup.value));
    autoQualifierCount.value = Math.min(
      maxAutoQualifierCount.value,
      Math.max(1, standingsWithTeams.value.length * autoQualifiersPerGroup.value),
    );
  } catch (caught) {
    loadError.value = messageFor(caught);
  } finally {
    loading.value = false;
  }
}

function requestConfigSave() {
  configError.value = '';
  const count = Number(roundCountDraft.value);
  if (!Number.isInteger(count) || count < 1 || count > 8) {
    configError.value = 'Escolha um número de rondas entre 1 e 8.';
    return;
  }
  if (count < 2) thirdPlaceEnabledDraft.value = false;
  if (!hasChangedConfig.value) return;
  showConfigConfirmation.value = Boolean(stage.value.roundCount);
  if (!showConfigConfirmation.value) saveConfig();
}

async function saveConfig(confirmed = false) {
  const roundCount = Number(roundCountDraft.value);
  const thirdPlaceEnabled = roundCount >= 2 && thirdPlaceEnabledDraft.value;
  configSaving.value = true;
  try {
    await api('/api/admin/final-stage/config', {
      method: 'PUT',
      body: JSON.stringify({ roundCount, thirdPlaceEnabled, ...(confirmed ? { confirmClearResults: true } : {}) }),
    });
    showConfigConfirmation.value = false;
    await load();
  } catch (caught) {
    configError.value = messageFor(caught);
    showConfigConfirmation.value = false;
  } finally {
    configSaving.value = false;
  }
}

async function clearConfig() {
  clearingConfig.value = true;
  configError.value = '';
  try {
    await api('/api/admin/final-stage/config', {
      method: 'DELETE',
      body: JSON.stringify({ confirm: true }),
    });
    showClearConfigConfirmation.value = false;
    await load();
  } catch (caught) {
    configError.value = messageFor(caught);
    showClearConfigConfirmation.value = false;
  } finally {
    clearingConfig.value = false;
  }
}

function updateSeed(slot: number, event: Event) {
  const value = (event.target as HTMLSelectElement).value;
  seedDraft.value[slot] = value ? Number(value) : null;
  seedError.value = '';
  autoSeedPreview.value = null;
}

function selectedInAnotherSlot(teamId: number, currentSlot: number): boolean {
  return Object.entries(seedDraft.value).some(([slot, selected]) => Number(slot) !== currentSlot && selected === teamId);
}

async function previewAutomaticSeeds() {
  autoSeedError.value = '';
  seedError.value = '';

  let payload: { mode: 'per-group'; qualifiersPerGroup: number } | { mode: 'overall'; qualifierCount: number };
  if (autoSeedMode.value === 'per-group') {
    const qualifiersPerGroup = Number(autoQualifiersPerGroup.value);
    if (!Number.isInteger(qualifiersPerGroup) || qualifiersPerGroup < 1 || qualifiersPerGroup > maxAutoQualifiersPerGroup.value) {
      autoSeedError.value = `Escolha entre 1 e ${maxAutoQualifiersPerGroup.value} equipas por grupo.`;
      return;
    }
    payload = { mode: 'per-group', qualifiersPerGroup };
  } else {
    const qualifierCount = Number(autoQualifierCount.value);
    if (!Number.isInteger(qualifierCount) || qualifierCount < 1 || qualifierCount > maxAutoQualifierCount.value) {
      autoSeedError.value = `Escolha entre 1 e ${maxAutoQualifierCount.value} equipas no total.`;
      return;
    }
    payload = { mode: 'overall', qualifierCount };
  }

  autoSeedLoading.value = true;
  try {
    const preview = await api<FinalSeedPreview>('/api/admin/final-stage/auto-seed-preview', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    autoSeedPreview.value = preview;
    seedDraft.value = Object.fromEntries(preview.seeds.map((seed) => [seed.slotIndex, seed.teamId]));
  } catch (caught) {
    autoSeedError.value = messageFor(caught);
  } finally {
    autoSeedLoading.value = false;
  }
}

function requestSeedSave() {
  seedError.value = '';
  if (!hasChangedSeeds.value) return;
  showSeedsConfirmation.value = hasResults.value;
  if (!showSeedsConfirmation.value) saveSeeds();
}

async function saveSeeds(confirmed = false) {
  seedsSaving.value = true;
  try {
    const seeds = Array.from({ length: slotCount.value }, (_, index) => ({
      slotIndex: index + 1,
      teamId: seedDraft.value[index + 1] ?? null,
    }));
    await api('/api/admin/final-stage/seeds', {
      method: 'PUT',
      body: JSON.stringify({ seeds, ...(confirmed ? { confirmClearResults: true } : {}) }),
    });
    showSeedsConfirmation.value = false;
    await load();
  } catch (caught) {
    seedError.value = messageFor(caught);
    showSeedsConfirmation.value = false;
  } finally {
    seedsSaving.value = false;
  }
}

async function saveResult(payload: MatchLocation & ScoreDraft) {
  const location = { roundIndex: payload.roundIndex, matchIndex: payload.matchIndex };
  const key = resultKey(location);
  const score = parseScoreDraft(payload);
  if (!score) {
    resultErrors.value[key] = 'Introduza dois resultados inteiros iguais ou superiores a zero.';
    return;
  }
  if (score.scoreA === score.scoreB) {
    resultErrors.value[key] = 'Os jogos da fase final não podem terminar empatados.';
    return;
  }

  savingResultKey.value = key;
  resultErrors.value[key] = '';
  resultSuccess.value[key] = '';
  try {
    await api(`/api/admin/final-stage/matches/${location.roundIndex}/${location.matchIndex}/result`, {
      method: 'PUT',
      body: JSON.stringify(score),
    });
    resultSuccess.value[key] = 'Resultado guardado.';
    await load();
  } catch (caught) {
    resultErrors.value[key] = messageFor(caught);
  } finally {
    savingResultKey.value = null;
  }
}

async function clearResult() {
  const location = pendingClear.value;
  if (!location) return;
  const key = resultKey(location);
  clearingResult.value = true;
  resultErrors.value[key] = '';
  try {
    await api(`/api/admin/final-stage/matches/${location.roundIndex}/${location.matchIndex}/result`, { method: 'DELETE' });
    pendingClear.value = null;
    await load();
  } catch (caught) {
    resultErrors.value[key] = messageFor(caught);
    pendingClear.value = null;
  } finally {
    clearingResult.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="admin-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">Eliminação directa</p>
        <h1>Fase Final</h1>
        <p class="muted">Configure o quadro, atribua as equipas da primeira ronda e registe os resultados.</p>
      </div>
    </div>

    <p v-if="loadError" class="notice notice--error" role="alert">{{ loadError }} <button class="text-button" @click="load">Tentar novamente</button></p>
    <p v-else-if="loading" class="loading-state">A carregar fase final...</p>
    <template v-else>
      <section class="panel final-config" aria-labelledby="final-config-title">
        <div>
          <h2 id="final-config-title">Configuração do quadro</h2>
          <p class="muted">A primeira ronda terá {{ slotCount || 'o número definido' }} lugares. Lugares vazios representam folgas.</p>
        </div>
        <form class="inline-form" @submit.prevent="requestConfigSave">
          <label>
            Número de rondas
            <select v-model="roundCountDraft">
              <option value="" disabled>Selecionar</option>
              <option v-for="round in 8" :key="round" :value="String(round)">{{ round }} {{ round === 1 ? 'ronda' : 'rondas' }}</option>
            </select>
          </label>
          <label class="final-config__checkbox">
            <input v-model="thirdPlaceEnabledDraft" type="checkbox" :disabled="!canEnableThirdPlace">
            <span>Jogo do 3.º lugar</span>
          </label>
          <button class="button" type="submit" :disabled="configSaving">{{ configSaving ? 'A guardar...' : 'Guardar configuração' }}</button>
        </form>
        <button v-if="stage.roundCount" class="button button--danger" type="button" :disabled="clearingConfig" @click="showClearConfigConfirmation = true">
          {{ clearingConfig ? 'A limpar...' : 'Limpar configuração da fase final' }}
        </button>
        <p v-if="configError" class="form-error" role="alert">{{ configError }}</p>
      </section>

      <template v-if="stage.roundCount">
        <section class="panel seed-panel" aria-labelledby="seed-title">
          <div>
            <h2 id="seed-title">Equipas da primeira ronda</h2>
            <p class="muted">Cada equipa só pode ocupar um lugar. Deixe um lugar livre para criar uma folga.</p>
          </div>
          <section class="auto-seed-box" aria-labelledby="auto-seed-title">
            <div>
              <h3 id="auto-seed-title">Apuramento automático</h3>
              <p class="muted">Use a classificação actual para preencher o quadro. Primeiro é mostrada uma pré-visualização; só fica guardada quando confirmar as atribuições abaixo.</p>
            </div>
            <form class="inline-form" @submit.prevent="previewAutomaticSeeds">
              <label class="inline-form__grow">
                Regra de apuramento
                <select v-model="autoSeedMode" :disabled="autoSeedLoading">
                  <option value="per-group">Melhores de cada grupo</option>
                  <option value="overall">Melhores no geral</option>
                </select>
              </label>
              <label v-if="autoSeedMode === 'per-group'">
                Apurados por grupo
                <input
                  v-model.number="autoQualifiersPerGroup"
                  type="number"
                  inputmode="numeric"
                  min="1"
                  :max="maxAutoQualifiersPerGroup || 1"
                  :disabled="maxAutoQualifiersPerGroup === 0 || autoSeedLoading"
                >
              </label>
              <label v-else>
                Apurados no total
                <input
                  v-model.number="autoQualifierCount"
                  type="number"
                  inputmode="numeric"
                  min="1"
                  :max="maxAutoQualifierCount || 1"
                  :disabled="maxAutoQualifierCount === 0 || autoSeedLoading"
                >
              </label>
              <button
                class="button button--quiet"
                type="submit"
                :disabled="(autoSeedMode === 'per-group' ? maxAutoQualifiersPerGroup === 0 : maxAutoQualifierCount === 0) || autoSeedLoading"
              >
                {{ autoSeedLoading ? 'A calcular...' : 'Pré-visualizar apuramento' }}
              </button>
            </form>
            <p v-if="autoSeedMode === 'overall'" class="muted">No apuramento geral são usados os critérios do modo de classificação do torneio; o número da equipa resolve empates entre grupos que continuem iguais.</p>
            <p v-if="(autoSeedMode === 'per-group' ? maxAutoQualifiersPerGroup : maxAutoQualifierCount) === 0" class="empty-inline">Não há classificação suficiente para preencher automaticamente esta fase final.</p>
            <p v-if="autoSeedError" class="form-error" role="alert">{{ autoSeedError }}</p>
            <div v-if="autoSeedPreview" class="auto-seed-preview" role="status">
              <p><strong>Pré-visualização pronta.</strong> Pode ajustar qualquer posição manualmente antes de guardar.</p>
              <div class="auto-seed-qualifiers">
                <span v-for="qualifier in autoSeedPreview.qualifiers" :key="qualifier.team.id">
                  Seed {{ qualifier.seedNumber }} · {{ qualifier.groupPosition }}.º {{ qualifier.team.group.name }} · {{ qualifier.team.name }}
                </span>
              </div>
            </div>
          </section>

          <div class="seed-grid">
            <article v-for="pair in seedPairs" :key="pair.matchIndex" class="seed-match">
              <h3>{{ firstRoundLabel }} · Jogo {{ pair.matchIndex }}</h3>
              <label>
                Equipa A
                <select :value="String(seedDraft[pair.slotA] ?? '')" @change="updateSeed(pair.slotA, $event)">
                  <option value="">--- Livre ---</option>
                  <option v-for="team in teams" :key="team.id" :value="team.id" :disabled="selectedInAnotherSlot(team.id, pair.slotA)">{{ team.name }}</option>
                </select>
              </label>
              <label>
                Equipa B
                <select :value="String(seedDraft[pair.slotB] ?? '')" @change="updateSeed(pair.slotB, $event)">
                  <option value="">--- Livre ---</option>
                  <option v-for="team in teams" :key="team.id" :value="team.id" :disabled="selectedInAnotherSlot(team.id, pair.slotB)">{{ team.name }}</option>
                </select>
              </label>
            </article>
          </div>
          <p v-if="seedError" class="form-error" role="alert">{{ seedError }}</p>
          <button class="button" type="button" :disabled="!hasChangedSeeds || seedsSaving" @click="requestSeedSave">{{ seedsSaving ? 'A guardar...' : 'Guardar atribuições' }}</button>
        </section>

        <section class="bracket-section" aria-labelledby="bracket-title">
          <div class="section-heading">
            <div>
              <p class="eyebrow">Actualização automática</p>
              <h2 id="bracket-title">Quadro da fase final</h2>
            </div>
          </div>
          <FinalBracket
            :stage="stage"
            editable
            :errors="resultErrors"
            :success="resultSuccess"
            :saving-key="savingResultKey"
            @save-result="saveResult"
            @clear-result="pendingClear = $event"
          />
          <div v-if="stage.champion" class="champion-card">
            <p>Campeão</p>
            <strong>{{ stage.champion.name }}</strong>
          </div>
        </section>
      </template>
    </template>

    <AppModal
      :open="showConfigConfirmation"
      title="Alterar configuração do quadro"
      confirm-label="Alterar quadro"
      destructive
      :busy="configSaving"
      @close="showConfigConfirmation = false; initialiseConfigDraft()"
      @confirm="() => saveConfig(true)"
    >
      <p>Alterar a configuração do quadro elimina as atribuições e todos os resultados da fase final.</p>
      <p class="muted">Esta operação não pode ser anulada.</p>
    </AppModal>
    <AppModal
      :open="showClearConfigConfirmation"
      title="Limpar configuração da fase final"
      confirm-label="Limpar configuração"
      destructive
      :busy="clearingConfig"
      @close="showClearConfigConfirmation = false"
      @confirm="clearConfig"
    >
      <p>Esta operação remove o número de rondas, as equipas atribuídas e todos os resultados da fase final.</p>
      <p class="muted">As equipas, o calendário e os resultados da fase de liga não são alterados.</p>
    </AppModal>
    <AppModal
      :open="showSeedsConfirmation"
      title="Alterar equipas da primeira ronda"
      confirm-label="Guardar e limpar resultados"
      destructive
      :busy="seedsSaving"
      @close="showSeedsConfirmation = false; initialiseSeeds()"
      @confirm="() => saveSeeds(true)"
    >
      <p>Ao alterar as equipas de partida serão eliminados todos os resultados da fase final.</p>
      <p class="muted">Os vencedores das rondas seguintes serão calculados novamente.</p>
    </AppModal>
    <AppModal
      :open="Boolean(pendingClear)"
      title="Limpar resultado da fase final"
      confirm-label="Limpar resultado"
      destructive
      :busy="clearingResult"
      @close="pendingClear = null"
      @confirm="clearResult"
    >
      <p>O resultado será removido. Resultados dependentes poderão também ser limpos para manter o quadro correcto.</p>
    </AppModal>
  </section>
</template>
