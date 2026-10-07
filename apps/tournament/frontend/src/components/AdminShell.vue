<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '../lib/api';
import logoUrl from '@crr-brand/assets/logo.png';

const router = useRouter();
const loggingOut = ref(false);

async function logout() {
  loggingOut.value = true;
  try {
    await api('/api/auth/logout', { method: 'POST' });
  } finally {
    loggingOut.value = false;
    await router.push('/admin/login');
  }
}
</script>

<template>
  <div class="admin-layout">
    <header class="crr-topbar admin-header">
      <div class="crr-topbar__inner">
        <RouterLink class="crr-topbar__brand admin-brand" to="/admin/dashboard" aria-label="Administração do torneio">
          <img class="crr-topbar__logo" :src="logoUrl" alt="CRR" />
          <span class="crr-topbar__name">Torneio</span>
        </RouterLink>
        <nav class="crr-topbar__nav admin-nav" aria-label="Navegação de administração">
          <RouterLink to="/admin/dashboard">Dashboard</RouterLink>
          <RouterLink to="/admin/teams">Equipas</RouterLink>
          <RouterLink to="/admin/calendar">Calendário</RouterLink>
          <RouterLink to="/admin/results">Resultados</RouterLink>
          <RouterLink to="/admin/final-stage">Fase Final</RouterLink>
          <RouterLink to="/admin/match-cards">Cartões</RouterLink>
          <RouterLink to="/admin/display">Ecrã</RouterLink>
        </nav>
        <div class="crr-topbar__account">
          <button class="crr-topbar__action logout-button" type="button" :disabled="loggingOut" @click="logout">
            {{ loggingOut ? 'A sair...' : 'Sair' }}
          </button>
        </div>
      </div>
    </header>
    <main class="admin-main"><slot /></main>
  </div>
</template>
