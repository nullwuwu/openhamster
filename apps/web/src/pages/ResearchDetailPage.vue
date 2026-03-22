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
const proposalId = computed(() => String(route.params.proposalId ?? ''))

const proposalQuery = useQuery({
  queryKey: ['research-proposal-detail', proposalId],
  queryFn: () => api.getResearchProposal(proposalId.value),
  enabled: computed(() => proposalId.value.length > 0),
  refetchInterval: 15_000,
})
const commandQuery = useQuery({
  queryKey: ['research-detail-command-context'],
  queryFn: api.getCommandCenter,
  refetchInterval: 15_000,
})
const strategiesQuery = useQuery({
  queryKey: ['research-detail-strategy-snapshots'],
  queryFn: api.getStrategies,
  refetchInterval: 60_000,
})
const knowledgeSuggestionsQuery = useQuery({
  queryKey: ['knowledge-suggestions'],
  queryFn: api.getKnowledgeSuggestions,
  refetchInterval: 60_000,
})
const knowledgeSourcesQuery = useQuery({
  queryKey: ['knowledge-sources'],
  queryFn: api.getKnowledgeSources,
  refetchInterval: 300_000,
})

const proposal = computed(() => proposalQuery.data.value ?? null)
const command = computed(() => commandQuery.data.value)
const strategyCatalog = computed(() => strategiesQuery.data.value ?? [])
const universeSelection = computed(() => command.value?.market_snapshot.universe_selection)
const knowledgeOps = computed(() => command.value?.long_horizon_stats.knowledge ?? null)
const selectedUniverseCandidate = computed(() =>
  universeSelection.value?.candidates?.find((candidate) => candidate.symbol === universeSelection.value?.selected_symbol) ?? null,
)
const strategyParams = computed<Record<string, unknown>>(() => {
  const params = proposal.value?.strategy_dsl?.params
  return params && typeof params === 'object' && !Array.isArray(params) ? (params as Record<string, unknown>) : {}
})
const baselineStrategy = computed(() => String(strategyParams.value.base_strategy ?? ''))
const baselineMeta = computed(() => {
  if (!baselineStrategy.value) return null
  return strategyCatalog.value.find((item) => item.strategy_name === baselineStrategy.value) ?? null
})
const knowledgeSuggestions = computed(() => {
  const items = knowledgeSuggestionsQuery.data.value ?? []
  const families = (proposal.value?.evidence_pack?.quality_report?.knowledge_families_used ?? []).map((item) => String(item))
  return items.filter((item) => families.includes(item.family_key)).slice(0, 4)
})
const externalKnowledgeSources = computed(() => {
  const allSources = knowledgeSourcesQuery.data.value ?? []
  const sourceIds = new Set<string>()
  for (const item of knowledgeSuggestions.value) {
    if (item.origin !== 'external') continue
    for (const sourceId of item.linked_source_ids) sourceIds.add(String(sourceId))
  }
  return allSources.filter((item) => sourceIds.has(item.source_id))
})

function proposalStatusLabel(status?: string): string {
  return displayLabel(t, 'proposalStatus', status)
}
function sourceKindLabel(value?: string): string {
  return displayLabel(t, 'sourceKind', value)
}
function llmStatusLabel(value?: string): string {
  return displayLabel(t, 'llmStatus', value)
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
function marketBiasLabel(value?: string): string {
  return displayLabel(t, 'marketBias', value)
}
function knowledgeFamilyLabel(value?: string): string {
  return displayLabel(t, 'knowledgeFamily', value)
}
function knowledgeFitLabel(value?: string): string {
  return displayLabel(t, 'knowledgeFit', value)
}
function boolLabel(value?: boolean): string {
  if (value === undefined || value === null) return '--'
  return value ? t('common.yes') : t('common.no')
}
function statusVariant(status?: string): 'success' | 'warning' | 'danger' | 'info' | 'neutral' {
  if (status === 'active') return 'success'
  if (status === 'candidate') return 'info'
  if (status === 'rejected') return 'danger'
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
function formatSignedMetric(value?: number | null, suffix = ''): string {
  if (value === null || value === undefined) return '--'
  return `${value > 0 ? '+' : ''}${value}${suffix}`
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
          <RouterLink to="/research" class="text-sm text-slate-500 underline-offset-2 hover:underline">
            {{ t('researchDetail.backToResearch') }}
          </RouterLink>
          <h1 class="mt-2 text-sm font-semibold uppercase tracking-widest text-slate-500">{{ t('researchDetail.title') }}</h1>
          <h2 class="mt-1 text-xl font-semibold text-slate-900">{{ strategyTitle(proposal?.title) }}</h2>
          <p
            v-if="proposal?.title && strategyTitle(proposal.title) !== proposal.title"
            class="mt-1 text-xs text-slate-500"
          >
            {{ proposal.title }}
          </p>
          <p class="mt-2 text-sm text-slate-600">{{ proposal?.thesis ?? t('common.noData') }}</p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Badge :variant="statusVariant(proposal?.status)">{{ proposalStatusLabel(proposal?.status) }}</Badge>
          <Badge variant="neutral">{{ sourceKindLabel(proposal?.source_kind) }}</Badge>
          <Badge variant="info">{{ llmStatusLabel(proposal?.provider_status) }}</Badge>
        </div>
      </div>
    </Card>

    <div v-if="proposalQuery.isLoading.value" class="text-sm text-slate-500">{{ t('researchDetail.loading') }}</div>
    <div v-else-if="proposalQuery.isError.value" class="text-sm text-rose-700">
      {{ proposalQuery.error.value instanceof Error ? proposalQuery.error.value.message : t('researchDetail.loadError') }}
    </div>

    <template v-else-if="proposal">
      <div class="grid gap-4 lg:grid-cols-4">
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('candidates.final') }}</p>
          <p class="mt-2 text-2xl font-semibold text-slate-900">{{ proposal.final_score.toFixed(1) }}</p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.poolRank') }}</p>
          <p class="mt-2 text-2xl font-semibold text-slate-900">
            #{{ proposal.evidence_pack?.quality_report?.pool_ranking?.rank ?? '--' }}
          </p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.qualityBand') }}</p>
          <p class="mt-2 text-lg font-semibold text-slate-900">
            {{ qualityBandLabel(String(proposal.evidence_pack?.quality_report?.verdict?.quality_band ?? 'fragile')) }}
          </p>
        </Card>
        <Card>
          <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.createdAt') }}</p>
          <p class="mt-2 text-sm font-semibold text-slate-900">{{ formatDateTime(proposal.created_at) }}</p>
        </Card>
      </div>

      <div class="grid gap-4 xl:grid-cols-[1.1fr,0.9fr]">
        <Card class="space-y-4">
          <div>
            <h3 class="text-sm font-semibold">{{ t('researchDetail.causalView') }}</h3>
            <p class="mt-1 text-sm text-slate-600">{{ t('researchDetail.causalBody') }}</p>
          </div>
          <div class="grid gap-4 text-sm md:grid-cols-3">
            <div class="rounded-lg border border-slate-200/80 bg-white/70 p-3">
              <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.marketLens') }}</p>
              <p class="mt-2 font-semibold text-slate-900">{{ command?.market_snapshot.market_profile.label ?? proposal.market_scope }}</p>
              <p class="mt-1 text-slate-600">{{ command?.market_snapshot.market_profile.trading_style ?? t('common.noData') }}</p>
              <p class="mt-3 text-slate-500">{{ t('command.selectedUniverseSymbol') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ universeSelection?.selected_symbol ?? proposal.symbol }}</p>
              <p class="mt-2 text-slate-500">{{ t('command.selectionReason') }}</p>
              <p class="mt-1 text-slate-700">{{ universeSelection?.selection_reason ?? t('common.noData') }}</p>
            </div>
            <div class="rounded-lg border border-slate-200/80 bg-white/70 p-3">
              <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.baselineSelection') }}</p>
              <p class="mt-2 font-semibold text-slate-900">{{ baselineStrategy || t('common.noData') }}</p>
              <p class="mt-2 text-slate-500">{{ t('command.marketBias') }}</p>
              <p class="mt-1 font-semibold text-slate-900">{{ marketBiasLabel(baselineMeta?.market_bias) }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge v-for="tag in baselineMeta?.tags ?? []" :key="tag" variant="neutral">{{ tag }}</Badge>
              </div>
            </div>
            <div class="rounded-lg border border-slate-200/80 bg-white/70 p-3">
              <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.gatingOutcome') }}</p>
              <p class="mt-2 font-semibold text-slate-900">{{ proposalStatusLabel(proposal.status) }}</p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge
                  v-for="reason in proposal.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []"
                  :key="String(reason)"
                  variant="warning"
                >
                  {{ governanceReasonLabel(String(reason)) }}
                </Badge>
                <span v-if="!(proposal.evidence_pack?.governance_report?.promotion_gate?.blocked_reasons ?? []).length" class="text-slate-500">
                  {{ t('research.noGovernanceBlocks') }}
                </span>
              </div>
            </div>
          </div>
          <div v-if="selectedUniverseCandidate" class="rounded-lg border border-slate-200/80 bg-slate-50/80 p-4">
            <div class="flex items-center justify-between gap-3">
              <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('researchDetail.universeCandidate') }}</p>
              <Badge variant="info">#{{ selectedUniverseCandidate.rank ?? '--' }}</Badge>
            </div>
            <p class="mt-2 text-sm text-slate-700">{{ selectedUniverseCandidate.selection_reason ?? t('common.noData') }}</p>
            <p class="mt-2 text-xs text-slate-500">
              {{ t('research.metric20d') }}: {{ formatSignedMetric(selectedUniverseCandidate.return_20d_pct, '%') }}
              · {{ t('research.metric60d') }}: {{ formatSignedMetric(selectedUniverseCandidate.return_60d_pct, '%') }}
              · {{ t('research.metric20dVol') }}: {{ formatSignedMetric(selectedUniverseCandidate.volatility_20d_pct, '%') }}
            </p>
          </div>
          <div class="rounded-lg border border-amber-200 bg-amber-50/70 p-4">
            <p class="text-sm font-semibold text-amber-900">{{ t('researchDetail.backtestTermsTitle') }}</p>
            <p class="mt-1 text-sm text-amber-800">{{ t('researchDetail.backtestTermsBody') }}</p>
          </div>
        </Card>

        <Card class="space-y-4">
          <div>
            <h3 class="text-sm font-semibold">{{ t('researchDetail.debateAndEvidence') }}</h3>
            <p class="mt-1 text-sm text-slate-600">{{ t('researchDetail.debateBody') }}</p>
          </div>
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.for') }}</p>
            <ul class="mt-2 space-y-2 text-sm text-slate-700">
              <li v-for="point in proposal.debate_report.stance_for" :key="point">{{ point }}</li>
            </ul>
          </div>
          <div>
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('research.against') }}</p>
            <ul class="mt-2 space-y-2 text-sm text-slate-700">
              <li v-for="point in proposal.debate_report.stance_against" :key="point">{{ point }}</li>
            </ul>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-white/70 p-3 text-sm text-slate-700">
            {{ proposal.debate_report.synthesis }}
          </div>
          <div class="grid gap-2 text-sm">
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.oosPassRate') }}</span>
              <span class="font-semibold text-slate-900">{{ proposal.evidence_pack?.quality_report?.oos_validation?.walkforward_pass_rate ?? '--' }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.selectionState') }}</span>
              <span class="font-semibold text-slate-900">
                {{ poolSelectionLabel(String(proposal.evidence_pack?.quality_report?.pool_ranking?.selection_state ?? 'challenger')) }}
              </span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.accumulable') }}</span>
              <span class="font-semibold text-slate-900">{{ boolLabel(Boolean(proposal.evidence_pack?.quality_report?.verdict?.accumulable)) }}</span>
            </div>
            <div class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-white/70 px-3 py-2">
              <span class="text-slate-500">{{ t('research.replaceable') }}</span>
              <span class="font-semibold text-slate-900">{{ boolLabel(Boolean(proposal.evidence_pack?.quality_report?.verdict?.replaceable)) }}</span>
            </div>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('researchDetail.backtestAdmission') }}</p>
            <p class="mt-2 text-sm font-semibold text-slate-900">
              {{ boolLabel(Boolean(proposal.evidence_pack?.quality_report?.backtest_gate?.eligible_for_paper)) }}
            </p>
            <p class="mt-2 text-sm text-slate-700">
              {{ proposal.evidence_pack?.quality_report?.backtest_gate?.summary ?? t('common.noData') }}
            </p>
            <p class="mt-2 text-xs text-slate-500">
              {{ t('research.metricCagr') }}: {{ proposal.evidence_pack?.quality_report?.backtest_gate?.metrics?.cagr ?? '--' }}
              · {{ t('research.metricSharpe') }}: {{ proposal.evidence_pack?.quality_report?.backtest_gate?.metrics?.sharpe ?? '--' }}
              · {{ t('research.metricMaxDrawdownShort') }}: {{ proposal.evidence_pack?.quality_report?.backtest_gate?.metrics?.max_drawdown ?? '--' }}
            </p>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('researchDetail.knowledgeTitle') }}</p>
            <p class="mt-2 text-sm font-semibold text-slate-900">
              {{
                (proposal.evidence_pack?.quality_report?.knowledge_families_used ?? [])
                  .map((item) => knowledgeFamilyLabel(String(item)))
                  .join(' / ') || t('common.noData')
              }}
            </p>
            <p class="mt-2 text-sm text-slate-700">
              {{ proposal.evidence_pack?.quality_report?.baseline_delta_summary ?? t('common.noData') }}
            </p>
            <p class="mt-2 text-xs text-slate-500">
              {{ t('researchDetail.knowledgeFit') }}:
              {{ knowledgeFitLabel(String(proposal.evidence_pack?.quality_report?.knowledge_fit_assessment ?? 'unknown')) }}
              · {{ t('researchDetail.noveltyAssessment') }}:
              {{ displayLabel(t, 'noveltyAssessment', String(proposal.evidence_pack?.quality_report?.verdict?.novelty_assessment ?? 'unknown')) }}
            </p>
          </div>
          <div v-if="knowledgeSuggestions.length" class="rounded-lg border border-slate-200/80 bg-slate-50/80 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('researchDetail.knowledgeSuggestions') }}</p>
            <div class="mt-3 space-y-3 text-sm">
              <div
                v-for="item in knowledgeSuggestions"
                :key="item.suggestion_id"
                class="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-3"
              >
                <div class="flex items-center justify-between gap-2">
                  <p class="font-semibold text-slate-900">{{ knowledgeFamilyLabel(item.family_key) }}</p>
                  <div class="flex gap-2">
                    <Badge :variant="item.origin === 'external' ? 'info' : 'neutral'">{{ item.origin }}</Badge>
                    <Badge :variant="item.status === 'adopted_candidate' ? 'success' : item.status === 'review_ready' ? 'warning' : 'neutral'">
                      {{ item.status }}
                    </Badge>
                  </div>
                </div>
                <p class="mt-2 text-slate-700">{{ item.rationale_zh }}</p>
                <p class="mt-2 text-xs text-slate-500">
                  confidence: {{ item.confidence }}
                  · proposal {{ item.evidence_counts.proposal ?? 0 }}
                  · paper {{ item.evidence_counts.paper ?? 0 }}
                  · sources {{ item.linked_source_ids.join(' / ') || '--' }}
                </p>
              </div>
            </div>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-slate-50/80 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">Knowledge Phase 2</p>
            <p class="mt-2 text-sm font-semibold text-slate-900">
              review-ready {{ knowledgeOps?.review_ready_count ?? 0 }} · adopted {{ knowledgeOps?.adopted_candidate_count ?? 0 }}
            </p>
            <p class="mt-2 text-sm text-slate-700">
              外部来源 {{ knowledgeOps?.source_count ?? 0 }} 个，外部条目 {{ knowledgeOps?.external_entry_count ?? 0 }} 个。
            </p>
            <p class="mt-2 text-xs text-slate-500">
              top families: {{ (knowledgeOps?.top_families ?? []).join(' / ') || '--' }}
            </p>
          </div>
          <div v-if="externalKnowledgeSources.length" class="rounded-lg border border-slate-200/80 bg-slate-50/80 p-4">
            <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('researchDetail.externalKnowledgeSources') }}</p>
            <div class="mt-3 space-y-2 text-sm">
              <div
                v-for="item in externalKnowledgeSources"
                :key="item.source_id"
                class="rounded-lg border border-slate-200/80 bg-white/80 px-3 py-3"
              >
                <p class="font-semibold text-slate-900">{{ item.source_name }}</p>
                <p class="mt-1 text-slate-600">{{ item.publisher }}</p>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </template>
  </div>
</template>
