<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { RouterLink, useRoute } from 'vue-router'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'
import { displayLabel, humanizeLabel } from '@/lib/display'

const { t, locale } = useI18n()
const route = useRoute()
const proposalId = computed(() => String(route.params.proposalId ?? ''))

const candidateQuery = useQuery({
  queryKey: ['candidate-detail', proposalId],
  queryFn: () => api.getCandidate(proposalId.value),
  enabled: computed(() => proposalId.value.length > 0),
  refetchInterval: 15_000,
})

const candidate = computed(() => candidateQuery.data.value)
const proposal = computed(() => candidate.value?.proposal ?? null)
const decision = computed(() => candidate.value?.latest_decision ?? null)

function proposalStatusLabel(status?: string): string {
  return displayLabel(t, 'proposalStatus', status)
}
function riskActionLabel(action?: string): string {
  return displayLabel(t, 'riskAction', action)
}
function governanceReasonLabel(reason?: string): string {
  return displayLabel(t, 'governanceReason', reason)
}
function qualityBandLabel(value?: string): string {
  return displayLabel(t, 'qualityBand', value)
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
function sourceKindLabel(value?: string): string {
  return displayLabel(t, 'sourceKind', value)
}

function statusVariant(status?: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (status === 'active') return 'success'
  if (status === 'candidate') return 'info'
  if (status === 'rejected') return 'danger'
  return 'warning'
}
function actionVariant(action?: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (action === 'promote_to_paper') return 'success'
  if (action === 'pause_active') return 'warning'
  if (action === 'reject' || action === 'rollback_to_previous_stable') return 'danger'
  if (action === 'keep_candidate') return 'info'
  return 'neutral'
}
function boolLabel(value?: boolean): string {
  if (value === undefined || value === null) return '--'
  return value ? t('common.yes') : t('common.no')
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
</script>

<template>
  <div class="space-y-4">
    <Card>
      <div class="flex flex-wrap items-start justify-between gap-4">
        <div>
          <RouterLink to="/candidates" class="text-sm text-slate-500 underline-offset-2 hover:underline">
            {{ t('candidateDetail.backToCandidates') }}
          </RouterLink>
          <h2 class="mt-2 text-xl font-semibold text-slate-900">{{ proposal?.title ?? t('candidateDetail.title') }}</h2>
          <p class="mt-2 text-sm text-slate-600">{{ proposal?.thesis ?? t('common.noData') }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Badge :variant="actionVariant(decision?.action)">{{ riskActionLabel(decision?.action) }}</Badge>
          <Badge :variant="statusVariant(proposal?.status)">{{ proposalStatusLabel(proposal?.status) }}</Badge>
          <Badge variant="neutral">{{ sourceKindLabel(proposal?.source_kind) }}</Badge>
        </div>
      </div>
    </Card>

    <div v-if="candidateQuery.isLoading.value" class="text-sm text-slate-500">{{ t('candidateDetail.loading') }}</div>
    <div v-else-if="candidateQuery.isError.value" class="text-sm text-rose-700">
      {{ candidateQuery.error.value instanceof Error ? candidateQuery.error.value.message : t('candidateDetail.loadError') }}
    </div>

    <template v-else-if="proposal && decision">
      <div class="grid gap-4 lg:grid-cols-4">
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.final') }}</p>
          <p class="mt-2 text-2xl font-semibold text-slate-900">{{ proposal.final_score.toFixed(1) }}</p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.poolRank') }}</p>
          <p class="mt-2 text-2xl font-semibold text-slate-900">
            #{{ proposal.evidence_pack?.quality_report?.pool_ranking?.rank ?? '--' }}
          </p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.phase') }}</p>
          <p class="mt-2 text-lg font-semibold text-slate-900">
            {{ governancePhaseLabel(String(decision.evidence_pack?.governance_report?.lifecycle?.phase ?? 'candidate_watch')) }}
          </p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.estimatedEligibility') }}</p>
          <p class="mt-2 text-sm font-semibold text-slate-900">
            {{
              decision.evidence_pack?.governance_report?.lifecycle?.estimated_next_eligible_at
                ? formatDateTime(String(decision.evidence_pack?.governance_report?.lifecycle?.estimated_next_eligible_at))
                : lifecycleEtaKindLabel(String(decision.evidence_pack?.governance_report?.lifecycle?.eta_kind ?? 'unknown'))
            }}
          </p>
        </Card>
      </div>

      <div class="grid gap-4 xl:grid-cols-[1.25fr,0.75fr]">
        <Card class="space-y-4">
          <div>
            <h3 class="text-sm font-semibold">{{ t('candidateDetail.decisionSummary') }}</h3>
            <p class="mt-2 text-sm text-slate-700">{{ decision.llm_explanation }}</p>
          </div>
          <div class="grid gap-3 sm:grid-cols-3 text-sm">
            <div class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2">
              <p class="text-slate-500">{{ t('candidates.deterministic') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ proposal.deterministic_score.toFixed(1) }}</p>
            </div>
            <div class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2">
              <p class="text-slate-500">{{ t('candidates.llm') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ proposal.llm_score.toFixed(1) }}</p>
            </div>
            <div class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2">
              <p class="text-slate-500">{{ t('candidateDetail.createdAt') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ formatDateTime(proposal.created_at) }}</p>
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
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidateDetail.features') }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Badge v-for="feature in proposal.features_used" :key="feature" variant="neutral">{{ feature }}</Badge>
            </div>
          </div>
        </Card>

        <Card class="space-y-4">
          <div>
            <h3 class="text-sm font-semibold">{{ t('candidateDetail.lifecycle') }}</h3>
            <div class="mt-3 grid gap-2 text-sm">
              <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
                <span class="text-slate-500">{{ t('candidates.nextStep') }}</span>
                <span class="font-semibold text-slate-900">{{ governanceNextStepLabel(String(decision.evidence_pack?.governance_report?.lifecycle?.next_step ?? 'monitor_candidate')) }}</span>
              </div>
              <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
                <span class="text-slate-500">{{ t('candidates.scoreDelta') }}</span>
                <span class="font-semibold text-slate-900">{{ decision.evidence_pack?.governance_report?.active_comparison?.score_delta ?? '--' }}</span>
              </div>
              <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
                <span class="text-slate-500">{{ t('candidates.cooldownRemaining') }}</span>
                <span class="font-semibold text-slate-900">{{ decision.evidence_pack?.governance_report?.active_comparison?.cooldown_remaining_days ?? '--' }}</span>
              </div>
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
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.qualityBand') }}</p>
            <p class="mt-2 text-sm font-semibold text-slate-900">
              {{ qualityBandLabel(String(decision.evidence_pack?.quality_report?.verdict?.quality_band ?? 'fragile')) }}
            </p>
            <div class="mt-3 grid gap-2 text-sm">
              <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
                <span class="text-slate-500">{{ t('candidates.accumulable') }}</span>
                <span class="font-semibold text-slate-900">{{ boolLabel(Boolean(decision.evidence_pack?.quality_report?.verdict?.accumulable)) }}</span>
              </div>
              <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
                <span class="text-slate-500">{{ t('candidates.replaceable') }}</span>
                <span class="font-semibold text-slate-900">{{ boolLabel(Boolean(decision.evidence_pack?.quality_report?.verdict?.replaceable)) }}</span>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </template>
  </div>
</template>
