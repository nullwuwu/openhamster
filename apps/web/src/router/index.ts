import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/command' },
    { path: '/command', component: () => import('@/pages/CommandPage.vue') },
    { path: '/runtime', component: () => import('@/pages/RuntimeDetailPage.vue') },
    { path: '/candidates', component: () => import('@/pages/CandidatesPage.vue') },
    { path: '/candidates/:proposalId', component: () => import('@/pages/CandidateDetailPage.vue') },
    { path: '/research', component: () => import('@/pages/ResearchPage.vue') },
    { path: '/research/:proposalId', component: () => import('@/pages/ResearchDetailPage.vue') },
    { path: '/paper', component: () => import('@/pages/PaperPage.vue') },
    { path: '/audit', component: () => import('@/pages/AuditPage.vue') },
    { path: '/audit/:decisionId', component: () => import('@/pages/AuditDecisionDetailPage.vue') },
  ],
})
