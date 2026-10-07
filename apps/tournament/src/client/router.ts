import { createRouter, createWebHistory } from 'vue-router';
import { api } from './lib/api';
import LoginView from './views/LoginView.vue';
import TeamsView from './views/TeamsView.vue';
import CalendarView from './views/CalendarView.vue';
import ResultsView from './views/ResultsView.vue';
import FinalStageView from './views/FinalStageView.vue';
import PublicResultsView from './views/PublicResultsView.vue';
import DisplayView from './views/DisplayView.vue';
import DisplaySettingsView from './views/DisplaySettingsView.vue';
import MatchCardsView from './views/MatchCardsView.vue';
import DashboardView from './views/DashboardView.vue';

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/', redirect: '/results' },
    { path: '/results', component: PublicResultsView },
    { path: '/display', component: DisplayView },
    { path: '/admin', redirect: '/admin/dashboard' },
    { path: '/admin/login', component: LoginView, meta: { login: true } },
    { path: '/admin/dashboard', component: DashboardView, meta: { admin: true } },
    { path: '/admin/teams', component: TeamsView, meta: { admin: true } },
    { path: '/admin/calendar', component: CalendarView, meta: { admin: true } },
    { path: '/admin/results', component: ResultsView, meta: { admin: true } },
    { path: '/admin/final-stage', component: FinalStageView, meta: { admin: true } },
    { path: '/admin/match-cards', component: MatchCardsView, meta: { admin: true } },
    { path: '/admin/display', component: DisplaySettingsView, meta: { admin: true } },
    { path: '/:pathMatch(.*)*', redirect: '/results' },
  ],
});

router.beforeEach(async (to) => {
  if (!to.meta.admin && !to.meta.login) return true;

  try {
    const session = await api<{ authenticated?: boolean; active?: boolean }>('/api/auth/session');
    const authenticated = session.authenticated ?? session.active ?? false;
    if (to.meta.admin && !authenticated) return { path: '/admin/login', query: { next: to.fullPath } };
    if (to.meta.login && authenticated) return '/admin/dashboard';
  } catch {
    if (to.meta.admin) return { path: '/admin/login', query: { next: to.fullPath } };
  }

  return true;
});

export default router;
