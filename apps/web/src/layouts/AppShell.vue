<script setup lang="ts">
import type { Component } from 'vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { BarChart3, FlaskConical, LayoutDashboard, LineChart, Menu, Target } from 'lucide-vue-next'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import { getCurrentLocale, setAppLocale, type SupportedLocale } from '@/i18n'
import { useUiStore } from '@/stores/ui'

type NavKey = 'overview' | 'strategies' | 'backtests' | 'experiments' | 'trading'

const navDefs: Array<{ path: string; key: NavKey; icon: Component }> = [
  { path: '/overview', key: 'overview', icon: LayoutDashboard },
  { path: '/strategies', key: 'strategies', icon: Target },
  { path: '/backtests', key: 'backtests', icon: LineChart },
  { path: '/experiments', key: 'experiments', icon: FlaskConical },
  { path: '/trading', key: 'trading', icon: BarChart3 },
]

const { t } = useI18n()
const ui = useUiStore()
const route = useRoute()
const locale = ref<SupportedLocale>(getCurrentLocale())

const navItems = computed(() =>
  navDefs.map((item) => ({
    ...item,
    label: t(`shell.nav.${item.key}`),
  })),
)

const routeTitle = computed(() => {
  const matched = navDefs.find((item) => route.path.startsWith(item.path))
  return matched ? t(`shell.nav.${matched.key}`) : t('shell.nav.overview')
})

function switchLocale(next: SupportedLocale): void {
  if (locale.value === next) return
  locale.value = next
  setAppLocale(next)
}
</script>

<template>
  <div class="min-h-screen">
    <div class="mx-auto flex max-w-[1500px] gap-4 px-4 py-4 sm:px-6 lg:px-8">
      <aside
        class="panel-glass sticky top-4 hidden h-[calc(100vh-2rem)] w-64 rounded-2xl p-4 lg:flex lg:flex-col"
        :class="{ 'lg:w-20': !ui.sideOpen }"
      >
        <div class="mb-5 flex items-center justify-between">
          <h1 class="text-lg font-semibold tracking-tight" :class="{ hidden: !ui.sideOpen }">
            {{ t('shell.appTitle') }}
          </h1>
          <Button variant="ghost" size="sm" class="h-8 w-8 p-0" @click="ui.toggleSidebar">
            <Menu class="h-4 w-4" />
          </Button>
        </div>
        <nav class="space-y-1">
          <RouterLink
            v-for="item in navItems"
            :key="item.path"
            :to="item.path"
            class="flex items-center gap-3 rounded-lg px-3 py-2 text-sm text-slate-700 transition-colors hover:bg-white/70"
            :class="{
              'bg-white/85 text-slate-900': route.path.startsWith(item.path),
              'justify-center': !ui.sideOpen,
            }"
          >
            <component :is="item.icon" class="h-4 w-4" />
            <span v-if="ui.sideOpen">{{ item.label }}</span>
          </RouterLink>
        </nav>
      </aside>

      <main class="flex-1 min-w-0">
        <header class="panel-glass mb-4 flex items-center justify-between rounded-2xl px-4 py-3">
          <div>
            <h2 class="text-sm uppercase tracking-[0.18em] text-slate-500">{{ t('shell.consoleTitle') }}</h2>
            <p class="text-base font-semibold text-slate-900">{{ routeTitle }}</p>
          </div>
          <div class="flex items-center gap-2">
            <div class="flex items-center gap-1 rounded-lg border border-white/70 bg-white/60 px-2 py-1">
              <span class="hidden text-[10px] uppercase tracking-widest text-slate-500 sm:inline">
                {{ t('shell.language') }}
              </span>
              <Button
                size="sm"
                class="h-7 px-2"
                :variant="locale === 'zh-CN' ? 'secondary' : 'ghost'"
                @click="switchLocale('zh-CN')"
              >
                ZH
              </Button>
              <Button
                size="sm"
                class="h-7 px-2"
                :variant="locale === 'en-US' ? 'secondary' : 'ghost'"
                @click="switchLocale('en-US')"
              >
                EN
              </Button>
            </div>
            <RouterLink to="/backtests">
              <Button size="sm">{{ t('shell.runBacktest') }}</Button>
            </RouterLink>
          </div>
        </header>

        <RouterView />
      </main>
    </div>
  </div>
</template>
