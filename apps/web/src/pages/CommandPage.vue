<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel, localizeStrategyTitle } from '@/lib/display'

const { t } = useI18n()

const commandQuery = useQuery({
  queryKey: ['command-center'],
  queryFn: api.getCommandCenter,
  refetchInterval: 10_000,
})

const command = computed(() => commandQuery.data.value)
const slotFocus = computed(() => command.value?.slot_focus ?? null)
const paperSummary = computed(() => command.value?.paper_summary ?? null)
const paperPoolSummary = computed(() => command.value?.paper_pool_summary ?? null)
const paperPoolSlots = computed(() => command.value?.paper_pool?.slots ?? [])
const liveReadiness = computed(() => command.value?.live_readiness ?? null)
const runtimeStatus = computed(() => command.value?.runtime_status ?? null)
const llmStatus = computed(() => command.value?.llm_status ?? null)

const focusLink = computed(() => {
  if (!slotFocus.value?.proposal_id) return null
  return slotFocus.value.mode === 'active' ? '/paper/detail' : `/candidates/${slotFocus.value.proposal_id}`
})

const topBlockers = computed(() => {
  const blockers = [
    ...(slotFocus.value?.candidate_gate?.blocked_reasons ?? []),
    ...(slotFocus.value?.promotion_gate?.blocked_reasons ?? []),
    ...(liveReadiness.value?.blockers ?? []),
  ]
  return Array.from(new Set(blockers)).slice(0, 3)
})

const headline = computed(() => {
  if (!slotFocus.value) return '当前席位主角'
  if (slotFocus.value.mode === 'active') return '当前席位主角'
  if (slotFocus.value.mode === 'challenger') return '当前席位候选主角'
  return '当前席位为空'
})

const slotModeLabel = computed(() => {
  if (!slotFocus.value) return '--'
  if (slotFocus.value.mode === 'active') return '已上模拟盘'
  if (slotFocus.value.mode === 'challenger') return '待上模拟盘'
  return '暂无主角'
})

function governanceReasonLabel(value?: string | null): string {
  return displayLabel(t, 'governanceReason', value)
}

function governanceNextStepLabel(value?: string | null): string {
  return displayLabel(t, 'governanceNextStep', value)
}

function liveReadinessStatusLabel(value?: string | null): string {
  return displayLabel(t, 'liveReadinessStatus', value)
}

const slotStageLabel = computed(() => {
  const stage = slotFocus.value?.stage
  return stage ? displayLabel(t, 'pipelineStage', stage) : '--'
})

const nextStepLabel = computed(() => {
  const step = slotFocus.value?.next_step
  return step ? governanceNextStepLabel(step) : '等待下一轮判断'
})

const primaryBlockerLabel = computed(() => {
  const blocker = slotFocus.value?.primary_blocker
  return blocker ? governanceReasonLabel(blocker) : '暂无明确阻断'
})

const slotStrategyTitle = computed(() => {
  return localizeStrategyTitle(slotFocus.value?.strategy_title, 'zh-CN')
})

const liveReadinessSummary = computed(() => {
  if (!liveReadiness.value) return '暂无实盘准备判断。'
  return `${liveReadinessStatusLabel(liveReadiness.value.status)} · 准入分 ${liveReadiness.value.score}`
})

const paperStatusLabel = computed(() => {
  const status = paperSummary.value?.latest_execution_status
  if (!status) return '暂无执行'
  if (status === 'executed') return '已执行'
  if (status === 'skipped') return '已跳过'
  return status
})

const strongestChallenger = computed(() =>
  paperPoolSlots.value.find((item) => item.slot_id === paperPoolSummary.value?.strongest_challenger_slot_id) ?? null,
)

const money = new Intl.NumberFormat('en-US', {
  style: 'currency',
  currency: 'HKD',
  maximumFractionDigits: 0,
})

function badgeVariant(ok?: boolean, hasData = true): 'success' | 'warning' | 'neutral' {
  if (!hasData) return 'neutral'
  return ok ? 'success' : 'warning'
}

function formatMoney(value?: number | null): string {
  if (value === undefined || value === null) return '--'
  return money.format(value)
}

function formatDelta(value?: number | null): string {
  if (value === undefined || value === null) return '--'
  const prefix = value > 0 ? '+' : ''
  return `${prefix}${money.format(value)}`
}
</script>

<template>
  <div class="space-y-4">
    <Card class="border border-slate-200/80 bg-slate-50/80">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">Slot Cockpit</p>
          <h2 class="mt-2 text-xl font-semibold text-slate-900">实盘准备驾驶舱</h2>
          <p class="mt-2 text-sm text-slate-600">
            首页只看最接近实盘的席位主角、当前阻断、下一步和模拟盘摘要。
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <RouterLink to="/candidates" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50">候选池</RouterLink>
          <RouterLink to="/research" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50">研究台</RouterLink>
          <RouterLink to="/paper" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50">模拟盘</RouterLink>
          <RouterLink to="/runtime" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50">运行详情</RouterLink>
        </div>
      </div>
    </Card>

    <div class="grid gap-4 xl:grid-cols-[1.4fr,0.9fr]">
      <Card class="border border-slate-200/80 bg-white">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="text-xs uppercase tracking-[0.18em] text-slate-500">{{ headline }}</p>
              <h3 class="mt-2 text-2xl font-semibold text-slate-900">{{ slotStrategyTitle ?? '暂无可上盘策略' }}</h3>
            <p class="mt-2 text-sm text-slate-600">
              标的：<span class="font-semibold text-slate-900">{{ slotFocus?.symbol ?? '--' }}</span>
              · 当前阶段：<span class="font-semibold text-slate-900">{{ slotStageLabel }}</span>
            </p>
          </div>
          <Badge :variant="slotFocus?.mode === 'active' ? 'success' : slotFocus?.mode === 'challenger' ? 'warning' : 'neutral'">
            {{ slotModeLabel }}
          </Badge>
        </div>

        <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <div class="rounded-lg border border-slate-200/80 bg-slate-50/70 px-3 py-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">候选门禁</p>
            <div class="mt-2 flex items-center gap-2">
              <Badge :variant="badgeVariant(slotFocus?.candidate_gate?.eligible, !!slotFocus)">
                {{ slotFocus?.candidate_gate?.eligible ? '可保留候选' : '未过候选门禁' }}
              </Badge>
            </div>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50/70 px-3 py-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">模拟盘门禁</p>
            <div class="mt-2 flex items-center gap-2">
              <Badge :variant="badgeVariant(slotFocus?.promotion_gate?.eligible, !!slotFocus)">
                {{ slotFocus?.promotion_gate?.eligible ? '可上模拟盘' : '暂不能上模拟盘' }}
              </Badge>
            </div>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50/70 px-3 py-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">当前最主要阻断</p>
            <p class="mt-2 text-sm font-semibold text-slate-900">{{ primaryBlockerLabel }}</p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50/70 px-3 py-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">下一步</p>
            <p class="mt-2 text-sm font-semibold text-slate-900">{{ nextStepLabel }}</p>
          </div>
        </div>

        <div class="mt-4 rounded-xl border border-slate-200/80 bg-slate-50/70 px-4 py-4">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">席位判断</p>
          <p class="mt-2 text-sm text-slate-700">{{ liveReadinessSummary }}</p>
        </div>

        <div class="mt-4 flex flex-wrap gap-2">
          <RouterLink
            v-if="focusLink"
            :to="focusLink"
            class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50"
          >
            查看主角详情
          </RouterLink>
          <RouterLink to="/audit" class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50">查看审计证据</RouterLink>
        </div>
      </Card>

      <div class="space-y-4">
        <Card class="border border-amber-200 bg-amber-50/70">
          <p class="text-xs uppercase tracking-[0.18em] text-amber-700">关键阻断</p>
          <div class="mt-3 space-y-2">
            <div
              v-for="item in topBlockers.length ? topBlockers : ['暂无明确阻断']"
              :key="item"
              class="rounded-lg border border-amber-200/80 bg-white px-3 py-3 text-sm text-slate-800"
            >
              {{ governanceReasonLabel(item) }}
            </div>
          </div>
        </Card>

        <Card class="border border-slate-200/80 bg-white">
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">下一步</p>
          <h3 class="mt-2 text-lg font-semibold text-slate-900">{{ nextStepLabel }}</h3>
          <p class="mt-2 text-sm text-slate-600">
            当前运行：{{ displayLabel(t, 'runtimeState', runtimeStatus?.current_state) }}
            · 模型：{{ llmStatus?.provider ?? '--' }} / {{ llmStatus?.model ?? '--' }}
          </p>
        </Card>

        <Card class="border border-emerald-200/80 bg-emerald-50/70">
          <p class="text-xs uppercase tracking-[0.18em] text-emerald-700">模拟盘摘要</p>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <div class="rounded-lg border border-emerald-200/80 bg-white px-3 py-3">
              <p class="text-xs uppercase tracking-widest text-emerald-700">最新权益</p>
              <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatMoney(paperSummary?.total_equity) }}</p>
            </div>
            <div class="rounded-lg border border-emerald-200/80 bg-white px-3 py-3">
              <p class="text-xs uppercase tracking-widest text-emerald-700">较上一笔净值变化</p>
              <p class="mt-2 text-lg font-semibold text-slate-900">{{ formatDelta(paperSummary?.latest_nav_change) }}</p>
            </div>
            <div class="rounded-lg border border-emerald-200/80 bg-white px-3 py-3">
              <p class="text-xs uppercase tracking-widest text-emerald-700">当前持仓数</p>
              <p class="mt-2 text-lg font-semibold text-slate-900">{{ paperSummary?.position_count ?? 0 }}</p>
            </div>
            <div class="rounded-lg border border-emerald-200/80 bg-white px-3 py-3">
              <p class="text-xs uppercase tracking-widest text-emerald-700">最新执行状态</p>
              <p class="mt-2 text-lg font-semibold text-slate-900">{{ paperStatusLabel }}</p>
            </div>
          </div>
          <div class="mt-4 rounded-lg border border-emerald-200/80 bg-white px-3 py-3 text-sm text-slate-700">
            {{ paperSummary?.latest_execution_explanation ?? '当前暂无新的模拟盘执行说明。' }}
          </div>
        </Card>

        <Card class="border border-sky-200/80 bg-sky-50/70">
          <p class="text-xs uppercase tracking-[0.18em] text-sky-700">Paper Pool</p>
          <div class="mt-4 grid gap-3 sm:grid-cols-2">
            <div class="rounded-lg border border-sky-200/80 bg-white px-3 py-3">
              <p class="text-xs uppercase tracking-widest text-sky-700">已占用席位</p>
              <p class="mt-2 text-lg font-semibold text-slate-900">
                {{ paperPoolSummary?.occupied_slot_count ?? 0 }} / {{ paperPoolSummary?.slot_count ?? 0 }}
              </p>
            </div>
            <div class="rounded-lg border border-sky-200/80 bg-white px-3 py-3">
              <p class="text-xs uppercase tracking-widest text-sky-700">Challenger 数</p>
              <p class="mt-2 text-lg font-semibold text-slate-900">{{ paperPoolSummary?.challenger_count ?? 0 }}</p>
            </div>
          </div>
          <div class="mt-4 rounded-lg border border-sky-200/80 bg-white px-3 py-3 text-sm text-slate-700">
            <template v-if="strongestChallenger?.proposal">
              最强 challenger：{{ localizeStrategyTitle(strongestChallenger.proposal.title, 'zh-CN') }}
              · {{ strongestChallenger.proposal.symbol }}
              · 分差 {{ paperPoolSummary?.primary_vs_strongest_score_delta ?? '--' }}
            </template>
            <template v-else>
              当前 challenger 席位尚未形成有效候选。
            </template>
          </div>
        </Card>
      </div>
    </div>
  </div>
</template>
