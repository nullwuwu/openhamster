<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel, humanizeLabel, localizeStrategyTitle } from '@/lib/display'

const { t, locale } = useI18n()
const route = useRoute()
const decisionId = computed(() => String(route.params.decisionId ?? ''))

const riskDecisionQuery = useQuery({
  queryKey: ['audit-detail-risk-decisions'],
  queryFn: api.getRiskDecisions,
  refetchInterval: 12_000,
})
const auditEventQuery = useQuery({
  queryKey: ['audit-detail-events'],
  queryFn: api.getAuditEvents,
  refetchInterval: 12_000,
})
const proposalQuery = useQuery({
  queryKey: ['audit-detail-proposals'],
  queryFn: api.getResearchProposals,
  refetchInterval: 12_000,
})

const decision = computed(() =>
  (riskDecisionQuery.data.value ?? []).find((item) => item.decision_id === decisionId.value) ?? null,
)
const proposal = computed(() =>
  decision.value
    ? (proposalQuery.data.value ?? []).find((item) => item.id === decision.value?.proposal_id) ?? null
    : null,
)
const relatedEvents = computed(() =>
  (auditEventQuery.data.value ?? [])
    .filter((item) => item.decision_id === decisionId.value)
    .sort((left, right) => left.created_at.localeCompare(right.created_at)),
)

function riskActionLabel(action?: string): string {
  return displayLabel(t, 'riskAction', action)
}
function auditEventLabel(eventType?: string): string {
  return displayLabel(t, 'auditEvent', eventType)
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
function qualityBandLabel(value?: string): string {
  return displayLabel(t, 'qualityBand', value)
}
function poolSelectionLabel(value?: string): string {
  return displayLabel(t, 'poolSelection', value)
}
function resumeConditionLabel(value?: string): string {
  return displayLabel(t, 'resumeCondition', value)
}
function actionVariant(action?: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
  if (action === 'rollback_to_previous_stable' || action === 'reject') return 'danger'
  if (action === 'pause_active') return 'warning'
  if (action === 'promote_to_paper') return 'success'
  if (action === 'keep_candidate') return 'info'
  return 'neutral'
}
function auditVariant(eventType?: string): 'neutral' | 'success' | 'warning' | 'danger' | 'info' {
  if (eventType === 'live_readiness_evaluated') return 'info'
  if (eventType === 'llm_fallback_triggered' || eventType === 'macro_provider_degraded') return 'warning'
  if (eventType === 'macro_provider_recovered' || eventType === 'proposal_created') return 'success'
  if (eventType === 'risk_decision_recorded') return 'info'
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
function strategyTitle(value?: string | null): string {
  return localizeStrategyTitle(value, locale.value)
}
</script>

<template>
  <div class="space-y-4">
    <Card>
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <RouterLink to="/audit" class="text-sm text-slate-500 underline-offset-2 hover:underline">
            {{ t('auditDetail.backToAudit') }}
          </RouterLink>
          <h2 class="mt-2 text-xl font-semibold text-slate-900">{{ strategyTitle(proposal?.title) }}</h2>
          <p
            v-if="proposal?.title && strategyTitle(proposal.title) !== proposal.title"
            class="mt-1 text-xs text-slate-500"
          >
            {{ proposal.title }}
          </p>
          <p class="mt-2 text-sm text-slate-600">{{ decision?.llm_explanation ?? t('common.noData') }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Badge :variant="actionVariant(decision?.action)">{{ riskActionLabel(decision?.action) }}</Badge>
          <Badge variant="neutral">{{ decisionId }}</Badge>
        </div>
      </div>
    </Card>

    <div v-if="riskDecisionQuery.isLoading.value || auditEventQuery.isLoading.value" class="text-sm text-slate-500">
      {{ t('auditDetail.loading') }}
    </div>
    <div v-else-if="!decision" class="text-sm text-rose-700">
      {{ t('auditDetail.loadError') }}
    </div>

    <template v-else>
      <div class="grid gap-4 lg:grid-cols-4">
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('audit.phase') }}</p>
          <p class="mt-2 text-lg font-semibold text-slate-900">
            {{ governancePhaseLabel(decision.evidence_pack?.governance_report?.lifecycle?.phase) }}
          </p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('audit.nextStep') }}</p>
          <p class="mt-2 text-sm font-semibold text-slate-900">
            {{ governanceNextStepLabel(decision.evidence_pack?.governance_report?.lifecycle?.next_step) }}
          </p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.qualityBand') }}</p>
          <p class="mt-2 text-sm font-semibold text-slate-900">
            {{ qualityBandLabel(String(decision.evidence_pack?.quality_report?.verdict?.quality_band ?? 'fragile')) }}
          </p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.selectionState') }}</p>
          <p class="mt-2 text-sm font-semibold text-slate-900">
            {{ poolSelectionLabel(String(decision.evidence_pack?.quality_report?.pool_ranking?.selection_state ?? 'challenger')) }}
          </p>
        </Card>
      </div>

      <div class="grid gap-4 xl:grid-cols-[0.95fr,1.05fr]">
        <Card class="space-y-4">
          <div>
            <h3 class="text-sm font-semibold">{{ t('auditDetail.decisionSummary') }}</h3>
            <p class="mt-2 text-sm text-slate-700">{{ decision.llm_explanation }}</p>
          </div>
          <div class="grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('audit.relatedContext') }}</span>
              <span class="font-semibold text-slate-900">{{ strategyTitle(decision.evidence_pack?.governance_report?.active_comparison?.active_title) }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('audit.scoreDelta') }}</span>
              <span class="font-semibold text-slate-900">{{ decision.evidence_pack?.governance_report?.active_comparison?.score_delta ?? '--' }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('audit.cooldownRemaining') }}</span>
              <span class="font-semibold text-slate-900">{{ decision.evidence_pack?.governance_report?.active_comparison?.cooldown_remaining_days ?? '--' }}</span>
            </div>
          </div>
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.resumeConditions') }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Badge
                v-for="condition in decision.evidence_pack?.governance_report?.lifecycle?.resume_conditions ?? []"
                :key="String(condition)"
                variant="warning"
              >
                {{ resumeConditionLabel(String(condition)) }}
              </Badge>
            </div>
          </div>
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.blockedReasons') }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Badge
                v-for="reason in decision.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []"
                :key="String(reason)"
                variant="warning"
              >
                {{ governanceReasonLabel(String(reason)) }}
              </Badge>
              <span v-if="!(decision.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []).length" class="text-sm text-slate-500">
                {{ t('common.noData') }}
              </span>
            </div>
          </div>
        </Card>

        <Card>
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-sm font-semibold">{{ t('auditDetail.timeline') }}</h3>
            <Badge variant="info">{{ relatedEvents.length }}</Badge>
          </div>
          <div class="space-y-3">
            <div
              v-for="event in relatedEvents"
              :key="event.id"
              class="rounded-lg border border-slate-200/80 bg-white/70 p-3"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div class="flex flex-wrap items-center gap-2">
                  <Badge :variant="auditVariant(event.event_type)">{{ auditEventLabel(event.event_type) }}</Badge>
                  <span class="text-xs text-slate-500">{{ entityTypeLabel(event.entity_type) }}</span>
                </div>
                <span class="text-xs text-slate-500">{{ formatDateTime(event.created_at) }}</span>
              </div>
              <p class="mt-2 text-sm text-slate-700">{{ event.entity_id }}</p>
              <div v-if="event.payload && Object.keys(event.payload).length" class="mt-3 grid gap-2 text-sm">
                <div
                  v-for="(value, key) in event.payload"
                  :key="String(key)"
                  class="flex items-start justify-between gap-3 rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
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
      </div>
    </template>
  </div>
</template>
