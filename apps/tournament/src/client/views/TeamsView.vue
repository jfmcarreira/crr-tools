<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import AppModal from '../components/AppModal.vue';
import { api, messageFor } from '../lib/api';
import type { Group, Player, Team } from '../types';

type TeamDetailsForm = { name: string; groupId: string };
type TeamForm = TeamDetailsForm & { number: string };
type NewTeamForm = TeamDetailsForm;
type GroupForm = { name: string };

const teams = ref<Team[]>([]);
const groups = ref<Group[]>([]);
const loading = ref(true);
const loadError = ref('');
const creatingGroup = ref(false);
const newGroup = ref<GroupForm>({ name: '' });
const newGroupError = ref('');
const editingGroupId = ref<number | null>(null);
const editGroup = ref<GroupForm>({ name: '' });
const groupErrors = ref<Record<number, string>>({});
const pendingGroupDelete = ref<Group | null>(null);
const deletingGroup = ref(false);
const randomizing = ref(false);
const randomizeError = ref('');
const showRandomizeConfirmation = ref(false);
const creating = ref(false);
const newTeam = ref<NewTeamForm>({ name: '', groupId: '' });
const newTeamErrors = ref<Record<string, string>>({});
const editingTeamId = ref<number | null>(null);
const editTeam = ref<TeamForm>({ number: '', name: '', groupId: '' });
const teamErrors = ref<Record<number, string>>({});
const addingPlayerFor = ref<number | null>(null);
const newPlayerName = ref('');
const editingPlayer = ref<{ id: number; teamId: number; name: string } | null>(null);
const playerErrors = ref<Record<number, string>>({});
const pendingTeamDelete = ref<Team | null>(null);
const deleting = ref(false);
const pendingPlayerDelete = ref<{ teamId: number; player: Player } | null>(null);
const deletingPlayer = ref(false);

const sortedTeams = computed(() => [...teams.value].sort((first, second) => first.number - second.number));
const sortedGroups = computed(() => [...groups.value].sort((first, second) => first.sortOrder - second.sortOrder || first.name.localeCompare(second.name, 'pt-PT')));

function teamDetailsErrors(form: TeamDetailsForm): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!form.name.trim()) errors.name = 'O nome da equipa é obrigatório.';
  if (!groups.value.some((group) => group.id === Number(form.groupId))) errors.groupId = 'Selecione o grupo da equipa.';
  return errors;
}

function teamFormErrors(form: TeamForm): Record<string, string> {
  const errors = teamDetailsErrors(form);
  if (!/^\d+$/.test(form.number) || Number(form.number) < 1) {
    errors.number = 'Introduza um número inteiro superior a zero.';
  }
  return errors;
}

function resetNewTeam(): void {
  newTeam.value = { name: '', groupId: String(sortedGroups.value[0]?.id ?? '') };
}

function validGroupName(name: string): string {
  return name.trim() ? '' : 'O nome do grupo é obrigatório.';
}

async function loadTeams() {
  loading.value = true;
  loadError.value = '';
  try {
    const [teamsResponse, groupsResponse] = await Promise.all([
      api<Team[]>('/api/admin/teams'),
      api<Group[]>('/api/admin/groups'),
    ]);
    teams.value = teamsResponse;
    groups.value = groupsResponse;
    if (!sortedGroups.value.some((group) => group.id === Number(newTeam.value.groupId))) {
      newTeam.value.groupId = String(sortedGroups.value[0]?.id ?? '');
    }
  } catch (caught) {
    loadError.value = messageFor(caught);
  } finally {
    loading.value = false;
  }
}

async function createGroup() {
  newGroupError.value = validGroupName(newGroup.value.name);
  if (newGroupError.value) return;

  creatingGroup.value = true;
  try {
    await api('/api/admin/groups', {
      method: 'POST',
      body: JSON.stringify({ name: newGroup.value.name.trim() }),
    });
    newGroup.value = { name: '' };
    await loadTeams();
  } catch (caught) {
    newGroupError.value = messageFor(caught);
  } finally {
    creatingGroup.value = false;
  }
}

function startGroupEdit(group: Group) {
  editingGroupId.value = group.id;
  editGroup.value = { name: group.name };
  groupErrors.value[group.id] = '';
}

async function saveGroup(group: Group) {
  const error = validGroupName(editGroup.value.name);
  if (error) {
    groupErrors.value[group.id] = error;
    return;
  }

  try {
    await api(`/api/admin/groups/${group.id}`, {
      method: 'PUT',
      body: JSON.stringify({ name: editGroup.value.name.trim() }),
    });
    editingGroupId.value = null;
    await loadTeams();
  } catch (caught) {
    groupErrors.value[group.id] = messageFor(caught);
  }
}

async function deleteGroup() {
  const group = pendingGroupDelete.value;
  if (!group) return;
  deletingGroup.value = true;
  groupErrors.value[group.id] = '';
  try {
    await api(`/api/admin/groups/${group.id}`, { method: 'DELETE' });
    pendingGroupDelete.value = null;
    await loadTeams();
  } catch (caught) {
    groupErrors.value[group.id] = messageFor(caught);
    pendingGroupDelete.value = null;
  } finally {
    deletingGroup.value = false;
  }
}

async function randomizeTeams() {
  randomizing.value = true;
  randomizeError.value = '';
  try {
    await api('/api/admin/teams/randomize', {
      method: 'POST',
      body: JSON.stringify({ confirm: true }),
    });
    showRandomizeConfirmation.value = false;
    await loadTeams();
  } catch (caught) {
    randomizeError.value = messageFor(caught);
    showRandomizeConfirmation.value = false;
  } finally {
    randomizing.value = false;
  }
}

async function createTeam() {
  newTeamErrors.value = teamDetailsErrors(newTeam.value);
  if (Object.keys(newTeamErrors.value).length) return;

  creating.value = true;
  try {
    await api('/api/admin/teams', {
      method: 'POST',
      body: JSON.stringify({ name: newTeam.value.name.trim(), groupId: Number(newTeam.value.groupId) }),
    });
    await loadTeams();
    resetNewTeam();
  } catch (caught) {
    newTeamErrors.value = { form: messageFor(caught) };
  } finally {
    creating.value = false;
  }
}

function startTeamEdit(team: Team) {
  editingTeamId.value = team.id;
  editTeam.value = { number: String(team.number), name: team.name, groupId: String(team.group.id) };
  teamErrors.value[team.id] = '';
}

async function saveTeam(team: Team) {
  const errors = teamFormErrors(editTeam.value);
  if (Object.keys(errors).length) {
    teamErrors.value[team.id] = Object.values(errors)[0];
    return;
  }

  try {
    await api(`/api/admin/teams/${team.id}`, {
      method: 'PUT',
      body: JSON.stringify({ number: Number(editTeam.value.number), name: editTeam.value.name.trim(), groupId: Number(editTeam.value.groupId) }),
    });
    editingTeamId.value = null;
    await loadTeams();
  } catch (caught) {
    teamErrors.value[team.id] = messageFor(caught);
  }
}

async function deleteTeam() {
  const team = pendingTeamDelete.value;
  if (!team) return;
  deleting.value = true;
  try {
    await api(`/api/admin/teams/${team.id}`, { method: 'DELETE' });
    pendingTeamDelete.value = null;
    await loadTeams();
  } catch (caught) {
    teamErrors.value[team.id] = messageFor(caught);
    pendingTeamDelete.value = null;
  } finally {
    deleting.value = false;
  }
}

function startPlayerAdd(teamId: number) {
  addingPlayerFor.value = teamId;
  newPlayerName.value = '';
  playerErrors.value[teamId] = '';
}

async function addPlayer(teamId: number) {
  if (!newPlayerName.value.trim()) {
    playerErrors.value[teamId] = 'O nome do jogador é obrigatório.';
    return;
  }

  try {
    await api(`/api/admin/teams/${teamId}/players`, {
      method: 'POST',
      body: JSON.stringify({ name: newPlayerName.value.trim() }),
    });
    addingPlayerFor.value = null;
    await loadTeams();
  } catch (caught) {
    playerErrors.value[teamId] = messageFor(caught);
  }
}

function startPlayerEdit(teamId: number, player: Player) {
  editingPlayer.value = { id: player.id, teamId, name: player.name };
  playerErrors.value[teamId] = '';
}

async function savePlayer() {
  const player = editingPlayer.value;
  if (!player) return;
  if (!player.name.trim()) {
    playerErrors.value[player.teamId] = 'O nome do jogador é obrigatório.';
    return;
  }

  try {
    await api(`/api/admin/players/${player.id}`, {
      method: 'PUT',
      body: JSON.stringify({ name: player.name.trim() }),
    });
    editingPlayer.value = null;
    await loadTeams();
  } catch (caught) {
    playerErrors.value[player.teamId] = messageFor(caught);
  }
}

async function removePlayer() {
  const pending = pendingPlayerDelete.value;
  if (!pending) return;
  deletingPlayer.value = true;
  playerErrors.value[pending.teamId] = '';
  try {
    await api(`/api/admin/players/${pending.player.id}`, { method: 'DELETE' });
    pendingPlayerDelete.value = null;
    await loadTeams();
  } catch (caught) {
    playerErrors.value[pending.teamId] = messageFor(caught);
    pendingPlayerDelete.value = null;
  } finally {
    deletingPlayer.value = false;
  }
}

onMounted(loadTeams);
</script>

<template>
  <section class="admin-page">
    <div class="page-heading">
      <div>
        <p class="eyebrow">Configuração do torneio</p>
        <h1>Equipas</h1>
        <p class="muted">Organize os grupos, crie as equipas e mantenha a lista de jogadores actualizada.</p>
      </div>
      <button v-if="sortedTeams.length > 1" class="button button--quiet" type="button" :disabled="randomizing || loading" @click="showRandomizeConfirmation = true">
        {{ randomizing ? 'A sortear...' : 'Sortear equipas' }}
      </button>
    </div>

    <p v-if="randomizeError" class="notice notice--error" role="alert">{{ randomizeError }}</p>

    <section class="panel groups-panel" aria-labelledby="groups-title">
      <div>
        <h2 id="groups-title">Grupos</h2>
        <p class="muted">Todas as equipas pertencem a um grupo. Os jogos entre grupos continuam a fazer parte do calendário, mas não contam para as classificações.</p>
      </div>
      <form class="inline-form" @submit.prevent="createGroup">
        <label class="inline-form__grow">
          Nome do grupo
          <input v-model="newGroup.name" maxlength="100" placeholder="Ex.: A" />
        </label>
        <button class="button" type="submit" :disabled="creatingGroup || loading">{{ creatingGroup ? 'A adicionar...' : 'Adicionar grupo' }}</button>
      </form>
      <p v-if="newGroupError" class="form-error" role="alert">{{ newGroupError }}</p>
      <div v-if="sortedGroups.length" class="group-list">
        <article v-for="group in sortedGroups" :key="group.id" class="group-card">
          <form v-if="editingGroupId === group.id" class="group-edit-form" @submit.prevent="saveGroup(group)">
            <label>
              Nome do grupo
              <input v-model="editGroup.name" maxlength="100" />
            </label>
            <p v-if="groupErrors[group.id]" class="form-error" role="alert">{{ groupErrors[group.id] }}</p>
            <div class="card-actions">
              <button class="button button--small" type="submit">Guardar</button>
              <button class="button button--quiet button--small" type="button" @click="editingGroupId = null">Cancelar</button>
            </div>
          </form>
          <template v-else>
            <strong>{{ group.name }}</strong>
            <div class="icon-actions">
              <button class="text-button" type="button" @click="startGroupEdit(group)">Editar</button>
              <button class="text-button text-button--danger" type="button" @click="pendingGroupDelete = group">Eliminar</button>
            </div>
            <p v-if="groupErrors[group.id]" class="form-error" role="alert">{{ groupErrors[group.id] }}</p>
          </template>
        </article>
      </div>
      <p v-else-if="!loading" class="empty-inline">Ainda não existem grupos. Adicione um grupo antes de criar equipas.</p>
    </section>

    <section class="panel team-create-panel" aria-labelledby="new-team-title">
      <div>
        <h2 id="new-team-title">Adicionar equipa</h2>
        <p class="muted">O número da equipa é atribuído automaticamente. O grupo define os seus adversários e a classificação.</p>
      </div>
      <form class="inline-form" @submit.prevent="createTeam">
        <label class="inline-form__grow">
          Nome da equipa
          <input v-model="newTeam.name" maxlength="100" />
          <span v-if="newTeamErrors.name" class="field-error">{{ newTeamErrors.name }}</span>
        </label>
        <label>
          Grupo
          <select v-model="newTeam.groupId" :disabled="!sortedGroups.length">
            <option value="" disabled>Selecionar</option>
            <option v-for="group in sortedGroups" :key="group.id" :value="String(group.id)">{{ group.name }}</option>
          </select>
          <span v-if="newTeamErrors.groupId" class="field-error">{{ newTeamErrors.groupId }}</span>
        </label>
        <button class="button" type="submit" :disabled="creating || loading || !sortedGroups.length">{{ creating ? 'A adicionar...' : 'Adicionar equipa' }}</button>
      </form>
      <p v-if="newTeamErrors.form" class="form-error" role="alert">{{ newTeamErrors.form }}</p>
    </section>

    <p v-if="loadError" class="notice notice--error" role="alert">{{ loadError }} <button class="text-button" @click="loadTeams">Tentar novamente</button></p>
    <p v-else-if="loading" class="loading-state">A carregar equipas...</p>
    <div v-else-if="sortedTeams.length" class="team-grid">
      <article v-for="team in sortedTeams" :key="team.id" class="team-card">
        <template v-if="editingTeamId === team.id">
          <form class="team-edit-form" @submit.prevent="saveTeam(team)">
            <label>
              Número
              <input v-model="editTeam.number" inputmode="numeric" />
            </label>
            <label>
              Nome da equipa
              <input v-model="editTeam.name" maxlength="100" />
            </label>
            <label>
              Grupo
              <select v-model="editTeam.groupId">
                <option value="" disabled>Selecionar</option>
                <option v-for="group in sortedGroups" :key="group.id" :value="String(group.id)">{{ group.name }}</option>
              </select>
            </label>
            <p v-if="teamErrors[team.id]" class="form-error">{{ teamErrors[team.id] }}</p>
            <div class="card-actions">
              <button class="button" type="submit">Guardar</button>
              <button class="button button--quiet" type="button" @click="editingTeamId = null">Cancelar</button>
            </div>
          </form>
        </template>
        <template v-else>
          <div class="team-card__heading">
            <p class="team-number">Equipa {{ team.number }}</p>
            <div class="icon-actions">
              <button class="text-button" type="button" @click="startTeamEdit(team)">Editar</button>
              <button class="text-button text-button--danger" type="button" @click="pendingTeamDelete = team">Eliminar</button>
            </div>
          </div>
          <h2>{{ team.name }}</h2>
          <p class="team-group">{{ team.group.name }}</p>
          <p v-if="teamErrors[team.id]" class="form-error">{{ teamErrors[team.id] }}</p>
          <div class="team-card__players">
            <h3>Jogadores <span>{{ team.players.length }}</span></h3>
            <ul v-if="team.players.length" class="player-list">
              <li v-for="player in team.players" :key="player.id">
                <template v-if="editingPlayer?.id === player.id">
                  <form class="player-edit" @submit.prevent="savePlayer">
                    <input v-model="editingPlayer.name" maxlength="100" aria-label="Nome do jogador" />
                    <button class="text-button" type="submit">Guardar</button>
                    <button class="text-button" type="button" @click="editingPlayer = null">Cancelar</button>
                  </form>
                </template>
                <template v-else>
                  <span>{{ player.name }}</span>
                  <span class="player-actions">
                    <button class="text-button" type="button" @click="startPlayerEdit(team.id, player)">Editar</button>
                    <button class="text-button text-button--danger" type="button" @click="pendingPlayerDelete = { teamId: team.id, player }">Eliminar</button>
                  </span>
                </template>
              </li>
            </ul>
            <p v-else class="empty-inline">Sem jogadores registados.</p>
            <form v-if="addingPlayerFor === team.id" class="player-add" @submit.prevent="addPlayer(team.id)">
              <input v-model="newPlayerName" maxlength="100" placeholder="Nome do jogador" aria-label="Nome do jogador" />
              <button class="button button--small" type="submit">Adicionar</button>
              <button class="button button--quiet button--small" type="button" @click="addingPlayerFor = null">Cancelar</button>
            </form>
            <button v-else class="button button--quiet button--small" type="button" @click="startPlayerAdd(team.id)">Adicionar jogador</button>
            <p v-if="playerErrors[team.id]" class="form-error">{{ playerErrors[team.id] }}</p>
          </div>
        </template>
      </article>
    </div>
    <section v-else-if="!loading" class="empty-state">
      <h2>Ainda não existem equipas</h2>
      <p>Adicione a primeira equipa para começar a preparar o torneio.</p>
    </section>

    <AppModal
      :open="Boolean(pendingGroupDelete)"
      title="Eliminar grupo"
      confirm-label="Eliminar grupo"
      destructive
      :busy="deletingGroup"
      @close="pendingGroupDelete = null"
      @confirm="deleteGroup"
    >
      <p>Tem a certeza de que pretende eliminar o grupo <strong>{{ pendingGroupDelete?.name }}</strong>?</p>
      <p class="muted">Esta operação não pode ser anulada. A eliminação será recusada se o grupo ainda tiver equipas ou jogos associados.</p>
    </AppModal>
    <AppModal
      :open="showRandomizeConfirmation"
      title="Sortear equipas"
      confirm-label="Sortear equipas"
      destructive
      :busy="randomizing"
      @close="showRandomizeConfirmation = false"
      @confirm="randomizeTeams"
    >
      <p>Os números actuais serão distribuídos aleatoriamente pelas equipas e as equipas serão repartidas pelos grupos de forma equilibrada.</p>
      <p class="muted">Se existir calendário, todos os jogos e resultados da fase de liga serão eliminados. A fase final não é alterada.</p>
    </AppModal>
    <AppModal
      :open="Boolean(pendingTeamDelete)"
      title="Eliminar equipa"
      confirm-label="Eliminar equipa"
      destructive
      :busy="deleting"
      @close="pendingTeamDelete = null"
      @confirm="deleteTeam"
    >
      <p>Tem a certeza de que pretende eliminar a equipa <strong>{{ pendingTeamDelete?.name }}</strong>?</p>
      <p class="muted">Esta operação não pode ser anulada. Se a equipa estiver a ser usada no calendário ou na fase final, a eliminação será recusada.</p>
    </AppModal>
    <AppModal
      :open="Boolean(pendingPlayerDelete)"
      title="Eliminar jogador"
      confirm-label="Eliminar jogador"
      destructive
      :busy="deletingPlayer"
      @close="pendingPlayerDelete = null"
      @confirm="removePlayer"
    >
      <p>Tem a certeza de que pretende eliminar o jogador <strong>{{ pendingPlayerDelete?.player.name }}</strong>?</p>
    </AppModal>
  </section>
</template>
