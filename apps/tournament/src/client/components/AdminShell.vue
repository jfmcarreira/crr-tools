<script setup lang="ts">
import { ref } from 'vue';
import { useRouter } from 'vue-router';
import { api } from '../lib/api';
import AppLogo from './AppLogo.vue';

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
    <header class="admin-header">
      <RouterLink class="admin-brand" to="/admin/dashboard" aria-label="Administração do torneio">
        <AppLogo />
      </RouterLink>
      <nav class="admin-nav" aria-label="Navegação de administração">
        <RouterLink to="/admin/dashboard">Dashboard</RouterLink>
        <RouterLink to="/admin/teams">Equipas</RouterLink>
        <RouterLink to="/admin/calendar">Calendário</RouterLink>
        <RouterLink to="/admin/results">Resultados</RouterLink>
        <RouterLink to="/admin/final-stage">Fase Final</RouterLink>
        <RouterLink to="/admin/match-cards">Cartões</RouterLink>
        <RouterLink to="/admin/display">Ecrã</RouterLink>
      </nav>
      <button class="logout-button" type="button" :disabled="loggingOut" @click="logout">
        {{ loggingOut ? 'A terminar...' : 'Terminar sessão' }}
      </button>
    </header>
    <main class="admin-main"><slot /></main>
  </div>
</template>
