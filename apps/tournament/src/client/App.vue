<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import AdminShell from './components/AdminShell.vue';

const route = useRoute();
const isAdmin = computed(() => Boolean(route.meta.admin));
</script>

<template>
  <AdminShell v-if="isAdmin">
    <RouterView />
  </AdminShell>
  <RouterView v-else />
</template>
