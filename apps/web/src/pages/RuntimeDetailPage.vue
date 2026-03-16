<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'
import { use } from 'echarts/core'
import { LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel, term } from '@/lib/display'

use([CanvasRenderer, GridComponent, TooltipComponent, LegendComponent, LineChart])

const { t, locale } = useI18n()
const logStream = ref<'out' | 'err'>('out')

const commandQuery = useQuery({
  queryKey: ['runtime-detail-command'],
  queryFn: api.getCommandCenter,
  refetchInterval: 10_000,
})
const runtimeLogsQuery = useQuery({
  queryKey: ['runtime-detail-logs', logStream],
  queryFn: () => api.getRuntimeLogs(logStream.value, 200),
  refetchInterval: 15_000,
})

const command = computed(() => commandQuery.data.value)
const runtimeStatus = computed(() => command.value?.runtime_status)
const runtimeSyncHistory = computed(() => command.value?.runtime_sync_history ?? [])
const llmStatus = computed(() => command.value?.llm_status)
const macroStatus = computed(() => command.value?.market_snapshot.macro_status)
const runtimeLogs = computed(() => runtimeLogsQuery.data.value)

const sortedRuntimeHistory = computed(() =>
  [...runtimeSyncHistory.value].sort((left, right) => left.created_at.localeCompare(right.created_at)),
)
const runtimeDurationOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  legend: { bottom: 0 },
  grid: { left: 48, right: 18, top: 24, bottom: 48 },
  xAxis: {
    type: 'category',
    data: sortedRuntimeHistory.value.map((item) => formatDateTime(item.created_at)),
  },
  yAxis: { type: 'value' },
  series: [
    {
      name: t('runtimeDetail.totalDuration'),
      type: 'line',
      smooth: true,
      data: sortedRuntimeHistory.value.map((item) => item.total_duration_ms ?? null),
      lineStyle: { color: '#0f766e', width: 2.5 },
      itemStyle: { color: '#0f766e' },
    },
    {
      name: pipelineStageLabel('strategy_agent'),
      type: 'line',
      smooth: true,
      data: sortedRuntimeHistory.value.map((item) => item.stage_durations_ms.strategy_agent ?? null),
      lineStyle: { color: '#ea580c', width: 2 },
      itemStyle: { color: '#ea580c' },
    },
    {
      name: pipelineStageLabel('materialize_decisions'),
      type: 'line',
      smooth: true,
      data: sortedRuntimeHistory.value.map((item) => item.stage_durations_ms.materialize_decisions ?? null),
      lineStyle: { color: '#7c3aed', width: 2 },
      itemStyle: { color: '#7c3aed' },
    },
    {
      name: pipelineStageLabel('paper_execution'),
      type: 'line',
      smooth: true,
      data: sortedRuntimeHistory.value.map((item) => item.stage_durations_ms.paper_execution ?? null),
      lineStyle: { color: '#2563eb', width: 2 },
      itemStyle: { color: '#2563eb' },
    },
  ],
}))
const averageRecentSyncDuration = computed(() => {
  const values = sortedRuntimeHistory.value
    .map((item) => item.total_duration_ms)
    .filter((item): item is number => typeof item === 'number' && item > 0)
  if (!values.length) return null
  return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length)
})
const latestRuntimeHistoryItem = computed(() => sortedRuntimeHistory.value[sortedRuntimeHistory.value.length - 1] ?? null)
const recentRuntimeFailures = computed(() => sortedRuntimeHistory.value.filter((item) => item.state === 'failed').length)

function setLogStream(stream: 'out' | 'err'): void {
  logStream.value = stream
}
function runtimeStateLabel(value?: string): string {
  return displayLabel(t, 'runtimeState', value)
}
function pipelineStageLabel(value?: string): string {
  return displayLabel(t, 'pipelineStage', value)
}
function llmStatusLabel(value?: string): string {
  return displayLabel(t, 'llmStatus', value)
}
function runtimeVariant(state?: string, degraded?: boolean, stalled?: boolean): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (state === 'running') return 'info'
  if (state === 'failed') return 'danger'
  if (state === 'stalled' || stalled) return 'warning'
  if (state === 'degraded' || degraded) return 'warning'
  if (state === 'idle') return 'success'
  return 'neutral'
}
function formatDateTime(value?: string | null): string {
  if (!value) return '--'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return value
  return new Intl.DateTimeFormat(locale.value, {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  }).format(parsed)
}
function formatUptime(value?: number | null): string {
  if (value === null || value === undefined) return '--'
  const total = Math.max(0, Math.floor(value))
  const days = Math.floor(total / 86400)
  const hours = Math.floor((total % 86400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  if (days > 0) return `${days}d ${hours}h ${minutes}m`
  if (hours > 0) return `${hours}h ${minutes}m`
  return `${minutes}m`
}
function formatDurationMs(value?: number): string {
  if (value === undefined || value === null) return '--'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(1)} s`
}
</script>

<template>
  <div class="space-y-4">
    <Card>
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <RouterLink to="/command" class="text-sm text-slate-500 underline-offset-2 hover:underline">
            {{ term(t('runtimeDetail.backToCommand')) }}
          </RouterLink>
          <h2 class="mt-2 text-xl font-semibold text-slate-900">{{ term(t('runtimeDetail.title')) }}</h2>
          <p class="mt-2 text-sm text-slate-600">{{ t('runtimeDetail.subtitle') }}</p>
        </div>
        <Badge :variant="runtimeVariant(runtimeStatus?.current_state, runtimeStatus?.degraded, runtimeStatus?.stalled)">
          {{ runtimeStateLabel(runtimeStatus?.current_state) }}
        </Badge>
      </div>
    </Card>

    <div class="grid gap-4 lg:grid-cols-4">
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.runtimeStatus') }}</p>
        <p class="mt-2 text-2xl font-semibold text-slate-900">{{ runtimeStateLabel(runtimeStatus?.current_state) }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.currentStage') }}</p>
        <p class="mt-2 text-lg font-semibold text-slate-900">{{ pipelineStageLabel(runtimeStatus?.current_stage) }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.processUptime') }}</p>
        <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatUptime(runtimeStatus?.process_uptime_seconds) }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.consecutiveFailures') }}</p>
        <p class="mt-2 text-2xl font-semibold text-slate-900">{{ runtimeStatus?.consecutive_failures ?? 0 }}</p>
      </Card>
    </div>

    <div class="grid gap-4 lg:grid-cols-3">
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('runtimeDetail.averageRecentSyncDuration') }}</p>
        <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatDurationMs(averageRecentSyncDuration ?? undefined) }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('runtimeDetail.recentSyncFailures') }}</p>
        <p class="mt-2 text-2xl font-semibold text-slate-900">{{ recentRuntimeFailures }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('runtimeDetail.latestSyncTrigger') }}</p>
        <p class="mt-2 text-lg font-semibold text-slate-900">{{ latestRuntimeHistoryItem?.trigger ?? '--' }}</p>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1fr,0.9fr]">
      <Card class="space-y-4">
        <div>
          <h3 class="text-sm font-semibold">{{ term(t('runtimeDetail.pipelineDetail')) }}</h3>
          <p class="mt-1 text-sm text-slate-600">{{ runtimeStatus?.status_message ?? t('common.noData') }}</p>
        </div>
        <div class="grid gap-2 text-sm sm:grid-cols-2">
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.serviceStartedAt') }}</span>
            <span class="font-semibold text-slate-900">{{ formatDateTime(runtimeStatus?.process_started_at) }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.stageStartedAt') }}</span>
            <span class="font-semibold text-slate-900">{{ formatDateTime(runtimeStatus?.stage_started_at) }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.lastRunAt') }}</span>
            <span class="font-semibold text-slate-900">{{ formatDateTime(runtimeStatus?.last_run_at) }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.lastSuccessAt') }}</span>
            <span class="font-semibold text-slate-900">{{ formatDateTime(runtimeStatus?.last_success_at) }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.expectedNextRunAt') }}</span>
            <span class="font-semibold text-slate-900">{{ formatDateTime(runtimeStatus?.expected_next_run_at) }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.llmProvider') }}</span>
            <span class="font-semibold text-slate-900">{{ llmStatus?.provider ?? '--' }} / {{ llmStatusLabel(llmStatus?.status) }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('runtimeDetail.startupMode') }}</span>
            <span class="font-semibold text-slate-900">{{ runtimeStatus?.startup_mode ?? '--' }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('runtimeDetail.localLogsAvailable') }}</span>
            <span class="font-semibold text-slate-900">{{ runtimeStatus?.local_logs_available ? t('common.yes') : t('common.no') }}</span>
          </div>
        </div>
        <div v-if="runtimeStatus?.stage_durations_ms && Object.keys(runtimeStatus.stage_durations_ms).length">
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('runtimeDetail.stageDurations') }}</p>
          <div class="mt-2 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="(value, key) in runtimeStatus.stage_durations_ms"
              :key="String(key)"
              class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
            >
              <p class="text-slate-500">{{ pipelineStageLabel(String(key)) }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ formatDurationMs(Number(value)) }}</p>
            </div>
          </div>
        </div>
      </Card>

      <Card class="space-y-4">
        <div>
          <h3 class="text-sm font-semibold">{{ term(t('runtimeDetail.dependencies')) }}</h3>
          <p class="mt-1 text-sm text-slate-600">{{ t('runtimeDetail.dependenciesBody') }}</p>
        </div>
        <div class="grid gap-2 text-sm">
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.llmProvider') }}</span>
            <span class="font-semibold text-slate-900">{{ llmStatus?.provider ?? '--' }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.runtimeStatus') }}</span>
            <span class="font-semibold text-slate-900">{{ llmStatusLabel(llmStatus?.status) }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.macroProvider') }}</span>
            <span class="font-semibold text-slate-900">{{ macroStatus?.active_provider ?? macroStatus?.provider ?? '--' }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <span class="text-slate-500">{{ t('command.runtimeHealthy') }}</span>
            <span class="font-semibold text-slate-900">{{ macroStatus?.status ?? '--' }}</span>
          </div>
        </div>
      </Card>
    </div>

    <Card class="space-y-4">
      <div>
        <h3 class="text-sm font-semibold">{{ t('runtimeDetail.recentSyncTrend') }}</h3>
        <p class="mt-1 text-sm text-slate-600">{{ t('runtimeDetail.recentSyncTrendBody') }}</p>
      </div>
      <div v-if="sortedRuntimeHistory.length" class="space-y-4">
        <VChart class="h-[280px] w-full" :option="runtimeDurationOption" autoresize />
        <div class="grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
          <div
            v-for="item in [...sortedRuntimeHistory].reverse().slice(0, 4)"
            :key="item.created_at"
            class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2"
          >
            <div class="flex items-center justify-between gap-2">
              <p class="text-slate-500">{{ formatDateTime(item.created_at) }}</p>
              <Badge :variant="runtimeVariant(item.state, item.degraded, false)">{{ runtimeStateLabel(item.state) }}</Badge>
            </div>
            <p class="mt-2 font-semibold text-slate-900">{{ formatDurationMs(item.total_duration_ms ?? undefined) }}</p>
            <p class="mt-1 text-slate-500">{{ item.trigger ?? '--' }}</p>
          </div>
        </div>
      </div>
      <p v-else class="text-sm text-slate-500">{{ t('runtimeDetail.recentSyncTrendEmpty') }}</p>
    </Card>

    <Card class="space-y-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 class="text-sm font-semibold">{{ t('command.runtimeLogs') }}</h3>
          <p class="mt-1 text-sm text-slate-600">
            {{ runtimeLogs?.updated_at ? t('command.logUpdatedAt', { time: formatDateTime(runtimeLogs.updated_at) }) : t('command.logWaiting') }}
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors"
            :class="logStream === 'out' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300 bg-white text-slate-900 hover:bg-slate-50'"
            @click="setLogStream('out')"
          >
            {{ t('command.logStreamOut') }}
          </button>
          <button
            type="button"
            class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors"
            :class="logStream === 'err' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300 bg-white text-slate-900 hover:bg-slate-50'"
            @click="setLogStream('err')"
          >
            {{ t('command.logStreamErr') }}
          </button>
        </div>
      </div>
      <div class="rounded-xl border border-slate-200/80 bg-slate-950 p-0.5">
        <div class="max-h-[28rem] overflow-auto rounded-[11px] bg-slate-950 px-4 py-3 font-mono text-xs leading-6 text-slate-100">
          <template v-if="runtimeLogsQuery.isLoading.value">
            <p class="text-slate-400">{{ t('command.logLoading') }}</p>
          </template>
          <template v-else-if="runtimeLogsQuery.isError.value">
            <p class="text-rose-300">
              {{ runtimeLogsQuery.error.value instanceof Error ? runtimeLogsQuery.error.value.message : t('command.logLoadError') }}
            </p>
          </template>
          <template v-else-if="!runtimeLogs?.exists">
            <p class="text-slate-400">{{ t('command.logMissing') }}</p>
          </template>
          <template v-else-if="!(runtimeLogs?.lines?.length)">
            <p class="text-slate-400">{{ t('command.logEmpty') }}</p>
          </template>
          <template v-else>
            <div v-for="(line, index) in runtimeLogs.lines" :key="`${logStream}-${index}-${line}`" class="whitespace-pre-wrap break-all">
              {{ line }}
            </div>
          </template>
        </div>
      </div>
    </Card>
  </div>
</template>
