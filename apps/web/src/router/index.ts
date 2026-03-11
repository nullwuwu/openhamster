import { createRouter, createWebHistory } from 'vue-router'

import OverviewPage from '@/pages/OverviewPage.vue'
import StrategiesPage from '@/pages/StrategiesPage.vue'
import BacktestsPage from '@/pages/BacktestsPage.vue'
import ExperimentsPage from '@/pages/ExperimentsPage.vue'
import TradingPage from '@/pages/TradingPage.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/overview' },
    { path: '/overview', component: OverviewPage },
    { path: '/strategies', component: StrategiesPage },
    { path: '/backtests', component: BacktestsPage },
    { path: '/experiments', component: ExperimentsPage },
    { path: '/trading', component: TradingPage },
  ],
})
