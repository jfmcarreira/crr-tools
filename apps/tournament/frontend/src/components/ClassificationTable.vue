<script setup lang="ts">
import { signedDifference } from '../lib/format';
import type { ClassificationMode, ClassificationRow, TeamSummary } from '../types';

const props = defineProps<{
  rows: ClassificationRow[];
  compact?: boolean;
  mode?: ClassificationMode;
  selectable?: boolean;
  highlightTeamId?: number | null;
}>();
const emit = defineEmits<{ selectTeam: [team: TeamSummary] }>();
</script>

<template>
  <div class="table-scroll">
    <table
      class="classification-table"
      :class="{
        'classification-table--compact': compact,
        'classification-table--points-only': mode === 'total-points',
      }"
    >
      <thead>
        <tr>
          <th>Pos.</th>
          <th>Equipa</th>
          <template v-if="mode !== 'total-points'">
            <th title="Jogos">J</th>
            <th title="Vitórias">V</th>
            <th title="Empates">E</th>
            <th title="Derrotas">D</th>
            <th title="Golos marcados">GM</th>
            <th title="Golos sofridos">GS</th>
            <th title="Diferença de golos">DG</th>
            <th title="Pontos">Pts</th>
          </template>
          <th v-else>Pontos</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.team.number"
          :class="{ 'classification-table__row--highlight': props.highlightTeamId === row.team.id }"
        >
          <td class="classification-table__position">{{ row.position }}</td>
          <td class="classification-table__team">
            <button
              v-if="selectable"
              class="classification-table__team-button"
              type="button"
              @click="emit('selectTeam', row.team)"
            >
              {{ row.team.name }}
            </button>
            <template v-else>{{ row.team.name }}</template>
          </td>
          <template v-if="mode !== 'total-points'">
            <td>{{ row.played }}</td>
            <td>{{ row.wins }}</td>
            <td>{{ row.draws }}</td>
            <td>{{ row.losses }}</td>
            <td>{{ row.goalsFor }}</td>
            <td>{{ row.goalsAgainst }}</td>
            <td>{{ signedDifference(row.goalDifference) }}</td>
            <td class="classification-table__points">{{ row.points }}</td>
          </template>
          <td v-else class="classification-table__points">{{ row.points }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
