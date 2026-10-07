import { onBeforeUnmount, onMounted, ref } from 'vue';
import { api, applicationPath, messageFor } from './api';
import type { PublicTournamentState } from '../types';

export function usePublicTournamentState() {
  const state = ref<PublicTournamentState | null>(null);
  const initialLoading = ref(true);
  const refreshError = ref('');
  const connection = ref<'connecting' | 'connected' | 'reconnecting'>('connecting');
  const lastUpdated = ref<Date | null>(null);
  const refreshing = ref(false);
  const refreshQueued = ref(false);
  let events: EventSource | null = null;

  async function refreshState() {
    if (refreshing.value) {
      refreshQueued.value = true;
      return;
    }

    refreshing.value = true;
    try {
      state.value = await api<PublicTournamentState>('/api/public/state');
      refreshError.value = '';
      lastUpdated.value = new Date();
    } catch (caught) {
      // Preserve the previous state so a temporary outage never blanks a display.
      refreshError.value = messageFor(caught);
    } finally {
      refreshing.value = false;
      initialLoading.value = false;
      if (refreshQueued.value) {
        refreshQueued.value = false;
        void refreshState();
      }
    }
  }

  function connectEvents() {
    events = new EventSource(applicationPath('/api/public/events'));
    const invalidate = () => { void refreshState(); };
    events.addEventListener('state-changed', invalidate);
    events.onmessage = invalidate;
    events.onopen = () => {
      connection.value = 'connected';
      void refreshState();
    };
    events.onerror = () => {
      // EventSource retries itself. Keep showing the last successful state meanwhile.
      connection.value = 'reconnecting';
    };
  }

  function refreshOnVisibility() {
    if (document.visibilityState === 'visible') void refreshState();
  }

  onMounted(() => {
    void refreshState();
    connectEvents();
    document.addEventListener('visibilitychange', refreshOnVisibility);
  });

  onBeforeUnmount(() => {
    events?.close();
    events = null;
    document.removeEventListener('visibilitychange', refreshOnVisibility);
  });

  return {
    connection,
    initialLoading,
    lastUpdated,
    refreshError,
    refreshState,
    state,
  };
}
