<script setup lang="ts">
import { computed } from 'vue';
import AppLogo from '../components/AppLogo.vue';
import { displayPanelDefinition } from '../displayPanels';
import { usePublicTournamentState } from '../lib/usePublicTournamentState';

const { connection, initialLoading, lastUpdated, refreshError, refreshState, state } = usePublicTournamentState();
const activePanel = computed(() => state.value ? displayPanelDefinition(state.value.display.activePanel) : null);
const displayZoomStyle = computed(() => {
  const zoom = (state.value?.display.zoomPercent ?? 100) / 100;
  return {
    width: `${100 / zoom}%`,
    height: `${100 / zoom}%`,
    transform: `scale(${zoom})`,
  };
});
const displayUpdatedAt = computed(() => lastUpdated.value
  ? new Intl.DateTimeFormat('pt-PT', { hour: '2-digit', minute: '2-digit', second: '2-digit' }).format(lastUpdated.value)
  : '');
</script>

<template>
  <main class="display-page">
    <header class="display-header">
      <AppLogo />
      <div class="display-header__title">
        <p class="eyebrow">Em directo</p>
        <p>{{ state?.tournament.name || 'Torneio' }}</p>
      </div>
      <div class="display-connection" :class="{ 'display-connection--waiting': connection !== 'connected' }" aria-live="polite">
        <span aria-hidden="true"></span>
        {{ connection === 'connected' ? 'Ligado' : 'A restabelecer ligação' }}
      </div>
    </header>

    <section v-if="initialLoading && !state" class="display-message">A preparar o ecrã...</section>
    <section v-else-if="!state" class="display-message display-message--error">
      <h1>Ecrã temporariamente indisponível</h1>
      <p>{{ refreshError || 'Não foi possível carregar o estado do torneio.' }}</p>
      <button class="button" type="button" @click="refreshState">Tentar novamente</button>
    </section>
    <div v-else class="display-content">
      <p v-if="refreshError" class="display-offline-notice" role="status">A mostrar a última actualização.</p>
      <p class="visually-hidden" aria-live="polite">Painel apresentado: {{ activePanel?.label }}</p>
      <div class="display-zoom" :style="displayZoomStyle">
        <component :is="activePanel?.component" :state="state" />
      </div>
      <p v-if="displayUpdatedAt" class="display-updated-at">Actualizado às {{ displayUpdatedAt }}</p>
    </div>
  </main>
</template>
