<script setup lang="ts">
import logoUrl from '@crr-brand/assets/logo.png';

withDefaults(defineProps<{ large?: boolean; light?: boolean }>(), {
  large: false,
  light: false,
});
</script>

<template>
  <div class="app-logo" :class="{ 'app-logo--large': large, 'app-logo--light': light }">
    <img :src="logoUrl" alt="Logótipo do torneio" />
    <span v-if="!large" class="app-logo__text">Torneio</span>
  </div>
</template>
