<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink } from 'vue-router'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel, humanizeLabel, term } from '@/lib/display'

const { t } = useI18n()

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

const command = computed(() => commandQuery.data.value)
const candidates = computed(() => candidatesQuery.data.value ?? [])
const acceptanceReport = computed(() => acceptanceReportQuery.data.value)
const runtimeStatus = computed(() => command.value?.runtime_status ?? null)
const liveReadiness = computed(() => command.value?.live_readiness ?? null)
const latestDecision = computed(() => command.value?.latest_risk_decision ?? null)
const latestPaperExecution = computed(() => command.value?.active_strategy.paper_trading.latest_execution ?? null)
const macroStatus = computed(() => command.value?.market_snapshot.macro_status ?? null)
const universeSelection = computed(() => command.value?.market_snapshot.universe_selection ?? null)
const activeProposal = computed(() => command.value?.active_strategy.proposal ?? null)
const providerMigration = computed(() => command.value?.provider_migration ?? null)
const activeKnowledgeFamilies = computed<string[]>(() => {
  const families = activeProposal.value?.evidence_pack?.quality_report?.knowledge_families_used
  return Array.isArray(families) ? families.map((item) => String(item)) : []
})

const operationalAcceptance = computed(
  () => (command.value?.active_strategy.operational_acceptance as Record<string, unknown> | undefined) ?? {},
)
const paperTrading = computed(() => command.value?.active_strategy.paper_trading ?? null)
const paperStatusSummary = computed(() => {
  const trading = paperTrading.value
  if (!trading) return null
  const orders = Array.isArray(trading.orders) ? trading.orders.length : 0
  const positions = Array.isArray(trading.positions) ? trading.positions.length : 0
  const navPoints = Array.isArray(trading.nav) ? trading.nav.length : 0
  const latestStatus = latestPaperExecution.value?.status
  const isActive = Boolean(activeProposal.value && (orders > 0 || positions > 0 || navPoints > 0))
  return {
    isActive,
    orders,
    positions,
    navPoints,
    latestStatus: paperExecutionStatusLabel(latestStatus),
    explanation: latestPaperExecution.value?.explanation ?? '--',
  }
})

const isSampleMode = computed(() => {
  if (!command.value) return false
  const sourceKind = command.value.active_strategy.proposal?.source_kind
  const llmStatus = command.value.llm_status
  const llmMock = llmStatus?.provider === 'mock' || llmStatus?.status === 'mock' || !!llmStatus?.using_mock_fallback
  const macroDegraded = macroStatus.value?.degraded === true || macroStatus.value?.status === 'degraded'
  return sourceKind === 'mock' || llmMock || macroDegraded
})

const executiveSummary = computed(() => {
  if (!command.value) return null
  const selectedSymbol = universeSelection.value?.selected_symbol ?? '--'
  const activeTitle = activeProposal.value?.title ?? '--'
  const readinessStatus = liveReadiness.value?.status ?? 'not_ready'
  const blockers = liveReadiness.value?.blockers ?? []
  const nextActions = liveReadiness.value?.next_actions ?? []
  const selectionReason = universeSelection.value?.selection_reason
  const executionExplanation = latestPaperExecution.value?.explanation
  const governanceNextStep = latestDecision.value?.evidence_pack?.governance_report?.lifecycle?.next_step

  let conclusionKey = 'executiveConclusion_not_ready'
  if (readinessStatus === 'ready_candidate') conclusionKey = 'executiveConclusion_ready_candidate'
  else if (readinessStatus === 'paper_building_evidence') conclusionKey = 'executiveConclusion_paper_building_evidence'

  const reasons: string[] = []
  if (selectionReason) reasons.push(`${t('command.executiveReason_selectedSymbol')}: ${selectedSymbol} - ${selectionReason}`)
  else reasons.push(`${t('command.executiveReason_selectedSymbol')}: ${selectedSymbol}`)

  if (activeKnowledgeFamilies.value.length > 0) {
    reasons.push(`${t('command.executiveReason_strategyMethod')}: ${activeKnowledgeFamilies.value.map((item) => knowledgeFamilyLabel(item)).join(' / ')}`)
  }

  if (executionExplanation) reasons.push(`${t('command.executiveReason_execution')}: ${executionExplanation}`)
  else if (latestPaperExecution.value) reasons.push(`${t('command.executiveReason_execution')}: ${paperExecutionStatusLabel(latestPaperExecution.value.status)}`)

  if (blockers.length > 0) reasons.push(`${t('command.executiveReason_blocker')}: ${humanizeLabel(blockers[0])}`)
  else if (liveReadiness.value?.summary) reasons.push(`${t('command.executiveReason_readiness')}: ${liveReadiness.value.summary}`)

  const nextStep = nextActions[0]
    ? humanizeLabel(nextActions[0])
    : governanceNextStep
      ? governanceNextStepLabel(String(governanceNextStep))
      : runtimeStatus.value?.current_state === 'running'
        ? pipelineStageLabel(runtimeStatus.value?.current_stage)
        : t('common.noData')

  return {
    selectedSymbol,
    activeTitle,
    conclusion: t(`command.${conclusionKey}`),
    reasons: reasons.slice(0, 3),
    nextStep,
  }
})

type BoardStatus = 'completed' | 'current' | 'pending' | 'attention'
type BoardStageId =
  | 'universe_selection'
  | 'market_analysis'
  | 'strategy_generation'
  | 'research_review'
  | 'backtest_admission'
  | 'governance_decision'
  | 'paper_trading'
  | 'live_readiness'

type StageView = {
  id: BoardStageId
  title: string
  subtitle: string
  status: BoardStatus
  summary: string
  evidence: Array<{ label: string; value: string }>
}

const TECH_TO_BUSINESS_STAGE: Record<string, BoardStageId> = {
  select_universe: 'universe_selection',
  sync_event_stream: 'market_analysis',
  sync_daily_event_digests: 'market_analysis',
  build_market_snapshot: 'market_analysis',
  market_analyst: 'market_analysis',
  strategy_agent: 'strategy_generation',
  materialize_decisions: 'governance_decision',
  paper_execution: 'paper_trading',
  active_health_check: 'live_readiness',
}

const currentBoardStageId = computed<BoardStageId | null>(() => {
  const runtimeStage = runtimeStatus.value?.current_stage
  if (!runtimeStage) return null
  return TECH_TO_BUSINESS_STAGE[runtimeStage] ?? null
})

const stageViews = computed<StageView[]>(() => {
  const selectedSymbol = universeSelection.value?.selected_symbol
  const hasMarketSummary = Boolean(command.value?.market_snapshot.summary)
  const hasStrategy = Boolean(activeProposal.value || candidates.value.length)
  const hasDecision = Boolean(latestDecision.value)
  const backtestGate = latestDecision.value?.evidence_pack?.quality_report?.backtest_gate
  const backtestReview = (backtestGate?.review as Record<string, unknown> | undefined) ?? {}
  const hardGateFailures = Array.isArray(backtestReview.hard_gates_failed)
    ? backtestReview.hard_gates_failed.map((item) => String(item))
    : []
  const backtestAvailable = Boolean(backtestGate?.available)
  const backtestEligible = Boolean(backtestGate?.eligible_for_paper)
  const hasPaperEvidence = Boolean(latestPaperExecution.value)
  const hasReadiness = Boolean(liveReadiness.value)
  const decisionAction = latestDecision.value?.action
  const governancePhase = latestDecision.value?.evidence_pack?.governance_report?.lifecycle?.phase
  const governanceNext = latestDecision.value?.evidence_pack?.governance_report?.lifecycle?.next_step
  const runtimeAttention = Boolean(
    runtimeStatus.value?.current_state === 'failed' ||
    runtimeStatus.value?.current_state === 'stalled' ||
    runtimeStatus.value?.current_state === 'degraded' ||
    runtimeStatus.value?.degraded ||
    runtimeStatus.value?.stalled,
  )
  const macroAttention = Boolean(macroStatus.value?.degraded)
  const readinessAttention = (liveReadiness.value?.blockers?.length ?? 0) > 0 || liveReadiness.value?.status === 'not_ready'

  const completionById: Record<BoardStageId, boolean> = {
    universe_selection: Boolean(selectedSymbol),
    market_analysis: hasMarketSummary,
    strategy_generation: hasStrategy,
    research_review: hasDecision,
    backtest_admission: hasDecision && (!backtestAvailable || backtestEligible),
    governance_decision: hasDecision,
    paper_trading: hasPaperEvidence || Boolean(activeProposal.value),
    live_readiness: hasReadiness,
  }

  const attentionById: Record<BoardStageId, boolean> = {
    universe_selection: !selectedSymbol,
    market_analysis: macroAttention,
    strategy_generation: runtimeAttention && runtimeStatus.value?.current_stage === 'strategy_agent',
    research_review: runtimeAttention && runtimeStatus.value?.current_stage === 'materialize_decisions',
    backtest_admission: hasDecision && backtestAvailable && !backtestEligible,
    governance_decision: decisionAction === 'reject' || decisionAction === 'pause_active' || decisionAction === 'rollback_to_previous_stable',
    paper_trading: runtimeAttention && runtimeStatus.value?.current_stage === 'paper_execution',
    live_readiness: readinessAttention || runtimeAttention,
  }

  const resolveStatus = (id: BoardStageId): BoardStatus => {
    if (attentionById[id]) return 'attention'
    if (currentBoardStageId.value === id) return 'current'
    if (completionById[id]) return 'completed'
    return 'pending'
  }

  return [
    {
      id: 'universe_selection',
      title: term('Universe Selection'),
      subtitle: term('Select universe and symbol'),
      status: resolveStatus('universe_selection'),
      summary: selectedSymbol
        ? `${term('Selected Symbol')}: ${selectedSymbol}`
        : t('common.noData'),
      evidence: [
        { label: term('Selected Symbol'), value: selectedSymbol ?? '--' },
        { label: term('Selection Reason'), value: universeSelection.value?.selection_reason ?? '--' },
        { label: term('Candidate Count'), value: String(universeSelection.value?.candidate_count ?? 0) },
      ],
    },
    {
      id: 'market_analysis',
      title: term('Market Analysis'),
      subtitle: term('Digest macro context and market profile'),
      status: resolveStatus('market_analysis'),
      summary: macroStatus.value?.message ?? command.value?.market_snapshot.summary ?? t('common.noData'),
      evidence: [
        { label: term('Macro Pipeline'), value: llmStatusLabel(macroStatus.value?.status) },
        { label: term('Active Provider'), value: macroStatus.value?.active_provider ?? '--' },
        {
          label: term('Reliability'),
          value:
            macroStatus.value?.reliability_score !== null && macroStatus.value?.reliability_score !== undefined
              ? `${Math.round(macroStatus.value.reliability_score * 100)}%`
              : '--',
        },
      ],
    },
    {
      id: 'strategy_generation',
      title: term('Strategy Generation'),
      subtitle: term('Generate candidate proposals'),
      status: resolveStatus('strategy_generation'),
      summary: `${term('Candidate Count')}: ${candidates.value.length}`,
      evidence: [
        { label: term('Active Strategy'), value: activeProposal.value?.title ?? '--' },
        { label: term('Candidate Count'), value: String(candidates.value.length) },
        { label: term('Provider'), value: command.value?.llm_status.provider ?? '--' },
      ],
    },
    {
      id: 'research_review',
      title: term('Research Review'),
      subtitle: term('Debate and risk scoring review'),
      status: resolveStatus('research_review'),
      summary: latestDecision.value?.llm_explanation ?? t('common.noData'),
      evidence: [
        {
          label: term('Final Score'),
          value: latestDecision.value?.final_score !== undefined ? latestDecision.value.final_score.toFixed(1) : '--',
        },
        {
          label: term('Risk Action'),
          value: riskActionLabel(latestDecision.value?.action),
        },
        {
          label: term('Governance Phase'),
          value: governancePhaseLabel(String(governancePhase ?? 'candidate_watch')),
        },
        {
          label: term('Knowledge Fit'),
          value: knowledgeFitLabel(latestDecision.value?.evidence_pack?.quality_report?.knowledge_fit_assessment),
        },
      ],
    },
    {
      id: 'backtest_admission',
      title: term('Backtest Admission'),
      subtitle: term('Pre-paper quality gate'),
      status: resolveStatus('backtest_admission'),
      summary: backtestGate?.summary ?? t('common.noData'),
      evidence: [
        { label: term('Gate Available'), value: yesNoLabel(backtestGate?.available) },
        { label: term('Eligible For Paper'), value: yesNoLabel(backtestGate?.eligible_for_paper) },
        {
          label: term('Blocked Reasons'),
          value: (backtestGate?.blocked_reasons ?? []).length
            ? (backtestGate?.blocked_reasons ?? []).map((item) => humanizeLabel(item)).join(' | ')
            : '--',
        },
        {
          label: term('Hard Gate Failures'),
          value: hardGateFailures.length ? hardGateFailures.join(' | ') : '--',
        },
      ],
    },
    {
      id: 'governance_decision',
      title: term('Governance Decision'),
      subtitle: term('Lifecycle and promotion decision'),
      status: resolveStatus('governance_decision'),
      summary: governanceNext ? governanceNextStepLabel(String(governanceNext)) : t('common.noData'),
      evidence: [
        { label: term('Decision Action'), value: riskActionLabel(latestDecision.value?.action) },
        { label: term('Current Phase'), value: governancePhaseLabel(String(governancePhase ?? 'candidate_watch')) },
        { label: term('Next Step'), value: governanceNext ? governanceNextStepLabel(String(governanceNext)) : '--' },
      ],
    },
    {
      id: 'paper_trading',
      title: term('Paper Trading'),
      subtitle: term('Execution evidence in simulated market'),
      status: resolveStatus('paper_trading'),
      summary: latestPaperExecution.value?.explanation ?? t('common.noData'),
      evidence: [
        { label: term('Execution Status'), value: paperExecutionStatusLabel(latestPaperExecution.value?.status) },
        { label: term('Signal'), value: latestPaperExecution.value?.signal ?? '--' },
        {
          label: term('Target Quantity'),
          value:
            latestPaperExecution.value?.target_quantity !== undefined && latestPaperExecution.value?.target_quantity !== null
              ? String(latestPaperExecution.value.target_quantity)
              : '--',
        },
      ],
    },
    {
      id: 'live_readiness',
      title: term('Live Readiness'),
      subtitle: term('Readiness evidence, not auto-live switch'),
      status: resolveStatus('live_readiness'),
      summary: liveReadiness.value?.summary ?? t('common.noData'),
      evidence: [
        { label: term('Readiness Status'), value: liveReadinessStatusLabel(liveReadiness.value?.status) },
        {
          label: term('Readiness Score'),
          value: liveReadiness.value?.score !== undefined ? String(liveReadiness.value.score) : '--',
        },
        {
          label: term('Blockers'),
          value: (liveReadiness.value?.blockers ?? []).length
            ? (liveReadiness.value?.blockers ?? []).map((item) => humanizeLabel(item)).join(' | ')
            : '--',
        },
      ],
    },
  ]
})

const defaultOpenStageId = computed<BoardStageId | null>(() => {
  const attention = stageViews.value.find((item) => item.status === 'attention')
  if (attention) return attention.id
  const current = stageViews.value.find((item) => item.status === 'current')
  if (current) return current.id
  return stageViews.value[0]?.id ?? null
})

function llmStatusLabel(status?: string): string {
  return displayLabel(t, 'llmStatus', status)
}

function riskActionLabel(action?: string): string {
  return displayLabel(t, 'riskAction', action)
}

function governancePhaseLabel(value?: string): string {
  return displayLabel(t, 'governancePhase', value)
}

function governanceNextStepLabel(value?: string): string {
  return displayLabel(t, 'governanceNextStep', value)
}

function pipelineStageLabel(value?: string): string {
  return displayLabel(t, 'pipelineStage', value)
}

function liveReadinessStatusLabel(value?: string): string {
  return displayLabel(t, 'liveReadinessStatus', value)
}

function knowledgeFamilyLabel(value?: string): string {
  return displayLabel(t, 'knowledgeFamily', value)
}

function knowledgeFitLabel(value?: string): string {
  return displayLabel(t, 'knowledgeFit', value)
}

function paperExecutionStatusLabel(status?: string): string {
  return status === 'executed' ? term('Executed') : status === 'skipped' ? term('Skipped') : '--'
}

function yesNoLabel(value?: boolean): string {
  if (value === undefined || value === null) return '--'
  return value ? t('common.yes') : t('common.no')
}

function statusVariant(value: BoardStatus): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (value === 'completed') return 'success'
  if (value === 'current') return 'info'
  if (value === 'attention') return 'warning'
  return 'neutral'
}

function statusLabel(value: BoardStatus): string {
  if (value === 'completed') return term('Completed')
  if (value === 'current') return term('Current')
  if (value === 'attention') return term('Attention')
  return term('Pending')
}
</script>

<template>
  <div class="space-y-4">
    <Card class="border border-slate-200/80 bg-slate-50/80">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-xs uppercase tracking-[0.18em] text-slate-500">{{ term('Pipeline Review Board') }}</p>
          <h2 class="mt-2 text-xl font-semibold text-slate-900">{{ term('Executive Summary') }}</h2>
          <p class="mt-2 text-sm text-slate-600">
            {{ t('command.guideSubtitle') }}
          </p>
        </div>
        <RouterLink
          to="/runtime"
          class="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-50"
        >
          {{ term('Open Runtime Detail') }}
        </RouterLink>
      </div>
    </Card>

    <Card v-if="executiveSummary" class="border border-slate-200/80 bg-white">
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 class="text-lg font-semibold text-slate-900">{{ executiveSummary.conclusion }}</h3>
          <p class="mt-2 text-sm text-slate-600">
            {{ term('Selected Symbol') }}: <span class="font-semibold text-slate-900">{{ executiveSummary.selectedSymbol }}</span>
            · {{ term('Active Strategy') }}: <span class="font-semibold text-slate-900">{{ executiveSummary.activeTitle }}</span>
          </p>
        </div>
        <Badge :variant="liveReadiness?.status === 'ready_candidate' ? 'success' : liveReadiness?.status === 'paper_building_evidence' ? 'info' : 'warning'">
          {{ liveReadinessStatusLabel(liveReadiness?.status) }}
        </Badge>
      </div>
      <div class="mt-4 grid gap-4 xl:grid-cols-[1.4fr,0.8fr]">
        <div>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ term('Three Key Reasons') }}</p>
          <ul class="mt-2 space-y-2 text-sm text-slate-700">
            <li v-for="reason in executiveSummary.reasons" :key="reason" class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2">{{ reason }}</li>
          </ul>
        </div>
        <div>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ term('Next Step') }}</p>
          <div class="mt-2 rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-3 text-sm text-slate-700">
            {{ executiveSummary.nextStep }}
          </div>
        </div>
      </div>
    </Card>

    <Card v-if="paperStatusSummary" class="border border-emerald-200/80 bg-emerald-50/70">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p class="text-xs uppercase tracking-widest text-emerald-700">{{ t('command.paperStatusTitle') }}</p>
          <h3 class="mt-1 text-base font-semibold text-emerald-950">
            {{ paperStatusSummary.isActive ? t('command.paperStatusActive') : t('command.paperStatusInactive') }}
          </h3>
          <p class="mt-2 text-sm text-emerald-900">{{ paperStatusSummary.explanation }}</p>
        </div>
        <Badge :variant="paperStatusSummary.isActive ? 'success' : 'warning'">
          {{ paperStatusSummary.latestStatus }}
        </Badge>
      </div>
      <div class="mt-4 grid gap-2 text-sm sm:grid-cols-3">
        <div class="rounded-lg border border-emerald-200/80 bg-white px-3 py-2">
          <p class="text-emerald-700">{{ t('command.paperOrders') }}</p>
          <p class="mt-1 font-semibold text-slate-900">{{ paperStatusSummary.orders }}</p>
        </div>
        <div class="rounded-lg border border-emerald-200/80 bg-white px-3 py-2">
          <p class="text-emerald-700">{{ t('command.paperPositions') }}</p>
          <p class="mt-1 font-semibold text-slate-900">{{ paperStatusSummary.positions }}</p>
        </div>
        <div class="rounded-lg border border-emerald-200/80 bg-white px-3 py-2">
          <p class="text-emerald-700">{{ t('command.paperNavPoints') }}</p>
          <p class="mt-1 font-semibold text-slate-900">{{ paperStatusSummary.navPoints }}</p>
        </div>
      </div>
    </Card>

    <Card v-if="isSampleMode" class="border border-amber-200 bg-amber-50/80">
      <h3 class="text-sm font-semibold text-amber-900">{{ t('command.sampleModeTitle') }}</h3>
      <p class="mt-1 text-sm text-amber-800">{{ t('command.sampleModeBody') }}</p>
    </Card>

    <Card class="border border-slate-200/80 bg-white">
      <div class="mb-3 flex items-center justify-between gap-3">
        <div>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ term('Pipeline Stages') }}</p>
          <h3 class="mt-1 text-sm font-semibold text-slate-900">{{ term('Stage Status Board') }}</h3>
        </div>
        <Badge :variant="runtimeStatus?.current_state === 'failed' || runtimeStatus?.stalled || runtimeStatus?.degraded ? 'warning' : runtimeStatus?.current_state === 'running' ? 'info' : 'success'">
          {{ pipelineStageLabel(runtimeStatus?.current_stage) }}
        </Badge>
      </div>
      <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        <div
          v-for="(stage, index) in stageViews"
          :key="stage.id"
          class="rounded-xl border border-slate-200/80 bg-slate-50/70 px-3 py-3"
        >
          <div class="flex items-start justify-between gap-2">
            <p class="text-xs font-semibold uppercase tracking-widest text-slate-500">{{ index + 1 }}</p>
            <Badge :variant="statusVariant(stage.status)">{{ statusLabel(stage.status) }}</Badge>
          </div>
          <p class="mt-2 text-sm font-semibold text-slate-900">{{ stage.title }}</p>
          <p class="mt-1 text-xs text-slate-500">{{ stage.subtitle }}</p>
          <p class="mt-2 text-sm text-slate-700 line-clamp-2">{{ stage.summary }}</p>
        </div>
      </div>
    </Card>

    <Card class="border border-slate-200/80 bg-white">
      <div class="mb-3">
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ term('Stage Evidence') }}</p>
        <h3 class="mt-1 text-sm font-semibold text-slate-900">{{ term('Evidence-first review cards') }}</h3>
      </div>
      <div class="space-y-3">
        <details
          v-for="stage in stageViews"
          :key="`evidence-${stage.id}`"
          class="rounded-xl border border-slate-200/80 bg-slate-50/70 px-3 py-3"
          :open="stage.id === defaultOpenStageId"
        >
          <summary class="flex cursor-pointer list-none items-center justify-between gap-3">
            <div>
              <p class="text-sm font-semibold text-slate-900">{{ stage.title }}</p>
              <p class="text-xs text-slate-500">{{ stage.subtitle }}</p>
            </div>
            <Badge :variant="statusVariant(stage.status)">{{ statusLabel(stage.status) }}</Badge>
          </summary>
          <p class="mt-3 text-sm text-slate-700">{{ stage.summary }}</p>
          <div class="mt-3 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-3">
            <div
              v-for="item in stage.evidence"
              :key="`${stage.id}-${item.label}`"
              class="rounded-lg border border-slate-200/80 bg-white px-3 py-2"
            >
              <p class="text-slate-500">{{ item.label }}</p>
              <p class="mt-1 font-semibold text-slate-900 break-words">{{ item.value }}</p>
            </div>
          </div>
        </details>
      </div>
    </Card>

    <Card class="border border-slate-200/80 bg-slate-50/70">
      <p class="text-xs uppercase tracking-widest text-slate-500">{{ term('Read-only board policy') }}</p>
      <p class="mt-2 text-sm text-slate-700">
        {{ term('This board focuses on status and evidence review. Operational controls are moved to Runtime detail.') }}
      </p>
      <div class="mt-3 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
        <div class="rounded-lg border border-slate-200/80 bg-white px-3 py-2">
          <p class="text-slate-500">{{ term('Runtime State') }}</p>
          <p class="mt-1 font-semibold text-slate-900">{{ displayLabel(t, 'runtimeState', runtimeStatus?.current_state) }}</p>
        </div>
        <div class="rounded-lg border border-slate-200/80 bg-white px-3 py-2">
          <p class="text-slate-500">{{ term('Provider Migration') }}</p>
          <p class="mt-1 font-semibold text-slate-900">{{ providerMigration?.current_provider ?? '--' }}</p>
        </div>
        <div class="rounded-lg border border-slate-200/80 bg-white px-3 py-2">
          <p class="text-slate-500">{{ term('Acceptance Status') }}</p>
          <p class="mt-1 font-semibold text-slate-900">{{ acceptanceReport?.status ? humanizeLabel(acceptanceReport.status) : '--' }}</p>
        </div>
        <div class="rounded-lg border border-slate-200/80 bg-white px-3 py-2">
          <p class="text-slate-500">{{ term('Operational Acceptance') }}</p>
          <p class="mt-1 font-semibold text-slate-900">{{ operationalAcceptance.status ? humanizeLabel(String(operationalAcceptance.status)) : '--' }}</p>
        </div>
      </div>
    </Card>
  </div>
</template>
