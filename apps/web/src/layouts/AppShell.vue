<script setup lang="ts">
import type { Component } from 'vue'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Activity, Command, FileSearch, LibraryBig, Menu, Radar, ShieldCheck } from 'lucide-vue-next'
import { RouterLink, RouterView, useRoute } from 'vue-router'

import Button from '@/components/ui/Button.vue'
import { getCurrentLocale, setAppLocale, type SupportedLocale } from '@/i18n'
import { term } from '@/lib/display'
import { useUiStore } from '@/stores/ui'

type NavKey = 'command' | 'runtime' | 'candidates' | 'research' | 'paper' | 'audit'

const navDefs: Array<{ path: string; key: NavKey; icon: Component }> = [
  { path: '/command', key: 'command', icon: Command },
  { path: '/runtime', key: 'runtime', icon: Activity },
  { path: '/candidates', key: 'candidates', icon: Radar },
  { path: '/research', key: 'research', icon: LibraryBig },
  { path: '/paper', key: 'paper', icon: ShieldCheck },
  { path: '/audit', key: 'audit', icon: FileSearch },
]

const { t } = useI18n()
const ui = useUiStore()
const route = useRoute()
const locale = ref<SupportedLocale>(getCurrentLocale())

const navItems = computed(() =>
  navDefs.map((item) => ({
    ...item,
    label: term(t(`shell.nav.${item.key}`)),
  })),
)

const routeTitle = computed(() => {
  const matched = navDefs.find((item) => route.path.startsWith(item.path))
  return term(matched ? t(`shell.nav.${matched.key}`) : t('shell.nav.command'))
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
          <div :class="{ hidden: !ui.sideOpen }">
            <h1 class="text-lg font-semibold tracking-tight">{{ t('shell.appTitle') }}</h1>
            <p class="mt-1 text-xs uppercase tracking-[0.2em] text-slate-500">{{ t('shell.appTagline') }}</p>
          </div>
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

      <main class="min-w-0 flex-1">
        <header class="panel-glass mb-4 flex items-center justify-between rounded-2xl px-4 py-3">
          <div>
            <h2 class="text-sm uppercase tracking-[0.18em] text-slate-500">{{ term(t('shell.consoleTitle')) }}</h2>
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
            <RouterLink to="/research">
              <Button size="sm">{{ t('shell.reviewResearch') }}</Button>
            </RouterLink>
          </div>
        </header>

        <RouterView />
      </main>
    </div>
  </div>
</template>
