<script setup lang="ts">
import { computed, watch, ref } from 'vue';
import type { ScoreDraft } from '../lib/score';
import type { BracketMatch, FinalStage } from '../types';

type MatchPayload = { roundIndex: number; matchIndex: number };
type ResultPayload = MatchPayload & ScoreDraft;

const props = withDefaults(defineProps<{
  stage: FinalStage;
  editable?: boolean;
  errors?: Record<string, string>;
  success?: Record<string, string>;
  savingKey?: string | null;
}>(), {
  editable: false,
  errors: () => ({}),
  success: () => ({}),
  savingKey: null,
});

const emit = defineEmits<{
  'save-result': [payload: ResultPayload];
  'clear-result': [payload: MatchPayload];
}>();

const drafts = ref<Record<string, ScoreDraft>>({});

const thirdPlaceMatch = computed(() => props.stage.roundCount !== null
  && props.stage.roundCount >= 2
  && props.stage.thirdPlaceEnabled
  ? props.stage.thirdPlaceMatch
  : null);

function key(roundIndex: number, matchIndex: number): string {
  return `${roundIndex}-${matchIndex}`;
}

function hasBothTeams(match: BracketMatch): boolean {
  return Boolean(match.teamA.team && match.teamB.team && !match.teamA.pending && !match.teamB.pending);
}

function isBye(match: BracketMatch): boolean {
  return match.isBye;
}

function resetDrafts(stage: FinalStage) {
  const nextDrafts: Record<string, ScoreDraft> = {};
  const setDraft = (roundIndex: number, match: BracketMatch) => {
    nextDrafts[key(roundIndex, match.matchIndex)] = {
      scoreA: match.scoreA === null ? '' : String(match.scoreA),
      scoreB: match.scoreB === null ? '' : String(match.scoreB),
    };
  };

  stage.rounds.forEach((round) => round.matches.forEach((match) => setDraft(round.roundIndex, match)));
  if (stage.roundCount !== null && stage.roundCount >= 2 && stage.thirdPlaceEnabled && stage.thirdPlaceMatch) {
    setDraft(stage.roundCount, stage.thirdPlaceMatch);
  }
  drafts.value = nextDrafts;
}

function save(roundIndex: number, match: BracketMatch) {
  const draft = drafts.value[key(roundIndex, match.matchIndex)];
  emit('save-result', {
    roundIndex,
    matchIndex: match.matchIndex,
    scoreA: draft?.scoreA ?? '',
    scoreB: draft?.scoreB ?? '',
  });
}

function thirdPlaceKey(match: BracketMatch): string {
  return props.stage.roundCount === null ? '' : key(props.stage.roundCount, match.matchIndex);
}

function saveThirdPlace(match: BracketMatch) {
  if (props.stage.roundCount !== null) save(props.stage.roundCount, match);
}

function clearThirdPlace(match: BracketMatch) {
  if (props.stage.roundCount !== null) {
    emit('clear-result', { roundIndex: props.stage.roundCount, matchIndex: match.matchIndex });
  }
}

watch(() => props.stage, resetDrafts, { immediate: true, deep: true });
</script>

<template>
  <div v-if="stage.rounds.length" class="bracket-scroll" tabindex="0" aria-label="Quadro da fase final. Deslize horizontalmente para ver todas as rondas.">
    <div class="bracket-grid">
      <section v-for="round in stage.rounds" :key="round.roundIndex" class="bracket-column">
        <h3>{{ round.name }}</h3>
        <div class="bracket-match-list" :style="{ '--matches-in-round': round.matches.length }">
          <article v-for="match in round.matches" :key="match.matchIndex" class="bracket-match">
            <p class="bracket-match__number">Jogo {{ match.matchIndex }}</p>
            <div class="bracket-team" :class="{ 'bracket-team--winner': match.winner?.id === match.teamA.team?.id }">
              <span>{{ match.teamA.team?.name ?? (match.teamA.pending ? 'Por apurar' : '--- Livre ---') }}</span>
              <input
                v-if="editable && hasBothTeams(match)"
                v-model="drafts[key(round.roundIndex, match.matchIndex)].scoreA"
                inputmode="numeric"
                :aria-label="`Resultado de ${match.teamA.team?.name}`"
              />
              <strong v-else>{{ match.scoreA ?? '-' }}</strong>
            </div>
            <div class="bracket-team" :class="{ 'bracket-team--winner': match.winner?.id === match.teamB.team?.id }">
              <span>{{ match.teamB.team?.name ?? (match.teamB.pending ? 'Por apurar' : '--- Livre ---') }}</span>
              <input
                v-if="editable && hasBothTeams(match)"
                v-model="drafts[key(round.roundIndex, match.matchIndex)].scoreB"
                inputmode="numeric"
                :aria-label="`Resultado de ${match.teamB.team?.name}`"
              />
              <strong v-else>{{ match.scoreB ?? '-' }}</strong>
            </div>
            <p v-if="isBye(match)" class="bracket-match__bye">Avança sem jogar</p>
            <template v-if="editable && hasBothTeams(match)">
              <div class="bracket-match__actions">
                <button class="button button--small" type="button" :disabled="savingKey === key(round.roundIndex, match.matchIndex)" @click="save(round.roundIndex, match)">
                  {{ savingKey === key(round.roundIndex, match.matchIndex) ? 'A guardar...' : 'Guardar' }}
                </button>
                <button v-if="match.scoreA !== null && match.scoreB !== null" class="text-button" type="button" @click="emit('clear-result', { roundIndex: round.roundIndex, matchIndex: match.matchIndex })">Limpar</button>
              </div>
              <p v-if="errors[key(round.roundIndex, match.matchIndex)]" class="form-error">{{ errors[key(round.roundIndex, match.matchIndex)] }}</p>
              <p v-else-if="success[key(round.roundIndex, match.matchIndex)]" class="form-success">{{ success[key(round.roundIndex, match.matchIndex)] }}</p>
            </template>
          </article>
        </div>
      </section>
    </div>
  </div>
  <article v-if="thirdPlaceMatch" class="third-place-match bracket-match">
    <h3 class="third-place-match__title">Jogo do 3.º lugar</h3>
    <div class="bracket-team" :class="{ 'bracket-team--winner': thirdPlaceMatch.winner?.id === thirdPlaceMatch.teamA.team?.id }">
      <span>{{ thirdPlaceMatch.teamA.team?.name ?? (thirdPlaceMatch.teamA.pending ? 'Por apurar' : '--- Livre ---') }}</span>
      <input
        v-if="editable && hasBothTeams(thirdPlaceMatch)"
        v-model="drafts[thirdPlaceKey(thirdPlaceMatch)].scoreA"
        inputmode="numeric"
        :aria-label="`Resultado de ${thirdPlaceMatch.teamA.team?.name}`"
      />
      <strong v-else>{{ thirdPlaceMatch.scoreA ?? '-' }}</strong>
    </div>
    <div class="bracket-team" :class="{ 'bracket-team--winner': thirdPlaceMatch.winner?.id === thirdPlaceMatch.teamB.team?.id }">
      <span>{{ thirdPlaceMatch.teamB.team?.name ?? (thirdPlaceMatch.teamB.pending ? 'Por apurar' : '--- Livre ---') }}</span>
      <input
        v-if="editable && hasBothTeams(thirdPlaceMatch)"
        v-model="drafts[thirdPlaceKey(thirdPlaceMatch)].scoreB"
        inputmode="numeric"
        :aria-label="`Resultado de ${thirdPlaceMatch.teamB.team?.name}`"
      />
      <strong v-else>{{ thirdPlaceMatch.scoreB ?? '-' }}</strong>
    </div>
    <p v-if="isBye(thirdPlaceMatch)" class="bracket-match__bye">Avança sem jogar</p>
    <template v-if="editable && hasBothTeams(thirdPlaceMatch)">
      <div class="bracket-match__actions">
        <button class="button button--small" type="button" :disabled="savingKey === thirdPlaceKey(thirdPlaceMatch)" @click="saveThirdPlace(thirdPlaceMatch)">
          {{ savingKey === thirdPlaceKey(thirdPlaceMatch) ? 'A guardar...' : 'Guardar' }}
        </button>
        <button v-if="thirdPlaceMatch.scoreA !== null && thirdPlaceMatch.scoreB !== null" class="text-button" type="button" @click="clearThirdPlace(thirdPlaceMatch)">Limpar</button>
      </div>
      <p v-if="errors[thirdPlaceKey(thirdPlaceMatch)]" class="form-error">{{ errors[thirdPlaceKey(thirdPlaceMatch)] }}</p>
      <p v-else-if="success[thirdPlaceKey(thirdPlaceMatch)]" class="form-success">{{ success[thirdPlaceKey(thirdPlaceMatch)] }}</p>
    </template>
  </article>
  <p v-if="!stage.rounds.length" class="empty-inline">A fase final ainda não está configurada.</p>
</template>
