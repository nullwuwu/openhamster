<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel, humanizeLabel } from '@/lib/display'

const { t, locale } = useI18n()

const riskDecisionQuery = useQuery({
  queryKey: ['risk-decisions'],
  queryFn: api.getRiskDecisions,
  refetchInterval: 12_000,
})
const auditEventQuery = useQuery({
  queryKey: ['audit-events'],
  queryFn: api.getAuditEvents,
  refetchInterval: 12_000,
})
const proposalQuery = useQuery({
  queryKey: ['research-proposals-audit'],
  queryFn: api.getResearchProposals,
  refetchInterval: 12_000,
})
const eventDigestQuery = useQuery({
  queryKey: ['event-digests'],
  queryFn: api.getDailyEventDigests,
  refetchInterval: 12_000,
})
const eventStreamQuery = useQuery({
  queryKey: ['event-stream'],
  queryFn: api.getEventStream,
  refetchInterval: 12_000,
})

const decisions = computed(() => riskDecisionQuery.data.value ?? [])
const audits = computed(() => auditEventQuery.data.value ?? [])
const proposals = computed(() => proposalQuery.data.value ?? [])
const digests = computed(() => eventDigestQuery.data.value ?? [])
const events = computed(() => eventStreamQuery.data.value ?? [])
const universeSelectionHistory = computed(() =>
  audits.value
    .filter((audit) => ['universe_selection_evaluated', 'universe_selection_changed'].includes(audit.event_type))
    .map((audit) => {
      const payload = audit.payload as Record<string, unknown>
      const selectedCandidate = (payload.selected_candidate as Record<string, unknown> | undefined) ?? {}
      const topCandidates = Array.isArray(payload.top_candidates)
        ? payload.top_candidates.map((candidate) => candidate as Record<string, unknown>)
        : []
      const topFactors = Array.isArray(payload.top_factors) ? payload.top_factors.map((item) => String(item)) : []
      return {
        ...audit,
        selectedSymbol: String(payload.selected_symbol ?? audit.entity_id),
        previousSymbol: payload.previous_symbol ? String(payload.previous_symbol) : '--',
        candidateCount: payload.candidate_count ?? '--',
        selectionReason: String(payload.selection_reason ?? ''),
        selectedCandidate,
        topCandidates,
        topFactors,
      }
    })
    .slice(0, 10),
)

const proposalsById = computed(
  () =>
    new Map(
      proposals.value.map((proposal) => [proposal.id, proposal]),
    ),
)

const decisionsByDecisionId = computed(
  () =>
    new Map(
      decisions.value.map((decision) => [decision.decision_id, decision]),
    ),
)

const decisionTimeline = computed(() =>
  [...audits.value]
    .filter((audit) => audit.decision_id && audit.decision_id !== 'n/a')
    .reduce(
      (accumulator, audit) => {
        const key = audit.decision_id
        const entry = accumulator.get(key) ?? {
          decisionId: key,
          runId: audit.run_id,
          createdAt: audit.created_at,
          events: [] as typeof audits.value,
        }
        entry.events.push(audit)
        if (audit.created_at > entry.createdAt) entry.createdAt = audit.created_at
        accumulator.set(key, entry)
        return accumulator
      },
      new Map<
        string,
        {
          decisionId: string
          runId: string
          createdAt: string
          events: typeof audits.value
        }
      >(),
    ),
)

const timelineChains = computed(() =>
  [...decisionTimeline.value.values()]
    .map((chain) => {
      const decision = decisionsByDecisionId.value.get(chain.decisionId) ?? null
      const proposal = decision ? proposalsById.value.get(decision.proposal_id) ?? null : null
      const sortedEvents = [...chain.events].sort((left, right) => left.created_at.localeCompare(right.created_at))
      return {
        ...chain,
        decision,
        proposal,
        sortedEvents,
        eventTypes: [...new Set(sortedEvents.map((item) => item.event_type))],
      }
    })
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .slice(0, 6),
)

const recentIncidents = computed(() => {
  const systemIncidents = audits.value
    .filter((audit) =>
      ['llm_fallback_triggered', 'macro_provider_degraded', 'macro_provider_recovered'].includes(audit.event_type),
    )
    .slice(0, 6)

  const decisionIncidents = decisions.value
    .filter((decision) =>
      ['pause_active', 'rollback_to_previous_stable', 'reject'].includes(decision.action),
    )
    .slice(0, 6)
    .map((decision) => ({
      id: decision.id,
      type: 'decision' as const,
      createdAt: decision.created_at,
      title: riskActionLabel(decision.action),
      message: decision.llm_explanation,
      detail: decision.decision_id,
      variant: actionVariant(decision.action),
    }))

  const auditIncidents = systemIncidents.map((audit) => ({
    id: audit.id,
    type: 'audit' as const,
    createdAt: audit.created_at,
    title: auditEventLabel(audit.event_type),
    message: String(audit.payload?.message ?? audit.payload?.provider_message ?? audit.entity_id),
    detail: audit.decision_id,
    variant: auditVariant(audit.event_type),
  }))

  return [...decisionIncidents, ...auditIncidents]
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .slice(0, 8)
})

const summaryCards = computed(() => {
  const fallbackCount = audits.value.filter((audit) => audit.event_type === 'llm_fallback_triggered').length
  const degradedCount = audits.value.filter((audit) => audit.event_type === 'macro_provider_degraded').length
  const rollbackCount = decisions.value.filter((decision) => decision.action === 'rollback_to_previous_stable').length
  const pausedCount = decisions.value.filter((decision) => decision.action === 'pause_active').length

  return [
    { key: 'chains', label: t('audit.summaryChains'), value: timelineChains.value.length },
    { key: 'fallbacks', label: t('audit.summaryFallbacks'), value: fallbackCount },
    { key: 'degraded', label: t('audit.summaryMacroDegraded'), value: degradedCount },
    { key: 'safety', label: t('audit.summarySafetyActions'), value: rollbackCount + pausedCount },
  ]
})

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

function auditEventLabel(eventType?: string): string {
  return displayLabel(t, 'auditEvent', eventType)
}

function eventTypeLabel(eventType?: string): string {
  return displayLabel(t, 'eventType', eventType)
}

function entityTypeLabel(entityType?: string): string {
  return displayLabel(t, 'entityType', entityType)
}

function governanceReasonLabel(reason?: string): string {
  return displayLabel(t, 'governanceReason', reason)
}

function governancePhaseLabel(phase?: string): string {
  return displayLabel(t, 'governancePhase', phase)
}

function governanceNextStepLabel(step?: string): string {
  return displayLabel(t, 'governanceNextStep', step)
}

function resumeConditionLabel(value?: string): string {
  return displayLabel(t, 'resumeCondition', value)
}

function qualityBandLabel(value?: string): string {
  return displayLabel(t, 'qualityBand', value)
}

function poolSelectionLabel(value?: string): string {
  return displayLabel(t, 'poolSelection', value)
}

function universeReasonTagLabel(value?: string): string {
  return displayLabel(t, 'universeReasonTag', value)
}

function actionVariant(action?: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
  if (action === 'rollback_to_previous_stable' || action === 'reject') return 'danger'
  if (action === 'pause_active') return 'warning'
  if (action === 'promote_to_paper') return 'success'
  if (action === 'keep_candidate') return 'info'
  return 'neutral'
}

function auditVariant(eventType?: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
  if (eventType === 'llm_fallback_triggered' || eventType === 'macro_provider_degraded') return 'warning'
  if (eventType === 'macro_provider_recovered' || eventType === 'proposal_created') return 'success'
  if (eventType === 'risk_decision_recorded') return 'info'
  return 'neutral'
}

function chainCauseLabel(chain: (typeof timelineChains.value)[number]): string {
  const blockedReasons = chain.decision?.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []
  if (chain.eventTypes.includes('macro_provider_degraded')) return t('labels.auditCause.macro_degraded')
  if (chain.eventTypes.includes('llm_fallback_triggered')) return t('labels.auditCause.llm_fallback')
  if (chain.decision?.action === 'rollback_to_previous_stable') return t('labels.auditCause.rollback')
  if (blockedReasons.includes('bottom_line_failed')) return t('labels.auditCause.bottom_line')
  if (blockedReasons.includes('cooldown_active')) return t('labels.auditCause.cooldown')
  if (blockedReasons.includes('delta_below_threshold')) return t('labels.auditCause.score_gap')
  return t('labels.auditCause.monitoring')
}
</script>

<template>
  <div class="space-y-4">
    <Card>
      <h3 class="text-sm font-semibold">{{ t('audit.title') }}</h3>
      <p class="mt-1 text-sm text-slate-600">{{ t('audit.subtitle') }}</p>
    </Card>

    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card v-for="item in summaryCards" :key="item.key">
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ item.label }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ item.value }}</p>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.25fr,0.95fr]">
      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('audit.timeline') }}</h3>
          <Badge variant="info">{{ timelineChains.length }}</Badge>
        </div>
        <div class="space-y-3">
          <div
            v-for="chain in timelineChains"
            :key="chain.decisionId"
            class="rounded-lg border border-slate-200/80 bg-white/60 p-4"
          >
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div class="flex flex-wrap items-center gap-2">
                  <Badge v-if="chain.decision" :variant="actionVariant(chain.decision.action)">
                    {{ riskActionLabel(chain.decision.action) }}
                  </Badge>
                  <Badge
                    v-for="eventType in chain.eventTypes"
                    :key="eventType"
                    :variant="auditVariant(eventType)"
                  >
                    {{ auditEventLabel(eventType) }}
                  </Badge>
                  <Badge variant="neutral">{{ chainCauseLabel(chain) }}</Badge>
                </div>
                <p class="mt-3 text-sm font-semibold text-slate-900">
                  {{ chain.proposal?.title ?? t('common.noData') }}
                </p>
                <p class="mt-1 text-sm text-slate-600">
                  {{ chain.decision?.llm_explanation ?? t('common.noData') }}
                </p>
              </div>
              <div class="text-right text-xs text-slate-500">
                <p class="font-mono">{{ chain.decisionId }}</p>
                <p class="mt-1">{{ formatDateTime(chain.createdAt) }}</p>
              </div>
            </div>

            <div v-if="chain.decision" class="mt-3 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
              <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2">
                <p class="text-slate-500">{{ t('audit.phase') }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{ governancePhaseLabel(chain.decision.evidence_pack?.governance_report?.lifecycle?.phase) }}
                </p>
              </div>
              <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2">
                <p class="text-slate-500">{{ t('audit.nextStep') }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{ governanceNextStepLabel(chain.decision.evidence_pack?.governance_report?.lifecycle?.next_step) }}
                </p>
              </div>
              <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2">
                <p class="text-slate-500">{{ t('research.qualityBand') }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{ qualityBandLabel(chain.decision.evidence_pack?.quality_report?.verdict?.quality_band) }}
                </p>
              </div>
              <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2">
                <p class="text-slate-500">{{ t('research.selectionState') }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{ poolSelectionLabel(chain.decision.evidence_pack?.quality_report?.pool_ranking?.selection_state) }}
                </p>
              </div>
            </div>

            <div
              v-if="chain.decision?.evidence_pack?.governance_report?.lifecycle?.resume_conditions?.length"
              class="mt-3"
            >
              <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.resumeConditions') }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge
                  v-for="condition in chain.decision.evidence_pack.governance_report.lifecycle.resume_conditions"
                  :key="String(condition)"
                  variant="warning"
                >
                  {{ resumeConditionLabel(String(condition)) }}
                </Badge>
              </div>
            </div>

            <div
              v-if="chain.decision?.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons?.length"
              class="mt-3 flex flex-wrap gap-2"
            >
              <Badge
                v-for="reason in chain.decision.evidence_pack.governance_report.promotion_gate.blocked_reasons"
                :key="String(reason)"
                variant="warning"
              >
                {{ governanceReasonLabel(String(reason)) }}
              </Badge>
            </div>

            <div class="mt-4 space-y-2 border-l border-slate-200 pl-4">
              <div
                v-for="event in chain.sortedEvents"
                :key="event.id"
                class="rounded-lg border border-slate-200/80 bg-slate-50/80 p-3"
              >
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <Badge :variant="auditVariant(event.event_type)">{{ auditEventLabel(event.event_type) }}</Badge>
                    <span class="text-xs text-slate-500">{{ entityTypeLabel(event.entity_type) }}</span>
                  </div>
                  <span class="text-xs text-slate-500">{{ formatDateTime(event.created_at) }}</span>
                </div>
                <p class="mt-2 text-sm text-slate-700">{{ event.entity_id }}</p>
                <p v-if="event.payload?.message" class="mt-1 text-sm text-slate-600">
                  {{ String(event.payload.message) }}
                </p>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('audit.incidents') }}</h3>
          <Badge variant="warning">{{ recentIncidents.length }}</Badge>
        </div>
        <div class="space-y-3">
          <div
            v-for="incident in recentIncidents"
            :key="`${incident.type}-${incident.id}`"
            class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
          >
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ incident.title }}</p>
              <Badge :variant="incident.variant">{{ incident.type === 'decision' ? t('audit.decisionIncident') : t('audit.systemIncident') }}</Badge>
            </div>
            <p class="mt-2 text-sm text-slate-600">{{ incident.message || t('common.noData') }}</p>
            <p class="mt-2 text-xs text-slate-500">{{ formatDateTime(incident.createdAt) }} · {{ incident.detail }}</p>
          </div>
        </div>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.1fr,1fr]">
      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('audit.universeHistory') }}</h3>
          <Badge variant="info">{{ universeSelectionHistory.length }}</Badge>
        </div>
        <div class="space-y-3">
          <div v-for="audit in universeSelectionHistory" :key="`universe-${audit.id}`" class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ audit.selectedSymbol }}</p>
              <Badge :variant="audit.event_type === 'universe_selection_changed' ? 'success' : 'info'">
                {{ auditEventLabel(audit.event_type) }}
              </Badge>
            </div>
            <p class="mt-1 text-xs text-slate-500">{{ formatDateTime(audit.created_at) }}</p>
            <p class="mt-2 text-sm text-slate-700">{{ audit.selectionReason || t('common.noData') }}</p>
            <div class="mt-3 grid gap-2 text-sm sm:grid-cols-2">
              <p>{{ t('audit.previousSymbol') }}: {{ audit.previousSymbol }}</p>
              <p>{{ t('audit.candidateCount') }}: {{ String(audit.candidateCount) }}</p>
              <p>{{ t('command.selectionScore') }}: {{ String(audit.selectedCandidate.score ?? '--') }}</p>
              <p>{{ t('command.turnoverMillions') }}: {{ String(audit.selectedCandidate.turnover_millions ?? '--') }}</p>
            </div>
            <div v-if="audit.topFactors.length" class="mt-3 flex flex-wrap gap-2">
              <Badge v-for="factor in audit.topFactors" :key="`${audit.id}-${factor}`" variant="success">
                {{ universeReasonTagLabel(String(factor)) }}
              </Badge>
            </div>
            <div v-if="audit.topCandidates.length" class="mt-3 space-y-2">
              <div
                v-for="candidate in audit.topCandidates"
                :key="`${audit.id}-${String(candidate.symbol)}`"
                class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
              >
                <div class="flex items-center justify-between gap-3">
                  <p class="font-medium text-slate-900">
                    #{{ candidate.rank ?? '--' }} · {{ candidate.symbol }}
                  </p>
                  <span class="text-xs text-slate-500">{{ t('command.selectionScore') }}: {{ candidate.score ?? '--' }}</span>
                </div>
                <p class="mt-1 text-sm text-slate-600">{{ candidate.selection_reason ?? t('common.noData') }}</p>
                <div v-if="Array.isArray(candidate.reason_tags) && candidate.reason_tags.length" class="mt-2 flex flex-wrap gap-2">
                  <Badge v-for="tag in candidate.reason_tags" :key="`${audit.id}-${String(candidate.symbol)}-${String(tag)}`" variant="neutral">
                    {{ universeReasonTagLabel(String(tag)) }}
                  </Badge>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('audit.riskDecisions') }}</h3>
          <Badge variant="info">{{ decisions.length }}</Badge>
        </div>
        <div class="space-y-3">
          <div v-for="decision in decisions" :key="decision.id" class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ riskActionLabel(decision.action) }}</p>
              <Badge :variant="decision.bottom_line_passed ? 'success' : 'danger'">{{ decision.final_score.toFixed(1) }}</Badge>
            </div>
            <p class="mt-2 text-sm text-slate-600">{{ decision.llm_explanation }}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <Badge
                v-for="reason in decision.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []"
                :key="String(reason)"
                variant="warning"
              >
                {{ governanceReasonLabel(String(reason)) }}
              </Badge>
            </div>
            <div class="mt-3 grid gap-2 text-sm text-slate-600 sm:grid-cols-2">
              <p>{{ t('audit.relatedContext') }}: {{ decision.evidence_pack?.governance_report?.active_comparison?.active_title ?? t('common.noData') }}</p>
              <p>{{ t('audit.scoreDelta') }}: {{ decision.evidence_pack?.governance_report?.active_comparison?.score_delta ?? '--' }}</p>
              <p>{{ t('audit.cooldownRemaining') }}: {{ decision.evidence_pack?.governance_report?.active_comparison?.cooldown_remaining_days ?? '--' }}</p>
              <p>{{ t('audit.bottomLinePassed') }}: {{ decision.bottom_line_passed ? t('common.yes') : t('common.no') }}</p>
              <p>{{ t('research.qualityBand') }}: {{ qualityBandLabel(String(decision.evidence_pack?.quality_report?.verdict?.quality_band ?? 'fragile')) }}</p>
              <p>{{ t('research.accumulable') }}: {{ decision.evidence_pack?.quality_report?.verdict?.accumulable ? t('common.yes') : t('common.no') }}</p>
              <p>{{ t('audit.phase') }}: {{ governancePhaseLabel(String(decision.evidence_pack?.governance_report?.lifecycle?.phase ?? 'candidate_watch')) }}</p>
              <p>{{ t('audit.nextStep') }}: {{ governanceNextStepLabel(String(decision.evidence_pack?.governance_report?.lifecycle?.next_step ?? 'monitor_candidate')) }}</p>
            </div>
            <div
              v-if="decision.evidence_pack?.governance_report?.lifecycle?.resume_conditions?.length"
              class="mt-3 flex flex-wrap gap-2"
            >
              <Badge
                v-for="condition in decision.evidence_pack.governance_report.lifecycle.resume_conditions"
                :key="`${decision.id}-${String(condition)}`"
                variant="warning"
              >
                {{ resumeConditionLabel(String(condition)) }}
              </Badge>
            </div>
            <p class="mt-2 font-mono text-xs text-slate-500">{{ decision.decision_id }}</p>
          </div>
        </div>
      </Card>

      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('audit.dailyDigests') }}</h3>
          <Badge variant="neutral">{{ digests.length }}</Badge>
        </div>
        <div class="space-y-3">
          <div v-for="digest in digests" :key="digest.digest_hash" class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ digest.trade_date }}</p>
              <Badge variant="info">{{ digest.symbol_scope }}</Badge>
            </div>
            <p class="mt-2 text-sm text-slate-700">{{ digest.macro_summary }}</p>
          </div>
        </div>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-[1.1fr,1fr]">
      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('audit.auditEvents') }}</h3>
          <Badge variant="info">{{ audits.length }}</Badge>
        </div>
        <div class="space-y-3">
          <div v-for="audit in audits" :key="audit.id" class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ auditEventLabel(audit.event_type) }}</p>
              <span class="font-mono text-xs text-slate-500">{{ audit.decision_id }}</span>
            </div>
            <p class="mt-1 text-xs text-slate-500">{{ formatDateTime(audit.created_at) }}</p>
            <p class="mt-2 text-sm text-slate-700">{{ entityTypeLabel(audit.entity_type) }} · {{ audit.entity_id }}</p>
            <div v-if="audit.payload && Object.keys(audit.payload).length" class="mt-3 grid gap-2 text-sm">
              <div
                v-for="(value, key) in audit.payload"
                :key="String(key)"
                class="flex items-start justify-between gap-3 rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2"
              >
                <span class="text-slate-500">{{ humanizeLabel(String(key)) }}</span>
                <span class="max-w-[60%] break-words text-right font-semibold text-slate-900">
                  {{ typeof value === 'object' ? JSON.stringify(value) : value }}
                </span>
              </div>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('audit.eventStream') }}</h3>
          <Badge variant="neutral">{{ events.length }}</Badge>
        </div>
        <div class="space-y-3">
          <div v-for="event in events" :key="event.id" class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <div class="flex items-center justify-between gap-3">
              <p class="font-medium text-slate-900">{{ event.title }}</p>
              <Badge variant="neutral">{{ eventTypeLabel(event.event_type) }}</Badge>
            </div>
            <p class="mt-1 text-xs text-slate-500">{{ formatDateTime(event.published_at) }} · {{ event.source }}</p>
            <p class="mt-2 text-sm text-slate-700">{{ event.tags.join(' / ') }}</p>
          </div>
        </div>
      </Card>
    </div>
  </div>
</template>
