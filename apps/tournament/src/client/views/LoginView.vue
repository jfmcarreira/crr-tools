<script setup lang="ts">
import { ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import AppLogo from '../components/AppLogo.vue';
import { api, messageFor } from '../lib/api';

const router = useRouter();
const route = useRoute();
const password = ref('');
const error = ref('');
const pending = ref(false);

async function login() {
  error.value = '';
  if (!password.value) {
    error.value = 'Introduza a palavra-passe.';
    return;
  }

  pending.value = true;
  try {
    await api('/api/auth/login', { method: 'POST', body: JSON.stringify({ password: password.value }) });
    const next = typeof route.query.next === 'string' && route.query.next.startsWith('/admin/')
      ? route.query.next
      : '/admin/dashboard';
    await router.replace(next);
  } catch (caught) {
    error.value = messageFor(caught);
  } finally {
    pending.value = false;
  }
}
</script>

<template>
  <main class="login-page">
    <section class="login-card" aria-labelledby="login-title">
      <AppLogo large />
      <div>
        <p class="eyebrow">Área reservada</p>
        <h1 id="login-title">Administração</h1>
      </div>
      <form class="stack-form" @submit.prevent="login">
        <label>
          Palavra-passe
          <input v-model="password" type="password" autocomplete="current-password" autofocus />
        </label>
        <p v-if="error" class="form-error" role="alert">{{ error }}</p>
        <button class="button button--wide" type="submit" :disabled="pending">
          {{ pending ? 'A entrar...' : 'Entrar' }}
        </button>
      </form>
      <RouterLink class="login-public-link" to="/results">Ver resultados públicos</RouterLink>
    </section>
  </main>
</template>
