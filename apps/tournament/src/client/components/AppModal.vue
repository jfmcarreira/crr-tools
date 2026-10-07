<script setup lang="ts">
withDefaults(defineProps<{
  open: boolean;
  title: string;
  confirmLabel?: string;
  busy?: boolean;
  destructive?: boolean;
}>(), {
  confirmLabel: 'Confirmar',
  busy: false,
  destructive: false,
});

const emit = defineEmits<{ confirm: []; close: [] }>();
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="modal-backdrop" @click.self="emit('close')">
      <section class="modal" role="dialog" aria-modal="true" :aria-label="title">
        <p class="eyebrow">Confirmação necessária</p>
        <h2>{{ title }}</h2>
        <div class="modal__body"><slot /></div>
        <div class="modal__actions">
          <button class="button button--quiet" type="button" :disabled="busy" @click="emit('close')">Cancelar</button>
          <button
            class="button"
            :class="{ 'button--danger': destructive }"
            type="button"
            :disabled="busy"
            @click="emit('confirm')"
          >
            {{ busy ? 'A guardar...' : confirmLabel }}
          </button>
        </div>
      </section>
    </div>
  </Teleport>
</template>
