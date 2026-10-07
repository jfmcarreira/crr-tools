<script setup lang="ts">
import type { MatchCardMatch } from './matchCards';

defineProps<{
  tournamentName: string;
  match: MatchCardMatch;
}>();
</script>

<template>
  <article class="match-result-card">
    <header class="match-result-card__header">
      <span>{{ tournamentName }}</span>
      <strong>{{ match.context }}</strong>
    </header>
    <div class="match-result-card__body">
      <div class="match-result-card__teams">
        <div
          v-for="entry in [{ participant: match.teamA, side: 'A' }, { participant: match.teamB, side: 'B' }]"
          :key="entry.side"
          class="match-result-card__team"
        >
          <div class="match-result-card__team-name">
            <small>{{ entry.participant.team ? `Equipa ${entry.participant.team.number}` : entry.participant.pending ? 'Equipa por apurar' : '--- Livre ---' }}</small>
            <strong>{{ entry.participant.team?.name ?? (entry.participant.pending ? 'Por apurar' : '--- Livre ---') }}</strong>
          </div>
        </div>
      </div>
      <div class="match-result-card__scores">
        <slot name="scores" />
      </div>
    </div>
  </article>
</template>

<style>
.match-result-card { min-width: 0; min-height: 0; display: grid; grid-template-rows: auto 1fr; break-inside: avoid; border: 1.5px solid #202124; background: #fff; color: #161719; overflow: hidden; padding: .75rem .75rem .25rem; page-break-inside: avoid; }
.match-result-card__header { display: grid; gap: .35rem; border-bottom: 2px solid var(--color-primary); padding-bottom: .55rem; }
.match-result-card__header span { color: #31353a; font-size: .72rem; font-weight: 800; line-height: 1.2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.match-result-card__header strong { color: var(--color-primary-dark); font-size: .64rem; letter-spacing: .04em; text-transform: uppercase; }
.match-result-card__body { min-width: 0; min-height: 0; display: grid; grid-template-columns: minmax(0, 1fr) var(--match-card-scores-width); overflow: hidden; }
.match-result-card__teams, .match-result-card__scores { min-width: 0; min-height: 0; display: grid; grid-template-rows: repeat(2, minmax(0, 1fr)); }
.match-result-card__scores { overflow: hidden; }
.match-result-card__scores-content { grid-row: 1 / -1; min-width: 0; min-height: 0; overflow: hidden; }
.match-result-card__team, .match-result-card__score-area { min-width: 0; display: flex; align-items: center; border-top: 1px solid #d6d7d9; padding: .55rem 0; }
.match-result-card__team-name { min-width: 0; display: grid; gap: .18rem; }
.match-result-card__team-name small { color: #777c82; font-size: .58rem; font-weight: 800; letter-spacing: .04em; text-transform: uppercase; }
.match-result-card__team-name strong { font-size: .8rem; line-height: 1.08; overflow-wrap: anywhere; }
.match-result-card__score-area { justify-content: flex-end; gap: .5rem; padding-left: .5rem; }
.match-result-card__score-fields { display: grid; grid-template-columns: repeat(var(--score-count), var(--score-box-size)); gap: .16rem; }
.match-result-card__score-fields span { width: var(--score-box-size); height: var(--score-box-size); border: 1.5px solid #1a1b1d; }
.match-result-card__final-score { display: grid; justify-items: center; gap: .12rem; }
.match-result-card__final-score > span { width: 4rem; height: 2.8rem; border: 2px solid #1a1b1d; }
.match-result-card__final-score small { color: #656a70; font-size: .5rem; font-weight: 800; letter-spacing: .03em; text-transform: uppercase; }
</style>
