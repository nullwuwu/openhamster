<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel } from '@/lib/display'

use([CanvasRenderer, GridComponent, TooltipComponent, LineChart, BarChart])

const { t, locale } = useI18n()

const activeStrategyQuery = useQuery({
  queryKey: ['paper-active-strategy'],
  queryFn: api.getActivePaperStrategy,
  refetchInterval: 10_000,
})

const active = computed(() => activeStrategyQuery.data.value)
const navRows = computed(() => active.value?.paper_trading.nav ?? [])
const orders = computed(() => active.value?.paper_trading.orders ?? [])
const positions = computed(() => active.value?.paper_trading.positions ?? [])
const latestExecution = computed(() => active.value?.paper_trading.latest_execution ?? null)
const latestDecision = computed(() => active.value?.latest_decision ?? null)
const governanceReport = computed(
  () => latestDecision.value?.evidence_pack?.governance_report ?? null,
)
const activeHealth = computed(
  () => (governanceReport.value?.active_health as Record<string, unknown> | undefined) ?? {},
)
const activeMacroStatus = computed(
  () => (activeHealth.value.macro_status as Record<string, unknown> | undefined) ?? {},
)
const activeComparison = computed(() => governanceReport.value?.active_comparison ?? null)
const blockedReasons = computed(() => governanceReport.value?.promotion_gate?.blocked_reasons ?? [])
const macroDependency = computed(
  () => (governanceReport.value?.macro_dependency as Record<string, unknown> | undefined) ?? {},
)
const macroDependencyStatus = computed(() => {
  const value = macroDependency.value.status ?? activeMacroStatus.value.status
  return value === null || value === undefined ? null : String(value)
})
const macroDependencyProvider = computed(() => {
  const value = macroDependency.value.provider ?? activeMacroStatus.value.provider
  return value === null || value === undefined ? null : String(value)
})
const macroDependencyMessage = computed(() => {
  const value = macroDependency.value.message ?? activeMacroStatus.value.message
  return value === null || value === undefined ? null : String(value)
})
const operationalAcceptance = computed(
  () => (active.value?.operational_acceptance as Record<string, unknown> | undefined) ?? {},
)

const sortedNavRows = computed(() =>
  [...navRows.value].sort((left, right) => left.trade_date.localeCompare(right.trade_date)),
)
const sortedPositions = computed(() =>
  [...positions.value].sort((left, right) => right.market_value - left.market_value),
)
const sortedOrders = computed(() =>
  [...orders.value].sort((left, right) => right.created_at.localeCompare(left.created_at)),
)
const awaitingFirstSnapshot = computed(() =>
  !!active.value?.proposal
  && active.value.proposal.status === 'active'
  && sortedNavRows.value.length === 0
  && sortedOrders.value.length === 0
  && sortedPositions.value.length === 0,
)

const latestNav = computed(() => {
  if (!sortedNavRows.value.length) return null
  return sortedNavRows.value[sortedNavRows.value.length - 1]
})

const previousNav = computed(() => {
  if (sortedNavRows.value.length < 2) return null
  return sortedNavRows.value[sortedNavRows.value.length - 2]
})

const latestEquityChange = computed(() => {
  if (!latestNav.value || !previousNav.value) return null
  return latestNav.value.total_equity - previousNav.value.total_equity
})

const latestCashRatio = computed(() => {
  if (!latestNav.value || latestNav.value.total_equity <= 0) return null
  return latestNav.value.cash / latestNav.value.total_equity
})

const latestGrossExposure = computed(() => {
  if (!latestNav.value || latestNav.value.total_equity <= 0) return null
  return latestNav.value.position_value / latestNav.value.total_equity
})

const orderFillRate = computed(() => {
  if (!sortedOrders.value.length) return null
  const filled = sortedOrders.value.filter((item) => item.status.toLowerCase() === 'filled').length
  return filled / sortedOrders.value.length
})

const lastOrderAt = computed(() => sortedOrders.value[0]?.created_at ?? null)

const liveDrawdown = computed(() => {
  let peak = 0
  let maxDrawdown = 0
  for (const row of sortedNavRows.value) {
    peak = Math.max(peak, row.total_equity)
    if (peak > 0) {
      maxDrawdown = Math.max(maxDrawdown, (peak - row.total_equity) / peak)
    }
  }
  return maxDrawdown || null
})

const pauseThreshold = computed(() => {
  const value = activeHealth.value.pause_threshold
  return typeof value === 'number' ? value : null
})

const rollbackThreshold = computed(() => {
  const value = activeHealth.value.rollback_threshold
  return typeof value === 'number' ? value : null
})
const rebalanceTriggered = computed(() => (latestExecution.value?.order_quantity ?? 0) > 0)
const priceChanged = computed(() => latestExecution.value?.price_changed ?? false)
const equityChanged = computed(() => latestExecution.value?.equity_changed ?? false)

const executionPosture = computed(() => {
  const action = latestDecision.value?.action
  if (action === 'rollback_to_previous_stable') {
    return { label: t('paper.postureEscalated'), variant: 'danger' as const }
  }
  if (action === 'pause_active') {
    return { label: t('paper.postureCaution'), variant: 'warning' as const }
  }
  if ((liveDrawdown.value ?? 0) > 0.08) {
    return { label: t('paper.postureCaution'), variant: 'warning' as const }
  }
  return { label: t('paper.postureStable'), variant: 'success' as const }
})

const navOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 18, top: 24, bottom: 36 },
  xAxis: { type: 'category', data: sortedNavRows.value.map((item) => item.trade_date) },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'line',
      smooth: true,
      data: sortedNavRows.value.map((item) => item.total_equity),
      lineStyle: { color: '#ea580c', width: 2.5 },
      itemStyle: { color: '#ea580c' },
      areaStyle: { color: 'rgba(234, 88, 12, 0.12)' },
    },
  ],
}))

const positionOption = computed(() => ({
  tooltip: { trigger: 'axis' },
  grid: { left: 48, right: 18, top: 24, bottom: 36 },
  xAxis: { type: 'category', data: sortedPositions.value.map((item) => item.symbol) },
  yAxis: { type: 'value' },
  series: [
    {
      type: 'bar',
      data: sortedPositions.value.map((item) => item.market_value),
      itemStyle: { color: '#0f766e' },
    },
  ],
}))

const currencyFormatter = computed(
  () =>
    new Intl.NumberFormat(locale.value, {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 0,
    }),
)

const compactCurrencyFormatter = computed(
  () =>
    new Intl.NumberFormat(locale.value, {
      style: 'currency',
      currency: 'USD',
      notation: 'compact',
      maximumFractionDigits: 1,
    }),
)

const percentFormatter = computed(
  () =>
    new Intl.NumberFormat(locale.value, {
      style: 'percent',
      maximumFractionDigits: 1,
    }),
)

function formatCurrency(value?: number | null): string {
  if (value === null || value === undefined) return '--'
  return currencyFormatter.value.format(value)
}

function formatCompactCurrency(value?: number | null): string {
  if (value === null || value === undefined) return '--'
  return compactCurrencyFormatter.value.format(value)
}

function formatPercent(value?: number | null): string {
  if (value === null || value === undefined) return '--'
  return percentFormatter.value.format(value)
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

function proposalStatusLabel(status?: string): string {
  return displayLabel(t, 'proposalStatus', status)
}

function riskActionLabel(action?: string): string {
  return displayLabel(t, 'riskAction', action)
}

function orderSideLabel(side?: string | null): string {
  return displayLabel(t, 'orderSide', side?.toLowerCase())
}

function orderStatusLabel(status?: string): string {
  return displayLabel(t, 'orderStatus', status?.toLowerCase())
}

function paperExecutionStatusLabel(status?: string): string {
  return status === 'executed' ? t('paper.executionRecorded') : status === 'skipped' ? t('paper.executionSkipped') : '--'
}

function signalLabel(signal?: string | null): string {
  if (!signal) return '--'
  return signal
}

function booleanStatusLabel(value?: boolean): string {
  if (value === undefined || value === null) return '--'
  return value ? t('common.yes') : t('common.no')
}

function formatHours(value?: number | null): string {
  if (value === null || value === undefined) return '--'
  return `${value.toFixed(1)}h`
}

function governanceReasonLabel(reason?: string): string {
  return displayLabel(t, 'governanceReason', reason)
}

function governancePhaseLabel(value?: string): string {
  return displayLabel(t, 'governancePhase', value)
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

function acceptanceStatusLabel(value?: string): string {
  return displayLabel(t, 'acceptanceStatus', value)
}

function actionVariant(action?: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
  if (action === 'rollback_to_previous_stable' || action === 'reject') return 'danger'
  if (action === 'pause_active') return 'warning'
  if (action === 'promote_to_paper') return 'success'
  if (action === 'keep_candidate') return 'info'
  return 'neutral'
}
</script>

<template>
  <div class="space-y-4">
    <Card>
      <h3 class="text-sm font-semibold">{{ t('paper.title') }}</h3>
      <p class="mt-1 text-sm text-slate-600">{{ t('paper.subtitle') }}</p>
    </Card>

    <div class="grid gap-4 xl:grid-cols-[1.5fr,1fr]">
      <Card>
        <div class="flex items-start justify-between gap-4">
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.activeStrategy') }}</p>
            <h3 class="mt-2 text-2xl font-semibold text-slate-900">{{ active?.proposal?.title ?? '--' }}</h3>
            <p class="mt-2 text-sm text-slate-600">{{ active?.proposal?.thesis ?? t('common.noData') }}</p>
            <p v-if="awaitingFirstSnapshot" class="mt-3 text-sm text-amber-700">{{ t('paper.awaitingFirstSnapshot') }}</p>
          </div>
          <Badge variant="success">{{ proposalStatusLabel(active?.proposal?.status) }}</Badge>
        </div>
      </Card>

      <Card>
        <div class="flex items-start justify-between gap-3">
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.riskPosture') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ executionPosture.label }}</p>
            <p class="mt-2 text-sm text-slate-600">{{ latestDecision?.llm_explanation ?? t('common.noData') }}</p>
          </div>
          <Badge :variant="executionPosture.variant">{{ riskActionLabel(latestDecision?.action) }}</Badge>
        </div>
      </Card>
    </div>

    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.latestEquity') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ formatCurrency(latestNav?.total_equity) }}</p>
        <p class="mt-2 text-sm text-slate-600">
          {{ t('paper.equityChange') }}: {{ formatCurrency(latestEquityChange) }}
        </p>
      </Card>

      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.cashReserve') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ formatCurrency(latestNav?.cash) }}</p>
        <p class="mt-2 text-sm text-slate-600">
          {{ t('paper.cashRatio') }}: {{ formatPercent(latestCashRatio) }}
        </p>
      </Card>

      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.grossExposure') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ formatPercent(latestGrossExposure) }}</p>
        <p class="mt-2 text-sm text-slate-600">
          {{ t('paper.positionValue') }}: {{ formatCompactCurrency(latestNav?.position_value) }}
        </p>
      </Card>

      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.fillRate') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ formatPercent(orderFillRate) }}</p>
        <p class="mt-2 text-sm text-slate-600">
          {{ t('paper.lastOrderAt') }}: {{ formatDateTime(lastOrderAt) }}
        </p>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-2">
      <Card>
        <h3 class="mb-3 text-sm font-semibold">{{ t('paper.nav') }}</h3>
        <VChart class="h-[280px] w-full" :option="navOption" autoresize />
      </Card>
      <Card>
        <h3 class="mb-3 text-sm font-semibold">{{ t('paper.positions') }}</h3>
        <VChart class="h-[280px] w-full" :option="positionOption" autoresize />
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-2">
      <Card>
        <h3 class="text-sm font-semibold">{{ t('paper.latestExecution') }}</h3>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.executionStatus') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ paperExecutionStatusLabel(latestExecution?.status) }}</p>
            <p class="mt-2 text-sm text-slate-600">{{ formatDateTime(latestExecution?.executed_at) }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.signal') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ signalLabel(latestExecution?.signal) }}</p>
            <p class="mt-2 text-sm text-slate-600">
              {{ t('paper.targetQuantity') }}: {{ latestExecution?.target_quantity ?? '--' }}
            </p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.rebalanceAction') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">
              {{ rebalanceTriggered ? orderSideLabel(latestExecution?.order_side) : t('paper.noRebalance') }}
            </p>
            <p class="mt-2 text-sm text-slate-600">
              {{ t('paper.orderQuantity') }}: {{ latestExecution?.order_quantity ?? 0 }}
            </p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.executionPrice') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatCurrency(latestExecution?.latest_price) }}</p>
            <p class="mt-2 text-sm text-slate-600">
              {{ t('paper.currentQuantity') }}: {{ latestExecution?.current_quantity ?? '--' }}
            </p>
            <p class="mt-2 text-sm text-slate-600">
              {{ t('paper.priceAsOf') }}: {{ formatDateTime(latestExecution?.latest_price_as_of) }}
            </p>
            <p class="mt-2 text-sm text-slate-600">
              {{ t('paper.priceFreshness') }}: {{ formatHours(latestExecution?.price_age_hours) }}
            </p>
          </div>
        </div>
        <div class="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
          <p class="font-medium text-slate-900">{{ t('paper.executionExplanation') }}</p>
          <p class="mt-2">{{ latestExecution?.explanation ?? t('common.noData') }}</p>
          <div class="mt-3 grid gap-2 sm:grid-cols-3">
            <p>{{ t('paper.priceChanged') }}: <span class="font-semibold text-slate-900">{{ booleanStatusLabel(priceChanged) }}</span></p>
            <p>{{ t('paper.equityMoved') }}: <span class="font-semibold text-slate-900">{{ booleanStatusLabel(equityChanged) }}</span></p>
            <p>{{ t('paper.rebalanceTriggered') }}: <span class="font-semibold text-slate-900">{{ booleanStatusLabel(latestExecution?.rebalance_triggered) }}</span></p>
          </div>
        </div>
      </Card>

      <Card>
        <h3 class="text-sm font-semibold">{{ t('paper.executionHealth') }}</h3>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.currentDrawdown') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatPercent(liveDrawdown) }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.openPositions') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ sortedPositions.length }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.pauseThreshold') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatPercent(pauseThreshold) }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.rollbackThreshold') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatPercent(rollbackThreshold) }}</p>
          </div>
        </div>
      </Card>

      <Card>
        <h3 class="text-sm font-semibold">{{ t('paper.governance') }}</h3>
        <div class="mt-3 space-y-4 text-sm">
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.latestDecision') }}</p>
            <div class="mt-2 flex flex-wrap items-center gap-2">
              <Badge :variant="actionVariant(latestDecision?.action)">{{ riskActionLabel(latestDecision?.action) }}</Badge>
              <span class="text-slate-600">{{ latestDecision?.created_at ? formatDateTime(latestDecision.created_at) : t('common.noData') }}</span>
            </div>
          </div>

          <div v-if="activeComparison">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.activeComparison') }}</p>
            <div class="mt-2 space-y-2 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p class="font-medium text-slate-900">{{ activeComparison.active_title ?? t('common.noData') }}</p>
              <p class="text-slate-600">{{ t('paper.scoreDelta') }}: {{ activeComparison.score_delta ?? '--' }}</p>
              <p class="text-slate-600">
                {{ t('paper.cooldownRemaining') }}: {{ activeComparison.cooldown_remaining_days ?? '--' }}
              </p>
            </div>
          </div>

          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.blockedReasons') }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Badge
                v-for="reason in blockedReasons"
                :key="reason"
                variant="warning"
              >
                {{ governanceReasonLabel(reason) }}
              </Badge>
              <span v-if="!blockedReasons.length" class="text-slate-600">{{ t('common.noData') }}</span>
            </div>
          </div>

          <div v-if="governanceReport?.lifecycle">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.strategyFlow') }}</p>
            <div class="mt-2 grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p class="text-slate-600">
                {{ t('paper.phase') }}:
                <span class="font-semibold text-slate-900">
                  {{ governancePhaseLabel(String(governanceReport?.lifecycle?.phase ?? 'candidate_watch')) }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.nextStep') }}:
                <span class="font-semibold text-slate-900">
                  {{ governanceNextStepLabel(String(governanceReport?.lifecycle?.next_step ?? 'monitor_candidate')) }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.reviewTrigger') }}:
                <span class="font-semibold text-slate-900">
                  {{ String(governanceReport?.lifecycle?.review_trigger ?? t('common.noData')) }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.rechallengeAllowed') }}:
                <span class="font-semibold text-slate-900">
                  {{ governanceReport?.lifecycle?.rechallenge_allowed ? t('common.yes') : t('common.no') }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.estimatedEligibility') }}:
                <span class="font-semibold text-slate-900">
                  {{
                    governanceReport?.lifecycle?.estimated_next_eligible_at
                      ? formatDateTime(String(governanceReport?.lifecycle?.estimated_next_eligible_at))
                      : lifecycleEtaKindLabel(String(governanceReport?.lifecycle?.eta_kind ?? 'unknown'))
                  }}
                </span>
              </p>
              <div v-if="Array.isArray(governanceReport?.lifecycle?.resume_conditions)">
                <p class="text-slate-600">{{ t('paper.resumeConditions') }}:</p>
                <div class="mt-2 flex flex-wrap gap-2">
                  <Badge
                    v-for="condition in governanceReport?.lifecycle?.resume_conditions ?? []"
                    :key="String(condition)"
                    variant="warning"
                  >
                    {{ resumeConditionLabel(String(condition)) }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>

          <div v-if="Object.keys(activeHealth).length || Object.keys(macroDependency).length">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.recoveryContext') }}</p>
            <div class="mt-2 grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
              <p class="text-slate-600">
                {{ t('paper.previousStable') }}:
                <span class="font-semibold text-slate-900">
                  {{ String(activeHealth.previous_stable_title ?? t('common.noData')) }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.macroDependency') }}:
                <span class="font-semibold text-slate-900">
                  {{ macroDependencyStatus ?? t('common.noData') }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.macroProvider') }}:
                <span class="font-semibold text-slate-900">
                  {{ macroDependencyProvider ?? t('common.noData') }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('command.macroFreshness') }}:
                <span class="font-semibold text-slate-900">
                  {{
                    activeMacroStatus?.freshness_hours !== undefined && activeMacroStatus?.freshness_hours !== null
                      ? `${activeMacroStatus.freshness_hours}h · ${String(activeMacroStatus?.freshness_tier ?? '--')}`
                      : t('common.noData')
                  }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('command.macroHealth30d') }}:
                <span class="font-semibold text-slate-900">
                  {{
                    activeMacroStatus?.health_score_30d !== undefined && activeMacroStatus?.health_score_30d !== null
                      ? formatPercent(Number(activeMacroStatus.health_score_30d))
                      : t('common.noData')
                  }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.macroMessage') }}:
                <span class="font-semibold text-slate-900">
                  {{ macroDependencyMessage ?? t('common.noData') }}
                </span>
              </p>
            </div>
          </div>

          <div v-if="Object.keys(operationalAcceptance).length">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.operationalAcceptance') }}</p>
            <div class="mt-2 grid gap-2 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm">
              <p class="text-slate-600">
                {{ t('command.acceptanceStatus') }}:
                <span class="font-semibold text-slate-900">
                  {{ acceptanceStatusLabel(String(operationalAcceptance.status ?? 'review_required')) }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('command.liveDays') }}:
                <span class="font-semibold text-slate-900">
                  {{ operationalAcceptance.live_days ?? t('common.noData') }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.fillRate') }}:
                <span class="font-semibold text-slate-900">
                  {{
                    operationalAcceptance.fill_rate !== undefined && operationalAcceptance.fill_rate !== null
                      ? formatPercent(Number(operationalAcceptance.fill_rate))
                      : t('common.noData')
                  }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('command.operationalScore') }}:
                <span class="font-semibold text-slate-900">
                  {{
                    operationalAcceptance.operational_score !== undefined && operationalAcceptance.operational_score !== null
                      ? formatPercent(Number(operationalAcceptance.operational_score))
                      : t('common.noData')
                  }}
                </span>
              </p>
              <p class="text-slate-600">
                {{ t('paper.incidentFreeDays') }}:
                <span class="font-semibold text-slate-900">
                  {{ operationalAcceptance.incident_free_days ?? t('common.noData') }}
                </span>
              </p>
              <div v-if="Array.isArray(operationalAcceptance.failed_checks) && operationalAcceptance.failed_checks.length">
                <p class="text-slate-600">{{ t('paper.blockedReasons') }}:</p>
                <div class="mt-2 flex flex-wrap gap-2">
                  <Badge
                    v-for="reason in operationalAcceptance.failed_checks"
                    :key="String(reason)"
                    variant="warning"
                  >
                    {{ governanceReasonLabel(String(reason)) }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>
    </div>

    <Card>
      <h3 class="text-sm font-semibold">{{ t('paper.latestOrders') }}</h3>
      <div v-if="sortedOrders.length" class="mt-3 overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="text-slate-500">
              <th class="pb-2">{{ t('common.time') }}</th>
              <th class="pb-2">{{ t('common.symbol') }}</th>
              <th class="pb-2">{{ t('common.side') }}</th>
              <th class="pb-2">{{ t('common.qty') }}</th>
              <th class="pb-2">{{ t('common.price') }}</th>
              <th class="pb-2">{{ t('paper.orderStatus') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in sortedOrders" :key="order.id" class="border-t border-slate-200">
              <td class="py-2">{{ formatDateTime(order.created_at) }}</td>
              <td class="py-2">{{ order.symbol }}</td>
              <td class="py-2">{{ orderSideLabel(order.side) }}</td>
              <td class="py-2">{{ order.quantity }}</td>
              <td class="py-2">{{ order.price.toFixed(2) }}</td>
              <td class="py-2">{{ orderStatusLabel(order.status) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <p v-else class="mt-3 text-sm text-slate-600">{{ t('paper.noOrders') }}</p>
    </Card>
  </div>
</template>
