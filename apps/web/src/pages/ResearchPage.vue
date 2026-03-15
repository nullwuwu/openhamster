<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed, ref, watchEffect } from "vue";
import { useI18n } from "vue-i18n";
import { RouterLink } from "vue-router";

import Badge from "@/components/ui/Badge.vue";
import Card from "@/components/ui/Card.vue";
import { api } from "@/lib/api";
import { displayLabel, localizeStrategyTitle } from "@/lib/display";

const { t, locale } = useI18n();

const proposalsQuery = useQuery({
  queryKey: ["research-proposals"],
  queryFn: api.getResearchProposals,
  refetchInterval: 15_000,
});
const commandQuery = useQuery({
  queryKey: ["research-command-context"],
  queryFn: api.getCommandCenter,
  refetchInterval: 15_000,
});
const strategiesQuery = useQuery({
  queryKey: ["strategy-snapshots"],
  queryFn: api.getStrategies,
  refetchInterval: 60_000,
});

const selectedId = ref<string>("");
const proposals = computed(() => proposalsQuery.data.value ?? []);
const strategyCatalog = computed(() => strategiesQuery.data.value ?? []);
const command = computed(() => commandQuery.data.value);
const universeSelection = computed(
  () => command.value?.market_snapshot.universe_selection,
);
const universeCandidates = computed(
  () => universeSelection.value?.candidates?.slice(0, 3) ?? [],
);
const selectedUniverseCandidate = computed(
  () =>
    universeSelection.value?.candidates?.find(
      (candidate) =>
        candidate.symbol === universeSelection.value?.selected_symbol,
    ) ?? null,
);
const orderedProposals = computed(() => {
  const items = [...proposals.value];
  return items.sort((left, right) => {
    const leftMock = left.source_kind === "mock" ? 1 : 0;
    const rightMock = right.source_kind === "mock" ? 1 : 0;
    if (leftMock !== rightMock) return leftMock - rightMock;
    return right.final_score - left.final_score;
  });
});
const initialVisibleCount = 12;
const showAllProposals = ref(false);
const visibleProposals = computed(() =>
  showAllProposals.value
    ? orderedProposals.value
    : orderedProposals.value.slice(0, initialVisibleCount),
);
const current = computed(
  () =>
    orderedProposals.value.find((item) => item.id === selectedId.value) ??
    orderedProposals.value[0] ??
    null,
);
const isSampleMode = computed(
  () =>
    current.value?.source_kind === "mock" ||
    command.value?.llm_status?.provider === "mock" ||
    command.value?.llm_status?.status === "mock" ||
    command.value?.market_snapshot.macro_status?.status === "degraded",
);
const leaderboard = computed(() =>
  [...proposals.value]
    .sort(
      (left, right) =>
        (left.evidence_pack?.quality_report?.pool_ranking?.rank ??
          Number.MAX_SAFE_INTEGER) -
        (right.evidence_pack?.quality_report?.pool_ranking?.rank ??
          Number.MAX_SAFE_INTEGER),
    )
    .slice(0, 5),
);
const eliminatedProposals = computed(() =>
  [...proposals.value]
    .filter(
      (item) =>
        item.status === "rejected" ||
        item.evidence_pack?.quality_report?.pool_ranking?.selection_state ===
          "trailing",
    )
    .sort((left, right) => right.final_score - left.final_score)
    .slice(0, 4),
);
const eliminationSummary = computed(() => {
  const summary = {
    rejected: 0,
    trailing: 0,
    thresholdBlocked: 0,
    cooldownBlocked: 0,
  };
  for (const proposal of eliminatedProposals.value) {
    if (proposal.status === "rejected") summary.rejected += 1;
    if (
      proposal.evidence_pack?.quality_report?.pool_ranking?.selection_state ===
      "trailing"
    )
      summary.trailing += 1;
    const blockedReasons =
      proposal.evidence_pack?.governance_report?.promotion_gate
        ?.blocked_reasons ?? [];
    if (
      blockedReasons.some((reason) =>
        [
          "below_keep_threshold",
          "below_promote_threshold",
          "delta_below_threshold",
        ].includes(String(reason)),
      )
    ) {
      summary.thresholdBlocked += 1;
    }
    if (blockedReasons.some((reason) => String(reason) === "cooldown_active"))
      summary.cooldownBlocked += 1;
  }
  return summary;
});
const scorecard = computed(() => {
  if (!current.value) return [];
  return [
    {
      key: "deterministic",
      value: current.value.deterministic_score.toFixed(1),
    },
    { key: "llm", value: current.value.llm_score.toFixed(1) },
    { key: "final", value: current.value.final_score.toFixed(1) },
  ];
});
const strategyParams = computed<Record<string, unknown>>(() => {
  const params = current.value?.strategy_dsl?.params;
  return params && typeof params === "object" && !Array.isArray(params)
    ? (params as Record<string, unknown>)
    : {};
});
const currentBaselineStrategy = computed(() =>
  String(strategyParams.value.base_strategy ?? ""),
);
const currentBaselineMeta = computed(() => {
  if (!currentBaselineStrategy.value) return null;
  return (
    strategyCatalog.value.find(
      (item) => item.strategy_name === currentBaselineStrategy.value,
    ) ?? null
  );
});

watchEffect(() => {
  if (!selectedId.value && orderedProposals.value[0])
    selectedId.value = orderedProposals.value[0].id;
});

function proposalStatusLabel(status?: string): string {
  return displayLabel(t, "proposalStatus", status);
}
function sourceKindLabel(sourceKind?: string): string {
  return displayLabel(t, "sourceKind", sourceKind);
}
function llmStatusLabel(status?: string): string {
  return displayLabel(t, "llmStatus", status);
}
function formatMetricLabel(key: string): string {
  if (key === "deterministic") return t("candidates.deterministic");
  if (key === "llm") return t("candidates.llm");
  if (key === "final") return t("candidates.final");
  return key;
}
function boolLabel(value: boolean): string {
  return value ? t("common.passed") : t("common.blocked");
}
function governanceReasonLabel(reason?: string): string {
  return displayLabel(t, "governanceReason", reason);
}
function qualityBandLabel(value?: string): string {
  return displayLabel(t, "qualityBand", value);
}
function poolSelectionLabel(value?: string): string {
  return displayLabel(t, "poolSelection", value);
}
function governanceNextStepLabel(value?: string): string {
  return displayLabel(t, "governanceNextStep", value);
}
function lifecycleEtaKindLabel(value?: string): string {
  return displayLabel(t, "lifecycleEtaKind", value);
}
function marketBiasLabel(value?: string): string {
  return displayLabel(t, "marketBias", value);
}
function universeReasonTagLabel(value?: string): string {
  return displayLabel(t, "universeReasonTag", value);
}
function formatSignedMetric(value?: number | null, suffix = ""): string {
  if (value === null || value === undefined) return "--";
  return `${value > 0 ? "+" : ""}${value}${suffix}`;
}
function formatDateTime(value?: string | null): string {
  if (!value) return "--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(locale.value, {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(parsed);
}
function strategyTitle(value?: string | null): string {
  return localizeStrategyTitle(value, locale.value);
}
</script>

<template>
  <div class="grid gap-4 xl:grid-cols-[340px,1fr]">
    <Card class="space-y-3">
      <div>
        <h3 class="text-sm font-semibold">{{ t("research.title") }}</h3>
        <p class="mt-1 text-sm text-slate-600">{{ t("research.subtitle") }}</p>
      </div>
      <div
        class="flex items-center justify-between rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2 text-xs text-slate-600"
      >
        <span>
          {{ t("research.showingCount", { shown: visibleProposals.length, total: orderedProposals.length }) }}
        </span>
        <button
          v-if="orderedProposals.length > initialVisibleCount"
          type="button"
          class="font-medium text-teal-700 underline-offset-2 hover:underline"
          @click="showAllProposals = !showAllProposals"
        >
          {{ showAllProposals ? t("research.showLess") : t("research.showAll") }}
        </button>
      </div>
      <button
        v-for="proposal in visibleProposals"
        :key="proposal.id"
        type="button"
        class="w-full rounded-lg border px-3 py-3 text-left transition-colors"
        :class="
          proposal.id === selectedId
            ? 'border-slate-900 bg-slate-900 text-white'
            : 'border-slate-200 bg-white/60 text-slate-900 hover:bg-white'
        "
        @click="selectedId = proposal.id"
      >
        <div class="flex items-center justify-between gap-2">
          <div class="min-w-0">
            <p class="font-semibold">{{ strategyTitle(proposal.title) }}</p>
            <p
              v-if="strategyTitle(proposal.title) !== proposal.title"
              class="mt-1 truncate text-xs opacity-70"
            >
              {{ proposal.title }}
            </p>
          </div>
          <Badge
            :variant="
              proposal.status === 'active'
                ? 'success'
                : proposal.status === 'candidate'
                  ? 'info'
                  : 'danger'
            "
          >
            {{ proposalStatusLabel(proposal.status) }}
          </Badge>
        </div>
        <p class="mt-1 text-sm opacity-80">{{ proposal.thesis }}</p>
      </button>
    </Card>

    <div class="space-y-4">
      <Card v-if="isSampleMode" class="border border-amber-200 bg-amber-50/80">
        <h3 class="text-sm font-semibold text-amber-900">
          {{ t("research.sampleModeTitle") }}
        </h3>
        <p class="mt-1 text-sm text-amber-800">
          {{ t("research.sampleModeBody") }}
        </p>
      </Card>

      <Card v-if="current" class="space-y-4">
        <div class="flex items-start justify-between gap-4">
          <div>
            <h3 class="text-base font-semibold">{{ strategyTitle(current.title) }}</h3>
            <p
              v-if="strategyTitle(current.title) !== current.title"
              class="mt-1 text-xs text-slate-500"
            >
              {{ current.title }}
            </p>
            <p class="mt-1 text-sm text-slate-600">{{ current.thesis }}</p>
            <p class="mt-3 text-xs uppercase tracking-widest text-slate-500">
              {{ t("research.providerStatus") }}
            </p>
            <div
              class="mt-2 flex flex-wrap items-center gap-2 text-sm text-slate-700"
            >
              <Badge variant="info">{{
                sourceKindLabel(current.source_kind)
              }}</Badge>
              <Badge variant="neutral">{{
                llmStatusLabel(current.provider_status)
              }}</Badge>
              <span>{{ current.provider_model }}</span>
            </div>
            <p class="mt-2 text-sm text-slate-600">
              {{ current.provider_message }}
            </p>
          </div>
          <div class="flex flex-col items-end gap-2">
            <Badge variant="info">{{ current.final_score.toFixed(1) }}</Badge>
            <RouterLink
              :to="`/research/${current.id}`"
              class="text-sm font-medium text-teal-700 underline-offset-2 hover:underline"
            >
              {{ t("research.openDetail") }}
            </RouterLink>
          </div>
        </div>
        <div class="grid gap-3 md:grid-cols-3">
          <div
            v-for="item in scorecard"
            :key="item.key"
            class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3"
          >
            <p class="text-sm text-slate-500">
              {{ formatMetricLabel(item.key) }}
            </p>
            <p class="mt-1 text-2xl font-semibold text-slate-900">
              {{ item.value }}
            </p>
          </div>
        </div>
      </Card>

      <Card v-if="current" class="space-y-4">
        <div class="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h3 class="text-sm font-semibold">
              {{ t("research.summaryTitle") }}
            </h3>
            <p class="mt-1 text-sm text-slate-600">
              {{ t("research.summaryBody") }}
            </p>
          </div>
          <RouterLink
            :to="`/research/${current.id}`"
            class="text-sm font-medium text-teal-700 underline-offset-2 hover:underline"
          >
            {{ t("research.openDetail") }}
          </RouterLink>
        </div>
        <div class="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          <div
            class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3"
          >
            <p class="text-sm text-slate-500">
              {{ t("research.backtestAdmission") }}
            </p>
            <p class="mt-1 text-lg font-semibold text-slate-900">
              {{
                boolLabel(
                  Boolean(
                    current.evidence_pack?.quality_report?.backtest_gate
                      ?.eligible_for_paper,
                  ),
                )
              }}
            </p>
            <p class="mt-1 text-sm text-slate-600">
              {{
                current.evidence_pack?.quality_report?.backtest_gate?.summary ??
                t("common.noData")
              }}
            </p>
          </div>
          <div
            class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3"
          >
            <p class="text-sm text-slate-500">
              {{ t("research.qualityBand") }}
            </p>
            <p class="mt-1 text-lg font-semibold text-slate-900">
              {{
                qualityBandLabel(
                  String(
                    current.evidence_pack?.quality_report?.verdict
                      ?.quality_band ?? "fragile",
                  ),
                )
              }}
            </p>
            <p class="mt-1 text-sm text-slate-600">
              {{ t("research.selectionState") }}:
              {{
                poolSelectionLabel(
                  String(
                    current.evidence_pack?.quality_report?.pool_ranking
                      ?.selection_state ?? "challenger",
                  ),
                )
              }}
            </p>
          </div>
          <div
            class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3"
          >
            <p class="text-sm text-slate-500">
              {{ t("research.activeComparison") }}
            </p>
            <p class="mt-1 text-lg font-semibold text-slate-900">
              {{
                current.evidence_pack?.governance_report?.active_comparison
                  ?.score_delta ?? t("common.noData")
              }}
            </p>
            <p class="mt-1 text-sm text-slate-600">
              {{
                current.evidence_pack?.governance_report?.active_comparison
                  ?.active_title ?? t("common.noData")
              }}
            </p>
          </div>
          <div
            class="rounded-lg border border-slate-200/80 bg-white/70 px-3 py-3"
          >
            <p class="text-sm text-slate-500">{{ t("candidates.nextStep") }}</p>
            <p class="mt-1 text-lg font-semibold text-slate-900">
              {{
                governanceNextStepLabel(
                  String(
                    current.evidence_pack?.governance_report?.lifecycle
                      ?.next_step ?? "monitor_candidate",
                  ),
                )
              }}
            </p>
            <p class="mt-1 text-sm text-slate-600">
              {{
                current.evidence_pack?.governance_report?.lifecycle
                  ?.estimated_next_eligible_at
                  ? formatDateTime(
                      String(
                        current.evidence_pack?.governance_report?.lifecycle
                          ?.estimated_next_eligible_at,
                      ),
                    )
                  : lifecycleEtaKindLabel(
                      String(
                        current.evidence_pack?.governance_report?.lifecycle
                          ?.eta_kind ?? "unknown",
                      ),
                    )
              }}
            </p>
          </div>
        </div>
        <div class="flex flex-wrap gap-2">
          <Badge
            v-for="reason in current.evidence_pack?.governance_report
              ?.promotion_gate?.blocked_reasons ?? []"
            :key="String(reason)"
            variant="warning"
          >
            {{ governanceReasonLabel(String(reason)) }}
          </Badge>
          <span
            v-if="
              !(
                current.evidence_pack?.governance_report?.promotion_gate
                  ?.blocked_reasons ?? []
              ).length
            "
            class="text-sm text-slate-600"
          >
            {{ t("research.noGovernanceBlocks") }}
          </span>
        </div>
      </Card>

      <details class="rounded-xl border border-slate-200/80 bg-white/90 p-4">
        <summary
          class="cursor-pointer list-none text-sm font-semibold text-slate-900"
        >
          {{ t("research.leaderboard") }}
        </summary>
        <div class="mt-3 grid gap-4 lg:grid-cols-2">
          <Card>
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-semibold">
                {{ t("research.leaderboard") }}
              </h3>
              <Badge variant="info">{{ leaderboard.length }}</Badge>
            </div>
            <div class="mt-3 space-y-3">
              <div
                v-for="proposal in leaderboard"
                :key="proposal.id"
                class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="font-medium text-slate-900">
                      {{ strategyTitle(proposal.title) }}
                    </p>
                    <p
                      v-if="strategyTitle(proposal.title) !== proposal.title"
                      class="mt-1 text-xs text-slate-500"
                    >
                      {{ proposal.title }}
                    </p>
                    <p class="mt-1 text-sm text-slate-600">
                      {{ proposal.thesis }}
                    </p>
                  </div>
                  <Badge variant="neutral"
                    >#{{
                      proposal.evidence_pack?.quality_report?.pool_ranking
                        ?.rank ?? "--"
                    }}</Badge
                  >
                </div>
                <div class="mt-3 grid gap-2 text-sm sm:grid-cols-3">
                  <div
                    class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2"
                  >
                    <p class="text-slate-500">{{ t("candidates.final") }}</p>
                    <p class="mt-1 font-semibold text-slate-900">
                      {{ proposal.final_score.toFixed(1) }}
                    </p>
                  </div>
                  <div
                    class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2"
                  >
                    <p class="text-slate-500">
                      {{ t("research.qualityBand") }}
                    </p>
                    <p class="mt-1 font-semibold text-slate-900">
                      {{
                        qualityBandLabel(
                          String(
                            proposal.evidence_pack?.quality_report?.verdict
                              ?.quality_band ?? "fragile",
                          ),
                        )
                      }}
                    </p>
                  </div>
                  <div
                    class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2"
                  >
                    <p class="text-slate-500">
                      {{ t("candidates.latestDecision") }}
                    </p>
                    <p class="mt-1 font-semibold text-slate-900">
                      {{
                        poolSelectionLabel(
                          String(
                            proposal.evidence_pack?.quality_report?.pool_ranking
                              ?.selection_state ?? "challenger",
                          ),
                        )
                      }}
                    </p>
                  </div>
                </div>
                <div class="mt-3">
                  <RouterLink
                    :to="`/research/${proposal.id}`"
                    class="text-sm font-medium text-teal-700 underline-offset-2 hover:underline"
                    >{{ t("research.openDetail") }}</RouterLink
                  >
                </div>
              </div>
            </div>
          </Card>

          <Card>
            <div class="flex items-center justify-between">
              <h3 class="text-sm font-semibold">
                {{ t("research.eliminationView") }}
              </h3>
              <Badge variant="warning">{{ eliminatedProposals.length }}</Badge>
            </div>
            <div class="mt-3 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4">
              <div
                class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2"
              >
                <p class="text-slate-500">{{ t("research.rejectedCount") }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{ eliminationSummary.rejected }}
                </p>
              </div>
              <div
                class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2"
              >
                <p class="text-slate-500">{{ t("research.trailingCount") }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{ eliminationSummary.trailing }}
                </p>
              </div>
              <div
                class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2"
              >
                <p class="text-slate-500">
                  {{ t("research.thresholdBlocked") }}
                </p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{ eliminationSummary.thresholdBlocked }}
                </p>
              </div>
              <div
                class="rounded-lg border border-slate-200/80 bg-slate-50 px-3 py-2"
              >
                <p class="text-slate-500">
                  {{ t("research.cooldownBlocked") }}
                </p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{ eliminationSummary.cooldownBlocked }}
                </p>
              </div>
            </div>
            <div class="mt-3 space-y-3">
              <div
                v-for="proposal in eliminatedProposals"
                :key="proposal.id"
                class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
              >
                <div class="flex items-start justify-between gap-3">
                  <div>
                    <p class="font-medium text-slate-900">
                      {{ strategyTitle(proposal.title) }}
                    </p>
                    <p
                      v-if="strategyTitle(proposal.title) !== proposal.title"
                      class="mt-1 text-xs text-slate-500"
                    >
                      {{ proposal.title }}
                    </p>
                    <p class="mt-1 text-sm text-slate-600">
                      {{ proposal.thesis }}
                    </p>
                  </div>
                  <Badge variant="danger">{{
                    proposalStatusLabel(proposal.status)
                  }}</Badge>
                </div>
                <div class="mt-3 flex flex-wrap gap-2">
                  <Badge
                    v-for="reason in proposal.evidence_pack?.governance_report
                      ?.promotion_gate?.blocked_reasons ?? []"
                    :key="`${proposal.id}-${String(reason)}`"
                    variant="warning"
                    >{{ governanceReasonLabel(String(reason)) }}</Badge
                  >
                  <span
                    v-if="
                      !(
                        proposal.evidence_pack?.governance_report
                          ?.promotion_gate?.blocked_reasons ?? []
                      ).length
                    "
                    class="text-sm text-slate-600"
                    >{{ t("common.noData") }}</span
                  >
                </div>
                <div class="mt-3">
                  <RouterLink
                    :to="`/research/${proposal.id}`"
                    class="text-sm font-medium text-teal-700 underline-offset-2 hover:underline"
                    >{{ t("research.openDetail") }}</RouterLink
                  >
                </div>
              </div>
            </div>
          </Card>
        </div>
      </details>

      <details
        v-if="current"
        class="rounded-xl border border-slate-200/80 bg-white/90 p-4"
      >
        <summary
          class="cursor-pointer list-none text-sm font-semibold text-slate-900"
        >
          {{ t("research.detailPreviewTitle") }}
        </summary>
        <p class="mt-2 text-sm text-slate-600">
          {{ t("research.detailPreviewBody") }}
          <RouterLink
            :to="`/research/${current.id}`"
            class="ml-1 font-medium text-teal-700 underline-offset-2 hover:underline"
            >{{ t("research.openDetail") }}</RouterLink
          >
        </p>
        <div class="mt-3 grid gap-4 text-sm md:grid-cols-3">
          <div class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">
              {{ t("research.marketLens") }}
            </p>
            <p class="mt-2 font-semibold text-slate-900">
              {{
                command?.market_snapshot.market_profile.label ??
                current.market_scope
              }}
            </p>
            <p class="mt-1 text-slate-600">
              {{
                command?.market_snapshot.market_profile.trading_style ??
                t("common.noData")
              }}
            </p>
            <p class="mt-3 text-slate-500">
              {{ t("command.selectedUniverseSymbol") }}
            </p>
            <p class="mt-1 font-semibold text-slate-900">
              {{ universeSelection?.selected_symbol ?? t("common.noData") }}
            </p>
            <p class="mt-2 text-slate-500">
              {{ t("command.selectionReason") }}
            </p>
            <p class="mt-1 text-slate-700">
              {{ universeSelection?.selection_reason ?? t("common.noData") }}
            </p>
            <div
              v-if="universeSelection?.top_factors?.length"
              class="mt-2 flex flex-wrap gap-2"
            >
              <Badge
                v-for="factor in universeSelection.top_factors"
                :key="`research-factor-${factor}`"
                variant="success"
                >{{ universeReasonTagLabel(factor) }}</Badge
              >
            </div>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">
              {{ t("research.baselineSelection") }}
            </p>
            <p class="mt-2 font-semibold text-slate-900">
              {{ currentBaselineStrategy || t("common.noData") }}
            </p>
            <p class="mt-2 text-slate-500">{{ t("command.marketBias") }}</p>
            <p class="mt-1 font-semibold text-slate-900">
              {{ marketBiasLabel(currentBaselineMeta?.market_bias) }}
            </p>
            <div class="mt-2 flex flex-wrap gap-2">
              <Badge
                v-for="tag in currentBaselineMeta?.tags ?? []"
                :key="tag"
                variant="neutral"
                >{{ tag }}</Badge
              >
            </div>
          </div>
          <div class="rounded-lg border border-slate-200/80 bg-white/60 p-3">
            <p class="text-xs uppercase tracking-widest text-slate-500">
              {{ t("research.universeRanking") }}
            </p>
            <div v-if="selectedUniverseCandidate" class="space-y-2">
              <p class="font-semibold text-slate-900">
                #{{ selectedUniverseCandidate.rank ?? "--" }} ·
                {{ selectedUniverseCandidate.symbol }}
              </p>
              <p class="text-slate-600">
                {{
                  selectedUniverseCandidate.selection_reason ??
                  t("common.noData")
                }}
              </p>
              <p class="text-xs text-slate-500">
                {{ t("research.metric20d") }}:
                {{
                  formatSignedMetric(
                    selectedUniverseCandidate.return_20d_pct,
                    "%",
                  )
                }}
                · {{ t("research.metric60d") }}:
                {{
                  formatSignedMetric(
                    selectedUniverseCandidate.return_60d_pct,
                    "%",
                  )
                }}
              </p>
            </div>
            <div v-if="universeCandidates.length" class="mt-3 space-y-2">
              <div
                v-for="candidate in universeCandidates"
                :key="`research-universe-${candidate.symbol}`"
                class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
              >
                <div class="flex items-center justify-between gap-3">
                  <p class="font-medium text-slate-900">
                    #{{ candidate.rank ?? "--" }} · {{ candidate.symbol }}
                  </p>
                  <span class="text-xs text-slate-500"
                    >{{ t("command.selectionScore") }}:
                    {{ candidate.score ?? "--" }}</span
                  >
                </div>
              </div>
            </div>
          </div>
        </div>
      </details>
    </div>
  </div>
</template>
