<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { displayPanelDefinitions } from '../displayPanels';
import { api, applicationPath, messageFor } from '../lib/api';
import {
  DISPLAY_ZOOM_MAX_PERCENT,
  DISPLAY_ZOOM_MIN_PERCENT,
  isDisplayZoomPercent,
  type DisplayPanelType,
  type DisplaySettings,
} from '../types';

const settings = ref<DisplaySettings | null>(null);
const loading = ref(true);
const loadError = ref('');
const saveError = ref('');
const success = ref('');
const savingPanel = ref<DisplayPanelType | null>(null);
const savingZoom = ref(false);
const zoomDraft = ref<number | ''>(100);
const displayPath = applicationPath('/display');
const displayUrl = computed(() => `${window.location.origin}${displayPath}`);
const zoomValue = computed(() => Number(zoomDraft.value));
const zoomIsValid = computed(() => isDisplayZoomPercent(zoomValue.value));

async function load() {
  loading.value = true;
  loadError.value = '';
  try {
    settings.value = await api<DisplaySettings>('/api/admin/display');
    zoomDraft.value = settings.value.zoomPercent;
  } catch (caught) {
    loadError.value = messageFor(caught);
  } finally {
    loading.value = false;
  }
}

async function showPanel(activePanel: DisplayPanelType) {
  if (savingPanel.value || savingZoom.value || !settings.value || settings.value.activePanel === activePanel) return;
  savingPanel.value = activePanel;
  saveError.value = '';
  success.value = '';
  try {
    settings.value = await api<DisplaySettings>('/api/admin/display', {
      method: 'PUT',
      body: JSON.stringify({ activePanel, zoomPercent: settings.value.zoomPercent }),
    });
    success.value = 'O ecrã foi actualizado.';
  } catch (caught) {
    saveError.value = messageFor(caught);
  } finally {
    savingPanel.value = null;
  }
}

async function saveZoom() {
  if (!settings.value || savingPanel.value || savingZoom.value || !zoomIsValid.value || zoomValue.value === settings.value.zoomPercent) return;
  savingZoom.value = true;
  saveError.value = '';
  success.value = '';
  try {
    settings.value = await api<DisplaySettings>('/api/admin/display', {
      method: 'PUT',
      body: JSON.stringify({ activePanel: settings.value.activePanel, zoomPercent: zoomValue.value }),
    });
    zoomDraft.value = settings.value.zoomPercent;
    success.value = 'O zoom do ecrã foi actualizado.';
  } catch (caught) {
    saveError.value = messageFor(caught);
  } finally {
    savingZoom.value = false;
  }
}

onMounted(load);
</script>

<template>
  <section class="admin-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">Apresentação em directo</p>
        <h1>Ecrã</h1>
        <p class="muted">Escolha o painel apresentado nos ecrãs ligados ao torneio.</p>
      </div>
      <a class="button button--quiet" :href="displayPath" target="_blank" rel="noopener">Abrir ecrã</a>
    </div>

    <section class="panel display-link-panel">
      <div>
        <h2>Endereço do ecrã</h2>
        <p class="muted">Abra este endereço no televisor ou ecrã externo. As alterações aparecem automaticamente.</p>
      </div>
      <a :href="displayUrl" target="_blank" rel="noopener">{{ displayUrl }}</a>
    </section>

    <p v-if="loadError" class="notice notice--error" role="alert">{{ loadError }} <button class="text-button" @click="load">Tentar novamente</button></p>
    <p v-else-if="loading" class="loading-state">A carregar definições do ecrã...</p>
    <section v-else-if="settings" class="panel display-control-panel">
      <section class="display-setting-section" aria-labelledby="display-zoom-title">
        <div class="section-heading">
          <div>
            <h2 id="display-zoom-title">Zoom do ecrã</h2>
            <p class="muted">Aumente o conteúdo sem criar barras de deslocamento no ecrã.</p>
          </div>
        </div>
        <form class="inline-form" @submit.prevent="saveZoom">
          <label class="inline-form__grow">
            Zoom (%)
            <input
              v-model.number="zoomDraft"
              type="number"
              inputmode="numeric"
              :min="DISPLAY_ZOOM_MIN_PERCENT"
              :max="DISPLAY_ZOOM_MAX_PERCENT"
              step="1"
              required
              aria-describedby="display-zoom-help display-zoom-error"
              :disabled="savingZoom || Boolean(savingPanel)"
            />
            <span id="display-zoom-help" class="muted">Entre {{ DISPLAY_ZOOM_MIN_PERCENT }}% e {{ DISPLAY_ZOOM_MAX_PERCENT }}%.</span>
            <span v-if="!zoomIsValid" id="display-zoom-error" class="field-error">Introduza uma percentagem inteira dentro deste intervalo.</span>
          </label>
          <button class="button" type="submit" :disabled="savingZoom || Boolean(savingPanel) || !zoomIsValid || zoomValue === settings.zoomPercent">
            {{ savingZoom ? 'A aplicar...' : 'Aplicar zoom' }}
          </button>
        </form>
      </section>

      <section class="display-setting-section" aria-labelledby="display-panel-title">
        <div class="section-heading">
          <div>
            <h2 id="display-panel-title">Painel apresentado</h2>
            <p class="muted">A escolha é publicada imediatamente em todos os ecrãs abertos.</p>
          </div>
        </div>

        <div class="display-option-grid">
          <article
            v-for="panelOption in displayPanelDefinitions"
            :key="panelOption.type"
            class="display-option"
            :class="{ 'display-option--active': settings.activePanel === panelOption.type }"
          >
            <p v-if="settings.activePanel === panelOption.type" class="display-option__status">Em apresentação</p>
            <h3>{{ panelOption.label }}</h3>
            <p>{{ panelOption.description }}</p>
            <button
              class="button button--small"
              :class="{ 'button--quiet': settings.activePanel === panelOption.type }"
              type="button"
              :disabled="Boolean(savingPanel) || savingZoom || settings.activePanel === panelOption.type"
              @click="showPanel(panelOption.type)"
            >
              {{ savingPanel === panelOption.type ? 'A apresentar...' : settings.activePanel === panelOption.type ? 'Painel activo' : 'Mostrar no ecrã' }}
            </button>
          </article>
        </div>
      </section>

      <p v-if="saveError" class="form-error" role="alert">{{ saveError }}</p>
      <p v-else-if="success" class="form-success" role="status">{{ success }}</p>
    </section>
  </section>
</template>
