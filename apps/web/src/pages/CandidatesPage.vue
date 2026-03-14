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

const candidatesQuery = useQuery({
  queryKey: ['candidate-strategies'],
  queryFn: api.getCandidates,
  refetchInterval: 15_000,
})

const candidates = computed(() => candidatesQuery.data.value ?? [])
const showAllCandidates = ref(false)
const visibleCandidates = computed(() => (showAllCandidates.value ? candidates.value : candidates.value.slice(0, 6)))
const candidateSummary = computed(() => {
  const summary = {
    total: candidates.value.length,
    promotionReady: 0,
    coolingDown: 0,
    challengers: 0,
    trailing: 0,
  }
  for (const item of candidates.value) {
    const phase = item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.phase
    const selectionState = item.proposal.evidence_pack?.quality_report?.pool_ranking?.selection_state
    if (phase === 'promotion_ready') summary.promotionReady += 1
    if (phase === 'candidate_cooldown') summary.coolingDown += 1
    if (selectionState === 'challenger') summary.challengers += 1
    if (selectionState === 'trailing') summary.trailing += 1
  }
  return summary
})

function statusVariant(status: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
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

function poolSelectionLabel(value?: string): string {
  return displayLabel(t, 'poolSelection', value)
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
      <h3 class="text-sm font-semibold">{{ t('candidates.title') }}</h3>
      <p class="mt-1 text-sm text-slate-600">{{ t('candidates.subtitle') }}</p>
    </Card>

    <Card class="border border-slate-200/80 bg-slate-50/70">
      <details>
        <summary class="cursor-pointer list-none text-sm font-semibold text-slate-900">
          {{ t('candidates.guideTitle') }}
        </summary>
        <div class="mt-3 grid gap-3 lg:grid-cols-3">
          <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3">
            <p class="text-sm font-semibold text-slate-900">{{ t('candidates.guideScoreTitle') }}</p>
            <p class="mt-1 text-sm text-slate-600">{{ t('candidates.guideScoreBody') }}</p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3">
            <p class="text-sm font-semibold text-slate-900">{{ t('candidates.guidePhaseTitle') }}</p>
            <p class="mt-1 text-sm text-slate-600">{{ t('candidates.guidePhaseBody') }}</p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3">
            <p class="text-sm font-semibold text-slate-900">{{ t('candidates.guideDecisionTitle') }}</p>
            <p class="mt-1 text-sm text-slate-600">{{ t('candidates.guideDecisionBody') }}</p>
          </div>
        </div>
      </details>
    </Card>

    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.totalTracked') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ candidateSummary.total }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.promotionReady') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ candidateSummary.promotionReady }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.coolingDown') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ candidateSummary.coolingDown }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.challengers') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ candidateSummary.challengers }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.trailing') }}</p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">{{ candidateSummary.trailing }}</p>
      </Card>
    </div>

    <div class="space-y-4">
      <div class="flex items-center justify-between gap-3">
        <p class="text-sm text-slate-600">
          {{ t('candidates.showingCount', { shown: visibleCandidates.length, total: candidates.length }) }}
        </p>
        <button
          v-if="candidates.length > 6"
          type="button"
          class="text-sm font-medium text-teal-700 underline-offset-2 hover:underline"
          @click="showAllCandidates = !showAllCandidates"
        >
          {{ showAllCandidates ? t('candidates.showLess') : t('candidates.showAll') }}
        </button>
      </div>

      <Card v-for="item in visibleCandidates" :key="item.proposal.id" class="space-y-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-base font-semibold text-slate-900">{{ item.proposal.title }}</h3>
            <p class="mt-1 text-sm text-slate-600">{{ item.proposal.thesis }}</p>
            <RouterLink :to="`/candidates/${item.proposal.id}`" class="mt-2 inline-flex text-sm text-teal-700 underline-offset-2 hover:underline">
              {{ t('candidateDetail.openDetail') }}
            </RouterLink>
          </div>
          <div class="flex flex-wrap items-center justify-end gap-2">
            <Badge :variant="actionVariant(item.latest_decision?.action)">{{ riskActionLabel(item.latest_decision?.action) }}</Badge>
            <Badge :variant="statusVariant(item.proposal.status)">{{ proposalStatusLabel(item.proposal.status) }}</Badge>
          </div>
        </div>

        <div class="grid gap-3 sm:grid-cols-3 xl:grid-cols-6 text-sm">
          <div>
            <p class="text-slate-500">{{ t('candidates.deterministic') }}</p>
            <p class="mt-1 font-semibold">{{ item.proposal.deterministic_score.toFixed(1) }}</p>
          </div>
          <div>
            <p class="text-slate-500">{{ t('candidates.llm') }}</p>
            <p class="mt-1 font-semibold">{{ item.proposal.llm_score.toFixed(1) }}</p>
          </div>
          <div>
            <p class="text-slate-500">{{ t('candidates.final') }}</p>
            <p class="mt-1 font-semibold">{{ item.proposal.final_score.toFixed(1) }}</p>
          </div>
          <div>
            <p class="text-slate-500">{{ t('candidates.poolRank') }}</p>
            <p class="mt-1 font-semibold">
              #{{ item.proposal.evidence_pack?.quality_report?.pool_ranking?.rank ?? '--' }}
              / {{ item.proposal.evidence_pack?.quality_report?.pool_ranking?.total_tracked ?? '--' }}
            </p>
          </div>
          <div>
            <p class="text-slate-500">{{ t('candidates.phase') }}</p>
            <p class="mt-1 font-semibold">
              {{ governancePhaseLabel(String(item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.phase ?? 'candidate_watch')) }}
            </p>
          </div>
          <div>
            <p class="text-slate-500">{{ t('candidates.estimatedEligibility') }}</p>
            <p class="mt-1 font-semibold">
              {{
                item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.estimated_next_eligible_at
                  ? formatDateTime(String(item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.estimated_next_eligible_at))
                  : lifecycleEtaKindLabel(String(item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.eta_kind ?? 'unknown'))
              }}
            </p>
          </div>
        </div>

        <div class="grid gap-3 lg:grid-cols-[1.2fr,0.8fr,0.8fr]">
          <div class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.latestDecision') }}</p>
            <p class="mt-2 text-sm text-slate-700">{{ item.latest_decision?.llm_explanation ?? '--' }}</p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.blockedReasons') }}</p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Badge
                v-for="reason in item.latest_decision?.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []"
                :key="String(reason)"
                variant="warning"
              >
                {{ governanceReasonLabel(String(reason)) }}
              </Badge>
              <span
                v-if="!(item.latest_decision?.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []).length"
                class="text-sm text-slate-600"
              >
                {{ t('common.noData') }}
              </span>
            </div>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.nextStep') }}</p>
            <p class="mt-2 text-sm font-semibold text-slate-900">
              {{ governanceNextStepLabel(String(item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.next_step ?? 'monitor_candidate')) }}
            </p>
          </div>
        </div>

        <div class="grid gap-3 sm:grid-cols-3 text-sm">
          <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.qualityBand') }}</p>
            <p class="mt-2 font-semibold text-slate-900">
              {{ qualityBandLabel(String(item.latest_decision?.evidence_pack?.quality_report?.verdict?.quality_band ?? 'fragile')) }}
            </p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.accumulable') }}</p>
            <p class="mt-2 font-semibold text-slate-900">
              {{ item.latest_decision?.evidence_pack?.quality_report?.verdict?.accumulable ? t('common.yes') : t('common.no') }}
            </p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.replaceable') }}</p>
            <p class="mt-2 font-semibold text-slate-900">
              {{ item.latest_decision?.evidence_pack?.quality_report?.verdict?.replaceable ? t('common.yes') : t('common.no') }}
            </p>
          </div>
        </div>

        <div class="grid gap-3 sm:grid-cols-3 text-sm">
          <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.leaderGap') }}</p>
            <p class="mt-2 font-semibold text-slate-900">
              {{ item.proposal.evidence_pack?.quality_report?.pool_ranking?.leader_gap ?? '--' }}
            </p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.latestDecision') }}</p>
            <p class="mt-2 font-semibold text-slate-900">
              {{ poolSelectionLabel(String(item.proposal.evidence_pack?.quality_report?.pool_ranking?.selection_state ?? 'challenger')) }}
            </p>
          </div>
        </div>

        <div
          v-if="Array.isArray(item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.resume_conditions)"
          class="rounded-lg border border-slate-200/80 bg-slate-50 p-3 text-sm"
        >
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.resumeConditions') }}</p>
          <div class="mt-2 flex flex-wrap gap-2">
            <Badge
              v-for="condition in item.latest_decision?.evidence_pack?.governance_report?.lifecycle?.resume_conditions ?? []"
              :key="String(condition)"
              variant="warning"
            >
              {{ resumeConditionLabel(String(condition)) }}
            </Badge>
          </div>
        </div>

        <details class="rounded-lg border border-slate-200/80 bg-white/70 p-3">
          <summary class="cursor-pointer list-none text-sm font-semibold text-slate-900">
            {{ t('candidates.advancedDetails') }}
          </summary>
          <div class="mt-4 space-y-4">
            <div>
              <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.features') }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge v-for="feature in item.proposal.features_used" :key="feature" variant="neutral">{{ feature }}</Badge>
              </div>
            </div>
            <div class="grid gap-3 sm:grid-cols-2 text-sm">
              <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
                <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.activeComparison') }}</p>
                <p class="mt-2 text-sm font-semibold text-slate-900">
                  {{ item.latest_decision?.evidence_pack?.governance_report?.active_comparison?.active_title ?? t('common.noData') }}
                </p>
                <p class="mt-2 text-sm text-slate-600">
                  {{ t('candidates.scoreDelta') }}:
                  {{ item.latest_decision?.evidence_pack?.governance_report?.active_comparison?.score_delta ?? '--' }}
                </p>
                <p class="mt-1 text-sm text-slate-600">
                  {{ t('candidates.cooldownRemaining') }}:
                  {{ item.latest_decision?.evidence_pack?.governance_report?.active_comparison?.cooldown_remaining_days ?? '--' }}
                </p>
              </div>
              <div class="rounded-lg border border-slate-200/80 bg-slate-50 p-3">
                <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.createdAt') }}</p>
                <p class="mt-2 text-sm font-semibold text-slate-900">{{ formatDateTime(item.proposal.created_at) }}</p>
                <p class="mt-2 text-xs text-slate-500">{{ t('common.symbol') }}: {{ item.proposal.symbol }}</p>
                <p class="mt-1 text-xs text-slate-500">{{ t('common.source') }}: {{ item.proposal.source_kind }}</p>
              </div>
            </div>
          </div>
        </details>
      </Card>
    </div>
  </div>
</template>
