<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import VChart from 'vue-echarts'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel, humanizeLabel } from '@/lib/display'
import type { LLMProvider } from '@/types/api'

use([CanvasRenderer, GridComponent, TooltipComponent, LineChart])

const { t, locale } = useI18n()
const queryClient = useQueryClient()

const commandQuery = useQuery({
  queryKey: ['command-center'],
  queryFn: api.getCommandCenter,
  refetchInterval: 10_000,
})
const candidatesQuery = useQuery({
  queryKey: ['command-candidates'],
  queryFn: api.getCandidates,
  refetchInterval: 10_000,
})
const acceptanceReportQuery = useQuery({
  queryKey: ['acceptance-report', 30],
  queryFn: () => api.getAcceptanceReport(30),
  refetchInterval: 15_000,
})
const strategiesQuery = useQuery({
  queryKey: ['strategy-snapshots'],
  queryFn: api.getStrategies,
  refetchInterval: 60_000,
})

const command = computed(() => commandQuery.data.value)
const candidates = computed(() => candidatesQuery.data.value ?? [])
const strategyCatalog = computed(() => strategiesQuery.data.value ?? [])
const acceptanceReport = computed(() => acceptanceReportQuery.data.value)
const navRows = computed(() => command.value?.active_strategy.paper_trading.nav ?? [])
const llmStatus = computed(() => command.value?.llm_status)
const runtimeStatus = computed(() => command.value?.runtime_status)
const eventLaneSources = computed(() => command.value?.market_snapshot.event_lane_sources ?? {})
const macroStatus = computed(() => command.value?.market_snapshot.macro_status)
const marketProfile = computed(() => command.value?.market_snapshot.market_profile)
const universeSelection = computed(() => command.value?.market_snapshot.universe_selection)
const selectedUniverseCandidate = computed(() =>
  universeSelection.value?.candidates?.find((candidate) => candidate.symbol === universeSelection.value?.selected_symbol) ?? null,
)
const benchmarkUniverseCandidate = computed(() => universeSelection.value?.benchmark_candidate ?? null)
const operationalAcceptance = computed(
  () => (command.value?.active_strategy.operational_acceptance as Record<string, unknown> | undefined) ?? {},
)
const activeProposal = computed(() => command.value?.active_strategy.proposal ?? null)
const latestPaperExecution = computed(() => command.value?.active_strategy.paper_trading.latest_execution ?? null)
const previousVisibleActive = ref<typeof activeProposal.value | null>(null)
const previousVisibleCandidates = ref<typeof candidates.value>([])

watch(activeProposal, (value) => {
  if (value) previousVisibleActive.value = value
}, { immediate: true })

watch(candidates, (value) => {
  if (value.length > 0) previousVisibleCandidates.value = value
}, { immediate: true })

const visibleActiveProposal = computed(() => {
  if (activeProposal.value) return activeProposal.value
  if (runtimeStatus.value?.current_state === 'running') return previousVisibleActive.value
  return null
})
const visibleCandidates = computed(() => {
  if (candidates.value.length > 0) return candidates.value
  if (runtimeStatus.value?.current_state === 'running') return previousVisibleCandidates.value
  return []
})
const latestDecision = computed(() => command.value?.latest_risk_decision ?? null)
const watchpoints = computed(() => {
  const raw = command.value?.market_snapshot.price_context?.watchpoints
  return Array.isArray(raw) ? raw.map((item) => String(item)).filter(Boolean) : []
})
const signalContext = computed(() => {
  const context = command.value?.market_snapshot.price_context ?? {}
  const keys = ['volatility', 'trend_strength']
  return keys
    .filter((key) => typeof context[key] === 'number')
    .map((key) => ({ key, value: Number(context[key]) }))
})
const scoreBreakdown = computed(() => {
  if (!latestDecision.value) return []
  return [
    { key: 'deterministic', value: latestDecision.value.deterministic_score.toFixed(1) },
    { key: 'llm', value: latestDecision.value.llm_score.toFixed(1) },
    { key: 'final', value: latestDecision.value.final_score.toFixed(1) },
  ]
})
const bottomLineReport = computed(() => Object.entries(latestDecision.value?.bottom_line_report ?? {}))
const latestDigestScores = computed(() => command.value?.latest_event_digest?.event_scores ?? {})
const candidateSummary = computed(() => {
  const summary = {
    promotionReady: 0,
    coolingDown: 0,
    challengers: 0,
    trailing: 0,
  }
  for (const item of visibleCandidates.value) {
    const phase = item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.phase
    const selectionState = item.proposal.evidence_pack?.quality_report?.pool_ranking?.selection_state
    if (phase === 'promotion_ready') summary.promotionReady += 1
    if (phase === 'candidate_cooldown') summary.coolingDown += 1
    if (selectionState === 'challenger') summary.challengers += 1
    if (selectionState === 'trailing') summary.trailing += 1
  }
  return summary
})
const topCandidates = computed(() => visibleCandidates.value.slice(0, 3))
const topUniverseCandidates = computed(() => universeSelection.value?.candidates?.slice(0, 5) ?? [])
const visibleCandidateCount = computed(() => Math.max(command.value?.candidate_count ?? 0, visibleCandidates.value.length))
const isSampleMode = computed(() => {
  if (!commandQuery.isSuccess.value || !command.value) return false
  const sourceKind = visibleActiveProposal.value?.source_kind ?? command.value?.active_strategy.proposal?.source_kind
  const laneValues = Object.values(eventLaneSources.value)
  const degradedLanes = laneValues.some((value) => value === 'unavailable' || value.startsWith('demo_'))
  return sourceKind === 'mock' || degradedLanes || !!llmStatus.value?.using_mock_fallback || llmStatus.value?.provider === 'mock'
})

const switchProviderMutation = useMutation({
  mutationFn: (provider: LLMProvider) => api.patchRuntimeLlm(provider),
  onSuccess: async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['command-center'] }),
      queryClient.invalidateQueries({ queryKey: ['research-proposals'] }),
    ])
  },
})
const triggerSyncMutation = useMutation({
  mutationFn: api.triggerRuntimeSync,
  onSuccess: async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ['command-center'] }),
      queryClient.invalidateQueries({ queryKey: ['command-candidates'] }),
      queryClient.invalidateQueries({ queryKey: ['research-proposals'] }),
    ])
  },
})

const navOption = computed(() => {
  const nav = [...navRows.value].reverse()
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 18, top: 24, bottom: 36 },
    xAxis: { type: 'category', data: nav.map((item) => item.trade_date) },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'line',
        smooth: true,
        data: nav.map((item) => item.total_equity),
        lineStyle: { color: '#0f766e', width: 2.5 },
        itemStyle: { color: '#0f766e' },
        areaStyle: { color: 'rgba(15, 118, 110, 0.12)' },
      },
    ],
  }
})

function decisionVariant(action?: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (action === 'promote_to_paper') return 'success'
  if (action === 'keep_candidate') return 'info'
  if (action === 'pause_active' || action === 'rollback_to_previous_stable') return 'warning'
  if (action === 'reject') return 'danger'
  return 'neutral'
}

function llmVariant(status?: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (status === 'ready') return 'success'
  if (status === 'mock') return 'info'
  if (status === 'missing_key' || status === 'auth_error' || status === 'rate_limited') return 'warning'
  if (status === 'network_error' || status === 'provider_error' || status === 'parse_error') return 'danger'
  return 'neutral'
}

function runtimeVariant(state?: string, degraded?: boolean, stalled?: boolean): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (state === 'running') return 'info'
  if (state === 'failed') return 'danger'
  if (state === 'stalled' || stalled) return 'warning'
  if (state === 'degraded' || degraded) return 'warning'
  if (state === 'idle') return 'success'
  return 'neutral'
}

function switchProvider(provider: LLMProvider): void {
  if (switchProviderMutation.isPending.value) return
  switchProviderMutation.mutate(provider)
}

function triggerSync(): void {
  if (triggerSyncMutation.isPending.value) return
  triggerSyncMutation.mutate()
}

function llmStatusLabel(status?: string): string {
  return displayLabel(t, 'llmStatus', status)
}

function riskActionLabel(action?: string): string {
  return displayLabel(t, 'riskAction', action)
}

function eventTypeLabel(eventType?: string): string {
  return displayLabel(t, 'eventType', eventType)
}

function auditEventLabel(eventType?: string): string {
  return displayLabel(t, 'auditEvent', eventType)
}

function laneLabel(lane?: string): string {
  return displayLabel(t, 'eventLane', lane)
}

function universeReasonTagLabel(tag?: string): string {
  return displayLabel(t, 'universeReasonTag', tag)
}

function formatSignedMetric(value?: number | null, suffix = ''): string {
  if (value === null || value === undefined) return '--'
  return `${value > 0 ? '+' : ''}${value}${suffix}`
}

function proposalStatusLabel(status?: string): string {
  return displayLabel(t, 'proposalStatus', status)
}

function sourceKindLabel(sourceKind?: string): string {
  return displayLabel(t, 'sourceKind', sourceKind)
}

function orderSideLabel(side?: string | null): string {
  return displayLabel(t, 'orderSide', side?.toLowerCase())
}

function boolLabel(value?: boolean): string {
  return value ? t('common.passed') : t('common.blocked')
}

function governanceReasonLabel(reason?: string): string {
  return displayLabel(t, 'governanceReason', reason)
}

function qualityBandLabel(value?: string): string {
  return displayLabel(t, 'qualityBand', value)
}

function acceptanceStatusLabel(value?: string): string {
  return displayLabel(t, 'acceptanceStatus', value)
}

function qualityTrendLabel(value?: string): string {
  return displayLabel(t, 'qualityTrend', value)
}

function acceptanceReportStatusLabel(value?: string): string {
  return displayLabel(t, 'acceptanceReportStatus', value)
}

function runtimeStateLabel(value?: string): string {
  return displayLabel(t, 'runtimeState', value)
}

function pipelineStageLabel(value?: string): string {
  return displayLabel(t, 'pipelineStage', value)
}

function paperExecutionStatusLabel(status?: string): string {
  return status === 'executed' ? t('paper.executionRecorded') : status === 'skipped' ? t('paper.executionSkipped') : '--'
}

function yesNoLabel(value?: boolean): string {
  if (value === undefined || value === null) return '--'
  return value ? t('common.yes') : t('common.no')
}

function governancePhaseLabel(value?: string): string {
  return displayLabel(t, 'governancePhase', value)
}

function marketBiasLabel(value?: string): string {
  return displayLabel(t, 'marketBias', value)
}

function formatDurationMs(value?: number): string {
  if (value === undefined || value === null) return '--'
  if (value < 1000) return `${value} ms`
  return `${(value / 1000).toFixed(1)} s`
}

function governanceNextStepLabel(value?: string): string {
  return displayLabel(t, 'governanceNextStep', value)
}

function lifecycleEtaKindLabel(value?: string): string {
  return displayLabel(t, 'lifecycleEtaKind', value)
}

function resumeConditionLabel(value?: string): string {
  return displayLabel(t, 'resumeCondition', value)
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

function formatHours(value?: number | null): string {
  if (value === null || value === undefined) return '--'
  return `${value.toFixed(1)}h`
}

function formatMetricLabel(key: string): string {
  if (key === 'deterministic') return t('candidates.deterministic')
  if (key === 'llm') return t('candidates.llm')
  if (key === 'final') return t('candidates.final')
  if (key === 'volatility') return 'Volatility'
  if (key === 'trend_strength') return 'Trend Strength'
  if (key === 'aggregate_sentiment') return t('command.eventSentiment')
  if (key === 'macro_bias') return t('command.eventStrength')
  return humanizeLabel(key)
}
</script>

<template>
  <div class="space-y-4">
    <Card v-if="isSampleMode" class="border border-amber-200 bg-amber-50/80">
      <h3 class="text-sm font-semibold text-amber-900">{{ t('command.sampleModeTitle') }}</h3>
      <p class="mt-1 text-sm text-amber-800">{{ t('command.sampleModeBody') }}</p>
    </Card>

    <div class="metric-grid">
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.activeStrategy') }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ visibleActiveProposal?.title ?? '--' }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.candidateCount') }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ visibleCandidateCount }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.marketRegime') }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ command?.market_snapshot.regime ?? '--' }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.latestScore') }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ command?.latest_risk_decision?.final_score?.toFixed(1) ?? '--' }}</p>
      </Card>
    </div>

    <div class="metric-grid">
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.runtimeStatus') }}</p>
        <div class="mt-2 flex items-center gap-3">
          <p class="text-2xl font-semibold">{{ runtimeStateLabel(runtimeStatus?.current_state) }}</p>
          <Badge :variant="runtimeVariant(runtimeStatus?.current_state, runtimeStatus?.degraded, runtimeStatus?.stalled)">
            {{ runtimeStatus?.degraded || runtimeStatus?.stalled ? t('command.runtimeDegraded') : t('command.runtimeHealthy') }}
          </Badge>
        </div>
        <p class="mt-2 text-sm text-slate-600">{{ runtimeStatus?.status_message ?? t('common.noData') }}</p>
        <div class="mt-3 grid gap-2 text-sm">
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/60 px-3 py-2">
            <span class="text-slate-500">{{ t('command.currentStage') }}</span>
            <span class="font-semibold text-slate-900">{{ pipelineStageLabel(runtimeStatus?.current_stage) }}</span>
          </div>
          <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/60 px-3 py-2">
            <span class="text-slate-500">{{ t('command.stageStartedAt') }}</span>
            <span class="font-semibold text-slate-900">{{ runtimeStatus?.stage_started_at ?? '--' }}</span>
          </div>
        </div>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.lastRunAt') }}</p>
        <p class="mt-2 text-sm font-semibold">{{ runtimeStatus?.last_run_at ?? '--' }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.lastSuccessAt') }}</p>
        <p class="mt-2 text-sm font-semibold">{{ runtimeStatus?.last_success_at ?? '--' }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.consecutiveFailures') }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ runtimeStatus?.consecutive_failures ?? 0 }}</p>
      </Card>
    </div>

    <Card class="space-y-4">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.runtimeStatus') }}</p>
          <div class="mt-2 flex items-center gap-3">
            <p class="text-2xl font-semibold">{{ runtimeStateLabel(runtimeStatus?.current_state) }}</p>
            <Badge :variant="runtimeVariant(runtimeStatus?.current_state, runtimeStatus?.degraded, runtimeStatus?.stalled)">
              {{ runtimeStatus?.degraded || runtimeStatus?.stalled ? t('command.runtimeDegraded') : t('command.runtimeHealthy') }}
            </Badge>
          </div>
          <p class="mt-1 text-sm text-slate-600">{{ runtimeStatus?.expected_next_run_at ?? t('common.noData') }}</p>
          <p class="mt-2 text-sm text-slate-600">
            {{ t('command.currentStage') }}: {{ pipelineStageLabel(runtimeStatus?.current_stage) }}
          </p>
        </div>

        <div>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.llmProvider') }}</p>
          <div class="mt-2 flex items-center gap-3">
            <p class="text-2xl font-semibold">{{ llmStatus?.provider ?? '--' }}</p>
            <Badge :variant="llmVariant(llmStatus?.status)">{{ llmStatusLabel(llmStatus?.status) }}</Badge>
          </div>
          <p class="mt-1 text-sm text-slate-600">{{ llmStatus?.model ?? '--' }}</p>
          <p class="mt-2 text-sm text-slate-600">{{ llmStatus?.message }}</p>
        </div>

        <div class="flex flex-col items-start gap-2">
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.switchProvider') }}</p>
          <div class="flex gap-2">
            <button
              type="button"
              class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors"
              :class="llmStatus?.provider === 'minimax' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300 bg-white text-slate-900 hover:bg-slate-50'"
              @click="switchProvider('minimax')"
            >
              MiniMax
            </button>
            <button
              type="button"
              class="rounded-lg border px-3 py-2 text-sm font-medium transition-colors"
              :class="llmStatus?.provider === 'mock' ? 'border-slate-900 bg-slate-900 text-white' : 'border-slate-300 bg-white text-slate-900 hover:bg-slate-50'"
              @click="switchProvider('mock')"
            >
              Mock
            </button>
          </div>
          <p v-if="switchProviderMutation.isError.value" class="text-sm text-rose-700">
            {{ switchProviderMutation.error.value instanceof Error ? switchProviderMutation.error.value.message : t('command.providerSwitchError') }}
          </p>
          <button
            type="button"
            class="rounded-lg border border-teal-700 bg-teal-700 px-3 py-2 text-sm font-medium text-white transition-colors hover:bg-teal-800 disabled:cursor-not-allowed disabled:opacity-60"
            :disabled="triggerSyncMutation.isPending.value || runtimeStatus?.current_state === 'running'"
            @click="triggerSync"
          >
            {{ t('command.runNow') }}
          </button>
          <p v-if="triggerSyncMutation.isError.value" class="text-sm text-rose-700">
            {{ triggerSyncMutation.error.value instanceof Error ? triggerSyncMutation.error.value.message : t('command.syncTriggerError') }}
          </p>
        </div>
      </div>
      <div
        v-if="runtimeStatus?.stage_durations_ms && Object.keys(runtimeStatus.stage_durations_ms).length"
        class="grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4"
      >
        <div
          v-for="(value, key) in runtimeStatus.stage_durations_ms"
          :key="key"
          class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2"
        >
          <p class="text-slate-500">{{ pipelineStageLabel(String(key)) }}</p>
          <p class="mt-1 font-semibold text-slate-900">{{ formatDurationMs(Number(value)) }}</p>
        </div>
      </div>
    </Card>

    <div class="grid gap-4 xl:grid-cols-[1.45fr,1fr]">
      <Card class="space-y-4">
        <div class="mb-3 flex items-center justify-between">
          <div>
            <h3 class="text-sm font-semibold">{{ t('command.marketPulse') }}</h3>
            <p class="mt-1 text-sm text-slate-600">{{ command?.market_snapshot.summary }}</p>
          </div>
          <Badge variant="info">{{ command?.market_snapshot.confidence?.toFixed(2) ?? '--' }}</Badge>
        </div>
        <VChart class="h-[300px] w-full" :option="navOption" autoresize />
        <div class="grid gap-4 md:grid-cols-[1.15fr,0.85fr]">
          <div>
            <h3 class="text-sm font-semibold">{{ t('command.watchpoints') }}</h3>
            <div class="mt-3 flex flex-wrap gap-2">
              <Badge v-for="point in watchpoints" :key="point" variant="warning">{{ point }}</Badge>
              <span v-if="watchpoints.length === 0" class="text-sm text-slate-500">{{ t('common.noData') }}</span>
            </div>
          </div>
          <div>
            <h3 class="text-sm font-semibold">{{ t('command.macroContext') }}</h3>
            <div class="mt-3 grid gap-2">
              <div
                v-for="metric in signalContext"
                :key="metric.key"
                class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2 text-sm"
              >
                <span class="text-slate-500">{{ formatMetricLabel(metric.key) }}</span>
                <span class="font-semibold text-slate-900">{{ metric.value.toFixed(3) }}</span>
              </div>
              <span v-if="signalContext.length === 0" class="text-sm text-slate-500">{{ t('common.noData') }}</span>
            </div>
          </div>
        </div>
        <div class="grid gap-3 rounded-xl border border-slate-200/80 bg-slate-50/80 p-4 lg:grid-cols-2">
          <div>
            <h3 class="text-sm font-semibold">{{ t('command.marketProfile') }}</h3>
            <p class="mt-1 text-sm text-slate-600">{{ marketProfile?.label ?? t('common.noData') }}</p>
            <p class="mt-2 text-xs text-slate-500">
              {{ t('command.marketBenchmark') }}: {{ marketProfile?.benchmark_symbol ?? '--' }}
            </p>
            <p class="mt-1 text-xs text-slate-500">
              {{ t('command.marketTradingStyle') }}: {{ marketProfile?.trading_style ?? '--' }}
            </p>
          </div>
          <div class="space-y-3">
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{{ t('command.preferredBaselineTags') }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge v-for="tag in marketProfile?.preferred_baseline_tags ?? []" :key="`preferred-${tag}`" variant="success">{{ tag }}</Badge>
                <span v-if="!(marketProfile?.preferred_baseline_tags?.length)" class="text-sm text-slate-500">{{ t('common.noData') }}</span>
              </div>
            </div>
            <div>
              <p class="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">{{ t('command.discouragedBaselineTags') }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge v-for="tag in marketProfile?.discouraged_baseline_tags ?? []" :key="`discouraged-${tag}`" variant="warning">{{ tag }}</Badge>
                <span v-if="!(marketProfile?.discouraged_baseline_tags?.length)" class="text-sm text-slate-500">{{ t('common.noData') }}</span>
              </div>
            </div>
          </div>
        </div>
        <div class="rounded-xl border border-slate-200/80 bg-slate-50/80 p-4">
          <div class="flex items-center justify-between gap-3">
            <div>
              <h3 class="text-sm font-semibold">{{ t('command.universeSelection') }}</h3>
              <p class="mt-1 text-sm text-slate-600">
                {{ t('command.selectedUniverseSymbol') }}: {{ universeSelection?.selected_symbol ?? command?.market_snapshot.symbol ?? '--' }}
              </p>
              <p class="mt-1 text-xs text-slate-500">
                {{ t('command.selectionReason') }}: {{ universeSelection?.selection_reason ?? t('common.noData') }}
              </p>
            </div>
            <Badge variant="info">{{ humanizeLabel(universeSelection?.mode) }}</Badge>
          </div>
          <div v-if="universeSelection?.top_factors?.length" class="mt-3 flex flex-wrap gap-2">
            <Badge v-for="factor in universeSelection.top_factors" :key="`factor-${factor}`" variant="success">
              {{ universeReasonTagLabel(factor) }}
            </Badge>
          </div>
          <div v-if="selectedUniverseCandidate?.factor_scores" class="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div
              v-for="(value, key) in selectedUniverseCandidate.factor_scores"
              :key="`selected-factor-${String(key)}`"
              class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2"
            >
              <span class="text-slate-500">{{ humanizeLabel(String(key)) }}</span>
              <span class="font-semibold text-slate-900">{{ formatSignedMetric(Number(value)) }}</span>
            </div>
          </div>
          <div class="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.visibleUniverseCount') }}</span>
              <span class="font-semibold text-slate-900">{{ universeSelection?.candidate_count ?? topUniverseCandidates.length }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.turnoverThreshold') }}</span>
              <span class="font-semibold text-slate-900">
                {{ universeSelection?.min_turnover_millions !== null && universeSelection?.min_turnover_millions !== undefined ? `${universeSelection.min_turnover_millions}M` : '--' }}
              </span>
            </div>
          </div>
          <div v-if="marketProfile?.benchmark_symbol" class="mt-3 rounded-lg border border-slate-200/80 bg-white/70 p-3 text-sm">
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ t('command.benchmarkComparison') }}</p>
              <Badge variant="neutral">{{ marketProfile.benchmark_symbol }}</Badge>
            </div>
            <p class="mt-2 text-slate-600">
              {{
                benchmarkUniverseCandidate
                  ? t('command.benchmarkGapMessage', {
                      selected: universeSelection?.selected_symbol ?? '--',
                      benchmark: marketProfile.benchmark_symbol,
                      gap: universeSelection?.benchmark_gap ?? '--',
                    })
                  : t('command.benchmarkNotInView', { benchmark: marketProfile.benchmark_symbol })
              }}
            </p>
            <div v-if="benchmarkUniverseCandidate" class="mt-2 grid gap-2 sm:grid-cols-2">
              <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2">
                <p class="text-slate-500">{{ t('command.selectionScore') }}</p>
                <p class="mt-1 font-semibold text-slate-900">{{ benchmarkUniverseCandidate.score ?? '--' }}</p>
              </div>
              <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2">
                <p class="text-slate-500">{{ t('command.selectionReason') }}</p>
                <p class="mt-1 text-slate-700">{{ benchmarkUniverseCandidate.selection_reason ?? t('common.noData') }}</p>
              </div>
            </div>
          </div>
          <div class="mt-3 grid gap-2">
            <div
              v-for="candidate in topUniverseCandidates"
              :key="candidate.symbol"
              class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2 text-sm"
            >
              <div>
                <p class="font-medium text-slate-900">
                  #{{ candidate.rank ?? '--' }} · {{ candidate.symbol }} · {{ candidate.name }}
                </p>
                <p class="text-xs text-slate-500">
                  {{ t('command.turnoverMillions') }}: {{ candidate.turnover_millions ?? '--' }}
                </p>
                <p class="mt-1 text-xs text-slate-500">
                  {{ t('command.selectionReason') }}: {{ candidate.selection_reason ?? t('common.noData') }}
                </p>
                <p class="mt-1 text-xs text-slate-500">
                  20D: {{ formatSignedMetric(candidate.return_20d_pct, '%') }} · 60D: {{ formatSignedMetric(candidate.return_60d_pct, '%') }}
                </p>
                <div v-if="candidate.reason_tags?.length" class="mt-2 flex flex-wrap gap-1">
                  <Badge
                    v-for="tag in candidate.reason_tags"
                    :key="`${candidate.symbol}-${tag}`"
                    variant="neutral"
                  >
                    {{ universeReasonTagLabel(tag) }}
                  </Badge>
                </div>
              </div>
              <div class="text-right">
                <p class="font-semibold text-slate-900">{{ candidate.change_pct !== null && candidate.change_pct !== undefined ? `${candidate.change_pct}%` : '--' }}</p>
                <p class="text-xs text-slate-500">{{ t('command.selectionScore') }}: {{ candidate.score ?? '--' }}</p>
                <p class="text-xs text-slate-500">
                  {{ t('command.selectionAmplitude') }}: {{ candidate.amplitude_pct !== null && candidate.amplitude_pct !== undefined ? `${candidate.amplitude_pct}%` : '--' }}
                </p>
                <p class="text-xs text-slate-500">
                  20D Vol: {{ candidate.volatility_20d_pct !== null && candidate.volatility_20d_pct !== undefined ? `${candidate.volatility_20d_pct}%` : '--' }}
                </p>
              </div>
            </div>
            <span v-if="topUniverseCandidates.length === 0" class="text-sm text-slate-500">{{ t('common.noData') }}</span>
          </div>
        </div>
      </Card>

      <Card class="space-y-4">
        <div>
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold">{{ t('command.macroPipeline') }}</h3>
            <Badge :variant="macroStatus?.degraded ? 'warning' : 'success'">
              {{ llmStatusLabel(macroStatus?.status) }}
            </Badge>
          </div>
          <p class="mt-2 text-sm text-slate-600">{{ macroStatus?.message }}</p>
          <p class="mt-2 text-xs text-slate-500">
            {{ t('command.lastSuccess') }}: {{ macroStatus?.last_success_at ?? t('common.noData') }}
          </p>
          <div class="mt-3 grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.macroReliability') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  macroStatus?.reliability_score !== undefined && macroStatus?.reliability_score !== null
                    ? `${Math.round(macroStatus.reliability_score * 100)}%`
                    : t('common.noData')
                }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.activeMacroProvider') }}</span>
              <span class="font-semibold text-slate-900">{{ macroStatus?.active_provider ?? t('common.noData') }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.macroTier') }}</span>
              <span class="font-semibold text-slate-900">{{ humanizeLabel(macroStatus?.reliability_tier) }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.macroFreshness') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  macroStatus?.freshness_hours !== undefined && macroStatus?.freshness_hours !== null
                    ? `${macroStatus.freshness_hours}h · ${humanizeLabel(macroStatus?.freshness_tier)}`
                    : t('common.noData')
                }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.macroHealth30d') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  macroStatus?.health_score_30d !== undefined && macroStatus?.health_score_30d !== null
                    ? `${Math.round(macroStatus.health_score_30d * 100)}%`
                    : t('common.noData')
                }}
              </span>
            </div>
          </div>
          <div v-if="macroStatus?.provider_chain?.length" class="mt-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.macroProviderChain') }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Badge
                v-for="provider in macroStatus.provider_chain"
                :key="provider"
                variant="neutral"
              >
                {{ provider }}
              </Badge>
            </div>
          </div>
          <p
            v-if="macroStatus?.using_last_known_context"
            class="mt-2 text-xs text-amber-700"
          >
            {{ t('command.fallbackContext') }}:
            {{ macroStatus?.fallback_event_count ?? 0 }}
          </p>
        </div>
        <div>
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold">{{ t('command.latestDecision') }}</h3>
            <Badge :variant="decisionVariant(command?.latest_risk_decision?.action)">
              {{ riskActionLabel(command?.latest_risk_decision?.action) }}
            </Badge>
          </div>
          <p class="mt-2 text-sm text-slate-600">{{ command?.latest_risk_decision?.llm_explanation }}</p>
        </div>
        <div>
          <h3 class="text-sm font-semibold">{{ t('command.candidatePool') }}</h3>
          <div class="mt-3 grid grid-cols-2 gap-3 text-sm">
            <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <p class="text-slate-500">{{ t('candidates.promotionReady') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ candidateSummary.promotionReady }}</p>
            </div>
            <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <p class="text-slate-500">{{ t('candidates.coolingDown') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ candidateSummary.coolingDown }}</p>
            </div>
            <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <p class="text-slate-500">{{ t('candidates.challengers') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ candidateSummary.challengers }}</p>
            </div>
            <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <p class="text-slate-500">{{ t('candidates.trailing') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ candidateSummary.trailing }}</p>
            </div>
          </div>
          <div class="mt-4 space-y-2">
            <div
              v-for="item in topCandidates"
              :key="item.proposal.id"
              class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3"
            >
              <div class="flex items-start justify-between gap-3">
                <div>
                  <p class="font-medium text-slate-900">{{ item.proposal.title }}</p>
                  <p class="mt-1 text-xs text-slate-500">
                    {{ sourceKindLabel(item.proposal.source_kind) }} ·
                    {{ proposalStatusLabel(item.proposal.status) }}
                  </p>
                </div>
                <Badge :variant="decisionVariant(item.latest_decision?.action)">
                  {{ riskActionLabel(item.latest_decision?.action) }}
                </Badge>
              </div>
              <div class="mt-3 grid grid-cols-3 gap-2 text-xs">
                <div class="rounded-md bg-slate-50 px-2 py-2">
                  <p class="text-slate-500">{{ t('candidates.final') }}</p>
                  <p class="mt-1 font-semibold text-slate-900">{{ item.proposal.final_score.toFixed(1) }}</p>
                </div>
                <div class="rounded-md bg-slate-50 px-2 py-2">
                  <p class="text-slate-500">{{ t('candidates.phase') }}</p>
                  <p class="mt-1 font-semibold text-slate-900">
                    {{ governancePhaseLabel(item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.phase) }}
                  </p>
                </div>
                <div class="rounded-md bg-slate-50 px-2 py-2">
                  <p class="text-slate-500">{{ t('candidates.poolRank') }}</p>
                  <p class="mt-1 font-semibold text-slate-900">
                    {{ item.proposal.evidence_pack?.quality_report?.pool_ranking?.rank ?? '--' }}
                  </p>
                </div>
              </div>
            </div>
            <p v-if="topCandidates.length === 0" class="text-sm text-slate-500">
              {{ t('command.candidatePreviewEmpty') }}
            </p>
          </div>
        </div>
        <div v-if="latestPaperExecution">
          <h3 class="text-sm font-semibold">{{ t('command.paperExecution') }}</h3>
          <div class="mt-3 grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.executionStatus') }}</span>
              <span class="font-semibold text-slate-900">{{ paperExecutionStatusLabel(latestPaperExecution.status) }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.signal') }}</span>
              <span class="font-semibold text-slate-900">{{ latestPaperExecution.signal ?? '--' }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.targetQuantity') }}</span>
              <span class="font-semibold text-slate-900">{{ latestPaperExecution.target_quantity ?? '--' }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.rebalanceAction') }}</span>
              <span class="font-semibold text-slate-900">
                {{ (latestPaperExecution.order_quantity ?? 0) > 0 ? orderSideLabel(latestPaperExecution.order_side) : t('paper.noRebalance') }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.priceAsOf') }}</span>
              <span class="font-semibold text-slate-900">{{ formatDateTime(latestPaperExecution.latest_price_as_of) }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.priceFreshness') }}</span>
              <span class="font-semibold text-slate-900">{{ formatHours(latestPaperExecution.price_age_hours) }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.priceChanged') }}</span>
              <span class="font-semibold text-slate-900">{{ yesNoLabel(latestPaperExecution.price_changed) }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.equityMoved') }}</span>
              <span class="font-semibold text-slate-900">{{ yesNoLabel(latestPaperExecution.equity_changed) }}</span>
            </div>
          </div>
          <p class="mt-3 rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3 text-sm text-slate-600">
            {{ latestPaperExecution.explanation ?? t('common.noData') }}
          </p>
        </div>
        <div v-if="acceptanceReport">
          <h3 class="text-sm font-semibold">{{ t('command.acceptanceReport') }}</h3>
          <div class="mt-3 grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.acceptanceStatus') }}</span>
              <span class="font-semibold text-slate-900">
                {{ acceptanceReportStatusLabel(String(acceptanceReport.status ?? 'watch')) }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.reportWindow') }}</span>
              <span class="font-semibold text-slate-900">{{ acceptanceReport.window_days }}d</span>
            </div>
          </div>
          <div v-if="acceptanceReport.key_findings.length" class="mt-3 flex flex-wrap gap-2">
            <Badge
              v-for="item in acceptanceReport.key_findings"
              :key="item"
              variant="neutral"
            >
              {{ humanizeLabel(item) }}
            </Badge>
          </div>
          <div v-if="acceptanceReport.next_actions.length" class="mt-3 flex flex-wrap gap-2">
            <Badge
              v-for="item in acceptanceReport.next_actions"
              :key="item"
              variant="warning"
            >
              {{ humanizeLabel(item) }}
            </Badge>
          </div>
        </div>
        <div>
          <h3 class="text-sm font-semibold">{{ t('command.scoreBreakdown') }}</h3>
          <div class="mt-3 grid grid-cols-3 gap-3 text-sm">
            <div v-for="item in scoreBreakdown" :key="item.key" class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <p class="text-slate-500">{{ formatMetricLabel(item.key) }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ item.value }}</p>
            </div>
          </div>
        </div>
        <div>
          <h3 class="text-sm font-semibold">{{ t('command.bottomLine') }}</h3>
          <div class="mt-3 flex flex-wrap gap-2">
            <Badge
              v-for="[key, value] in bottomLineReport"
              :key="key"
              :variant="value ? 'success' : 'danger'"
            >
              {{ humanizeLabel(String(key)) }} · {{ boolLabel(Boolean(value)) }}
            </Badge>
          </div>
        </div>
        <div v-if="Array.isArray(latestDecision?.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons)">
          <h3 class="text-sm font-semibold">{{ t('command.governanceReasons') }}</h3>
          <div class="mt-3 flex flex-wrap gap-2">
            <Badge
              v-for="reason in latestDecision?.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []"
              :key="String(reason)"
              variant="warning"
            >
              {{ governanceReasonLabel(String(reason)) }}
            </Badge>
          </div>
        </div>
        <div v-if="latestDecision?.evidence_pack?.quality_report">
          <h3 class="text-sm font-semibold">{{ t('command.qualityGate') }}</h3>
          <div class="mt-3 grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.qualityBand') }}</span>
              <span class="font-semibold text-slate-900">
                {{ qualityBandLabel(String(latestDecision?.evidence_pack?.quality_report?.verdict?.quality_band ?? 'fragile')) }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.oosPassRate') }}</span>
              <span class="font-semibold text-slate-900">
                {{ latestDecision?.evidence_pack?.quality_report?.oos_validation?.walkforward_pass_rate ?? t('common.noData') }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.oosWindows') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  latestDecision?.evidence_pack?.quality_report?.oos_validation?.passed_windows !== undefined
                    ? `${latestDecision?.evidence_pack?.quality_report?.oos_validation?.passed_windows}/${latestDecision?.evidence_pack?.quality_report?.oos_validation?.total_windows ?? '--'}`
                    : t('common.noData')
                }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.accumulable') }}</span>
              <span class="font-semibold text-slate-900">
                {{ boolLabel(Boolean(latestDecision?.evidence_pack?.quality_report?.verdict?.accumulable)) }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.percentile') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  latestDecision?.evidence_pack?.quality_report?.pool_ranking?.percentile !== undefined
                    ? `${Math.round(Number(latestDecision?.evidence_pack?.quality_report?.pool_ranking?.percentile) * 100)}%`
                    : t('common.noData')
                }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.trackRecordTrend') }}</span>
              <span class="font-semibold text-slate-900">
                {{ qualityTrendLabel(String(latestDecision?.evidence_pack?.quality_report?.track_record?.trend ?? 'flat')) }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.trackRecordComparable') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  latestDecision?.evidence_pack?.quality_report?.track_record?.recent_comparable !== undefined
                    ? `${latestDecision?.evidence_pack?.quality_report?.track_record?.recent_comparable}/${latestDecision?.evidence_pack?.quality_report?.track_record?.recent_total ?? '--'}`
                    : t('common.noData')
                }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.trackRecord30d') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  latestDecision?.evidence_pack?.quality_report?.track_record?.recent_30d_comparable !== undefined
                    ? `${latestDecision?.evidence_pack?.quality_report?.track_record?.recent_30d_comparable}/${latestDecision?.evidence_pack?.quality_report?.track_record?.recent_30d_total ?? '--'}`
                    : t('common.noData')
                }}
              </span>
            </div>
          </div>
        </div>
        <div v-if="Object.keys(operationalAcceptance).length">
          <h3 class="text-sm font-semibold">{{ t('command.operationalAcceptance') }}</h3>
          <div class="mt-3 grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.acceptanceStatus') }}</span>
              <span class="font-semibold text-slate-900">
                {{ acceptanceStatusLabel(String(operationalAcceptance.status ?? 'review_required')) }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.liveDays') }}</span>
              <span class="font-semibold text-slate-900">{{ operationalAcceptance.live_days ?? t('common.noData') }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('paper.fillRate') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  operationalAcceptance.fill_rate !== undefined && operationalAcceptance.fill_rate !== null
                    ? `${Math.round(Number(operationalAcceptance.fill_rate) * 100)}%`
                    : t('common.noData')
                }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.operationalScore') }}</span>
              <span class="font-semibold text-slate-900">
                {{
                  operationalAcceptance.operational_score !== undefined && operationalAcceptance.operational_score !== null
                    ? `${Math.round(Number(operationalAcceptance.operational_score) * 100)}%`
                    : t('common.noData')
                }}
              </span>
            </div>
          </div>
        </div>
        <div v-if="latestDecision?.evidence_pack?.governance_report?.lifecycle">
          <h3 class="text-sm font-semibold">{{ t('command.strategyFlow') }}</h3>
          <div class="mt-3 grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('candidates.phase') }}</span>
              <span class="font-semibold text-slate-900">
                {{ governancePhaseLabel(String(latestDecision?.evidence_pack?.governance_report?.lifecycle?.phase ?? 'candidate_watch')) }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('candidates.nextStep') }}</span>
              <span class="font-semibold text-slate-900">
                {{ governanceNextStepLabel(String(latestDecision?.evidence_pack?.governance_report?.lifecycle?.next_step ?? 'monitor_candidate')) }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('command.estimatedEligibility') }}</span>
              <span class="text-right font-semibold text-slate-900">
                {{
                  latestDecision?.evidence_pack?.governance_report?.lifecycle?.estimated_next_eligible_at
                    ? formatDateTime(String(latestDecision?.evidence_pack?.governance_report?.lifecycle?.estimated_next_eligible_at))
                    : lifecycleEtaKindLabel(String(latestDecision?.evidence_pack?.governance_report?.lifecycle?.eta_kind ?? 'unknown'))
                }}
              </span>
            </div>
            <div
              v-if="Array.isArray(latestDecision?.evidence_pack?.governance_report?.lifecycle?.resume_conditions)"
              class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2"
            >
              <p class="text-slate-500">{{ t('paper.resumeConditions') }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge
                  v-for="condition in latestDecision?.evidence_pack?.governance_report?.lifecycle?.resume_conditions ?? []"
                  :key="String(condition)"
                  variant="warning"
                >
                  {{ resumeConditionLabel(String(condition)) }}
                </Badge>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.1fr,0.9fr]">
      <Card class="space-y-4">
        <div class="flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('command.strategyBrief') }}</h3>
          <Badge :variant="visibleActiveProposal?.status === 'active' ? 'success' : 'info'">
            {{ proposalStatusLabel(visibleActiveProposal?.status) }}
          </Badge>
        </div>
        <div>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.thesis') }}</p>
          <p class="mt-2 text-sm text-slate-700">{{ visibleActiveProposal?.thesis ?? t('common.noData') }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Badge variant="info">{{ sourceKindLabel(visibleActiveProposal?.source_kind) }}</Badge>
          <Badge variant="neutral">{{ llmStatusLabel(visibleActiveProposal?.provider_status) }}</Badge>
          <Badge
            v-for="feature in visibleActiveProposal?.features_used ?? []"
            :key="feature"
            variant="neutral"
          >
            {{ feature }}
          </Badge>
        </div>
        <div>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.providerMessage') }}</p>
          <p class="mt-2 text-sm text-slate-600">{{ visibleActiveProposal?.provider_message || llmStatus?.message || t('common.noData') }}</p>
        </div>
      </Card>

      <Card class="space-y-4">
        <div>
          <h3 class="text-sm font-semibold">{{ t('command.eventDigest') }}</h3>
          <p class="mt-2 text-sm text-slate-700">{{ command?.latest_event_digest.macro_summary }}</p>
        </div>
        <div class="grid grid-cols-2 gap-3 text-sm">
          <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <p class="text-slate-500">{{ t('command.eventSentiment') }}</p>
            <p class="mt-1 font-semibold text-slate-900">{{ Number(latestDigestScores.aggregate_sentiment ?? 0).toFixed(2) }}</p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
            <p class="text-slate-500">{{ t('command.eventStrength') }}</p>
            <p class="mt-1 font-semibold text-slate-900">{{ Number(latestDigestScores.macro_bias ?? 0).toFixed(2) }}</p>
          </div>
        </div>
        <div>
          <h3 class="text-sm font-semibold">{{ t('command.eventLanes') }}</h3>
          <div class="mt-2 flex flex-wrap gap-2">
            <Badge v-for="(source, lane) in eventLaneSources" :key="lane" variant="neutral">
              {{ laneLabel(String(lane)) }}: {{ source }}
            </Badge>
          </div>
        </div>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.2fr,1fr]">
      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('command.baselineCatalog') }}</h3>
          <Badge variant="neutral">{{ strategyCatalog.length }}</Badge>
        </div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-1">
          <div
            v-for="strategy in strategyCatalog"
            :key="strategy.strategy_name"
            class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
          >
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ strategy.strategy_name }}</p>
              <Badge :variant="strategy.enabled ? 'success' : 'neutral'">
                {{ strategy.enabled ? t('common.enabled') : t('common.disabled') }}
              </Badge>
            </div>
            <p class="mt-2 text-sm text-slate-600">{{ strategy.description }}</p>
            <p class="mt-2 text-xs text-slate-500">
              {{ t('command.defaultParamsCount') }}: {{ Object.keys(strategy.default_params ?? {}).length }}
            </p>
            <div class="mt-3 flex flex-wrap gap-2">
              <Badge v-for="tag in strategy.tags" :key="`${strategy.strategy_name}-${tag}`" variant="neutral">{{ tag }}</Badge>
            </div>
            <p class="mt-2 text-xs text-slate-500">
              {{ t('command.supportedMarkets') }}: {{ strategy.supported_markets.join(', ') || '--' }}
            </p>
            <p class="mt-1 text-xs text-slate-500">
              {{ t('command.marketBias') }}: {{ marketBiasLabel(strategy.market_bias) }}
            </p>
          </div>
        </div>
      </Card>

      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('command.eventPreview') }}</h3>
          <Badge variant="neutral">{{ command?.market_snapshot.event_stream_preview.length ?? 0 }}</Badge>
        </div>
        <div class="space-y-3">
          <div v-for="event in command?.market_snapshot.event_stream_preview ?? []" :key="event.event_id" class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ event.title }}</p>
              <Badge variant="neutral">{{ eventTypeLabel(event.event_type) }}</Badge>
            </div>
            <p class="mt-1 text-xs text-slate-500">{{ new Date(event.published_at).toLocaleString() }} · {{ event.source }}</p>
          </div>
        </div>
      </Card>

      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('command.auditFeed') }}</h3>
          <Badge variant="info">{{ command?.latest_audit_events.length ?? 0 }}</Badge>
        </div>
        <div class="space-y-3">
          <div v-for="audit in command?.latest_audit_events ?? []" :key="audit.id" class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ auditEventLabel(audit.event_type) }}</p>
              <span class="font-mono text-xs text-slate-500">{{ audit.decision_id }}</span>
            </div>
            <p class="mt-1 text-xs text-slate-500">{{ new Date(audit.created_at).toLocaleString() }}</p>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
