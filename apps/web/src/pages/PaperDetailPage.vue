<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { use } from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import VChart from 'vue-echarts'
import { RouterLink } from 'vue-router'

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

const latestNav = computed(() => sortedNavRows.value[sortedNavRows.value.length - 1] ?? null)

const latestGrossExposure = computed(() => {
  if (!latestNav.value || latestNav.value.total_equity <= 0) return null
  return latestNav.value.position_value / latestNav.value.total_equity
})

const liveDrawdown = computed(() => {
  let peak = 0
  let maxDrawdown = 0
  for (const row of sortedNavRows.value) {
    peak = Math.max(peak, row.total_equity)
    if (peak > 0) maxDrawdown = Math.max(maxDrawdown, (peak - row.total_equity) / peak)
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
      currency: 'HKD',
      maximumFractionDigits: 0,
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
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="text-sm font-semibold">{{ t('paper.detailTitle') }}</h3>
          <p class="mt-1 text-sm text-slate-600">{{ t('paper.detailSubtitle') }}</p>
        </div>
        <RouterLink to="/paper" class="text-sm font-medium text-teal-700 underline-offset-2 hover:underline">
          {{ t('paper.backToSummary') }}
        </RouterLink>
      </div>
    </Card>

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
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ latestExecution?.signal ?? '--' }}</p>
            <p class="mt-2 text-sm text-slate-600">{{ t('paper.targetQuantity') }}: {{ latestExecution?.target_quantity ?? '--' }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.rebalanceAction') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">
              {{ (latestExecution?.order_quantity ?? 0) > 0 ? orderSideLabel(latestExecution?.order_side) : t('paper.noRebalance') }}
            </p>
            <p class="mt-2 text-sm text-slate-600">{{ t('paper.orderQuantity') }}: {{ latestExecution?.order_quantity ?? 0 }}</p>
          </div>
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.executionPrice') }}</p>
            <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatCurrency(latestExecution?.latest_price) }}</p>
            <p class="mt-2 text-sm text-slate-600">{{ t('paper.currentQuantity') }}: {{ latestExecution?.current_quantity ?? '--' }}</p>
            <p class="mt-2 text-sm text-slate-600">{{ t('paper.priceAsOf') }}: {{ formatDateTime(latestExecution?.latest_price_as_of) }}</p>
          </div>
        </div>
        <div class="mt-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600">
          <p class="font-medium text-slate-900">{{ t('paper.executionExplanation') }}</p>
          <p class="mt-2">{{ latestExecution?.explanation ?? t('common.noData') }}</p>
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
    </div>

    <div class="grid gap-4 xl:grid-cols-2">
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

          <div v-if="activeComparison" class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.activeComparison') }}</p>
            <p class="mt-2 font-medium text-slate-900">{{ activeComparison.active_title ?? t('common.noData') }}</p>
            <p class="mt-2 text-slate-600">{{ t('paper.scoreDelta') }}: {{ activeComparison.score_delta ?? '--' }}</p>
            <p class="mt-2 text-slate-600">{{ t('paper.cooldownRemaining') }}: {{ activeComparison.cooldown_remaining_days ?? '--' }}</p>
          </div>

          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('paper.blockedReasons') }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Badge v-for="reason in blockedReasons" :key="reason" variant="warning">
                {{ governanceReasonLabel(reason) }}
              </Badge>
              <span v-if="!blockedReasons.length" class="text-slate-600">{{ t('common.noData') }}</span>
            </div>
          </div>

          <div v-if="governanceReport?.lifecycle" class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.strategyFlow') }}</p>
            <div class="mt-2 grid gap-2">
              <p class="text-slate-600">{{ t('paper.phase') }}: <span class="font-semibold text-slate-900">{{ governancePhaseLabel(String(governanceReport?.lifecycle?.phase ?? 'candidate_watch')) }}</span></p>
              <p class="text-slate-600">{{ t('paper.nextStep') }}: <span class="font-semibold text-slate-900">{{ governanceNextStepLabel(String(governanceReport?.lifecycle?.next_step ?? 'monitor_candidate')) }}</span></p>
              <p class="text-slate-600">{{ t('paper.reviewTrigger') }}: <span class="font-semibold text-slate-900">{{ String(governanceReport?.lifecycle?.review_trigger ?? t('common.noData')) }}</span></p>
              <p class="text-slate-600">{{ t('paper.estimatedEligibility') }}: <span class="font-semibold text-slate-900">{{ governanceReport?.lifecycle?.estimated_next_eligible_at ? formatDateTime(String(governanceReport?.lifecycle?.estimated_next_eligible_at)) : lifecycleEtaKindLabel(String(governanceReport?.lifecycle?.eta_kind ?? 'unknown')) }}</span></p>
              <div v-if="Array.isArray(governanceReport?.lifecycle?.resume_conditions)">
                <p class="text-slate-600">{{ t('paper.resumeConditions') }}:</p>
                <div class="mt-2 flex flex-wrap gap-2">
                  <Badge v-for="condition in governanceReport?.lifecycle?.resume_conditions ?? []" :key="String(condition)" variant="warning">
                    {{ resumeConditionLabel(String(condition)) }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <h3 class="text-sm font-semibold">{{ t('paper.recoveryContext') }}</h3>
        <div class="mt-3 space-y-4 text-sm">
          <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-slate-600">{{ t('paper.previousStable') }}: <span class="font-semibold text-slate-900">{{ String(activeHealth.previous_stable_title ?? t('common.noData')) }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('paper.macroDependency') }}: <span class="font-semibold text-slate-900">{{ macroDependencyStatus ?? t('common.noData') }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('paper.macroProvider') }}: <span class="font-semibold text-slate-900">{{ macroDependencyProvider ?? t('common.noData') }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('paper.macroMessage') }}: <span class="font-semibold text-slate-900">{{ macroDependencyMessage ?? t('common.noData') }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('paper.positionValue') }}: <span class="font-semibold text-slate-900">{{ formatCurrency(latestNav?.position_value) }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('paper.grossExposure') }}: <span class="font-semibold text-slate-900">{{ formatPercent(latestGrossExposure) }}</span></p>
          </div>

          <div v-if="Object.keys(operationalAcceptance).length" class="rounded-2xl border border-slate-200 bg-slate-50 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('command.operationalAcceptance') }}</p>
            <p class="mt-2 text-slate-600">{{ t('command.acceptanceStatus') }}: <span class="font-semibold text-slate-900">{{ acceptanceStatusLabel(String(operationalAcceptance.status ?? 'review_required')) }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('command.liveDays') }}: <span class="font-semibold text-slate-900">{{ operationalAcceptance.live_days ?? t('common.noData') }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('paper.fillRate') }}: <span class="font-semibold text-slate-900">{{ operationalAcceptance.fill_rate !== undefined && operationalAcceptance.fill_rate !== null ? formatPercent(Number(operationalAcceptance.fill_rate)) : t('common.noData') }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('command.operationalScore') }}: <span class="font-semibold text-slate-900">{{ operationalAcceptance.operational_score !== undefined && operationalAcceptance.operational_score !== null ? formatPercent(Number(operationalAcceptance.operational_score)) : t('common.noData') }}</span></p>
            <p class="mt-2 text-slate-600">{{ t('paper.incidentFreeDays') }}: <span class="font-semibold text-slate-900">{{ operationalAcceptance.incident_free_days ?? t('common.noData') }}</span></p>
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
