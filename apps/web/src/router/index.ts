import { createRouter, createWebHistory } from 'vue-router'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/command' },
    { path: '/command', component: () => import('@/pages/CommandPage.vue') },
    { path: '/candidates', component: () => import('@/pages/CandidatesPage.vue') },
    { path: '/research', component: () => import('@/pages/ResearchPage.vue') },
    { path: '/paper', component: () => import('@/pages/PaperPage.vue') },
    { path: '/audit', component: () => import('@/pages/AuditPage.vue') },
  ],
})
