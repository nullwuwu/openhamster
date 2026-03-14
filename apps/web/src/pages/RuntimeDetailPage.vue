<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel } from '@/lib/display'

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
const llmStatus = computed(() => command.value?.llm_status)
const macroStatus = computed(() => command.value?.market_snapshot.macro_status)
const runtimeLogs = computed(() => runtimeLogsQuery.data.value)

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
            {{ t('runtimeDetail.backToCommand') }}
          </RouterLink>
          <h2 class="mt-2 text-xl font-semibold text-slate-900">{{ t('runtimeDetail.title') }}</h2>
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

    <div class="grid gap-4 xl:grid-cols-[1fr,0.9fr]">
      <Card class="space-y-4">
        <div>
          <h3 class="text-sm font-semibold">{{ t('runtimeDetail.pipelineDetail') }}</h3>
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
          <h3 class="text-sm font-semibold">{{ t('runtimeDetail.dependencies') }}</h3>
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
