<script setup lang="ts">
import { useQuery } from "@tanstack/vue-query";
import { computed } from "vue";
import { use } from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { GridComponent, TooltipComponent } from "echarts/components";
import { LineChart } from "echarts/charts";
import VChart from "vue-echarts";
import { useI18n } from "vue-i18n";
import { RouterLink } from "vue-router";

import Badge from "@/components/ui/Badge.vue";
import Card from "@/components/ui/Card.vue";
import { api } from "@/lib/api";
import { displayLabel, humanizeLabel } from "@/lib/display";

use([CanvasRenderer, GridComponent, TooltipComponent, LineChart]);

const { t, locale } = useI18n();

const riskDecisionQuery = useQuery({
  queryKey: ["risk-decisions"],
  queryFn: api.getRiskDecisions,
  refetchInterval: 12_000,
});
const auditEventQuery = useQuery({
  queryKey: ["audit-events"],
  queryFn: api.getAuditEvents,
  refetchInterval: 12_000,
});
const proposalQuery = useQuery({
  queryKey: ["research-proposals-audit"],
  queryFn: api.getResearchProposals,
  refetchInterval: 12_000,
});
const eventDigestQuery = useQuery({
  queryKey: ["event-digests"],
  queryFn: api.getDailyEventDigests,
  refetchInterval: 12_000,
});
const eventStreamQuery = useQuery({
  queryKey: ["event-stream"],
  queryFn: api.getEventStream,
  refetchInterval: 12_000,
});
const commandQuery = useQuery({
  queryKey: ["audit-command-center"],
  queryFn: api.getCommandCenter,
  refetchInterval: 12_000,
});

const decisions = computed(() => riskDecisionQuery.data.value ?? []);
const audits = computed(() => auditEventQuery.data.value ?? []);
const proposals = computed(() => proposalQuery.data.value ?? []);
const digests = computed(() => eventDigestQuery.data.value ?? []);
const events = computed(() => eventStreamQuery.data.value ?? []);
const providerMigration = computed(
  () => commandQuery.data.value?.provider_migration ?? null,
);
const providerMigrationHistory = computed(
  () => commandQuery.data.value?.provider_migration_history ?? [],
);
const liveReadinessHistory = computed(() =>
  audits.value
    .filter((audit) => audit.event_type === "live_readiness_evaluated")
    .map((audit) => {
      const payload = audit.payload as Record<string, unknown>;
      const dimensions =
        (payload.dimensions as Record<string, unknown> | undefined) ?? {};
      const evidence =
        (payload.evidence as Record<string, unknown> | undefined) ?? {};
      return {
        ...audit,
        status: String(payload.status ?? "not_ready"),
        score: Number(payload.score ?? 0),
        summary: String(payload.summary ?? ""),
        blockers: Array.isArray(payload.blockers)
          ? payload.blockers.map((item) => String(item))
          : [],
        nextActions: Array.isArray(payload.next_actions)
          ? payload.next_actions.map((item) => String(item))
          : [],
        dimensions: Object.fromEntries(
          Object.entries(dimensions).map(([key, value]) => [
            key,
            Number(value),
          ]),
        ),
        evidence,
      };
    })
    .sort((left, right) => right.created_at.localeCompare(left.created_at))
    .slice(0, 10),
);
const latestLiveReadiness = computed(
  () => liveReadinessHistory.value[0] ?? null,
);
const previousLiveReadiness = computed(
  () => liveReadinessHistory.value[1] ?? null,
);
const liveReadinessDelta = computed(() => {
  if (!latestLiveReadiness.value || !previousLiveReadiness.value) return null;
  const latest = latestLiveReadiness.value;
  const previous = previousLiveReadiness.value;
  const scoreDelta = latest.score - previous.score;
  const previousBlockers = new Set(previous.blockers);
  const latestBlockers = new Set(latest.blockers);
  const addedBlockers = latest.blockers.filter(
    (item) => !previousBlockers.has(item),
  );
  const clearedBlockers = previous.blockers.filter(
    (item) => !latestBlockers.has(item),
  );
  const trend =
    scoreDelta > 0 ? "improved" : scoreDelta < 0 ? "weakened" : "flat";
  return { scoreDelta, addedBlockers, clearedBlockers, trend };
});
const liveReadinessTrendOption = computed(() => {
  const rows = [...liveReadinessHistory.value].reverse();
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 16, top: 20, bottom: 28 },
    xAxis: {
      type: "category",
      data: rows.map((item) => formatDateTime(item.created_at)),
      axisLabel: { hideOverlap: true, color: "#64748b", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { color: "#64748b", fontSize: 11 },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.2)" } },
    },
    series: [
      {
        type: "line",
        smooth: true,
        data: rows.map((item) => item.score),
        lineStyle: { color: "#0f766e", width: 2.5 },
        itemStyle: { color: "#0f766e" },
        areaStyle: { color: "rgba(15, 118, 110, 0.12)" },
      },
    ],
  };
});
const providerMigrationTrendOption = computed(() => {
  const rows = providerMigrationHistory.value;
  return {
    tooltip: { trigger: "axis" },
    grid: { left: 40, right: 16, top: 20, bottom: 28 },
    legend: { bottom: 0, textStyle: { color: "#64748b", fontSize: 11 } },
    xAxis: {
      type: "category",
      data: rows.map((item) => item.label),
      axisLabel: { hideOverlap: true, color: "#64748b", fontSize: 11 },
    },
    yAxis: {
      type: "value",
      min: 0,
      max: 100,
      axisLabel: { color: "#64748b", fontSize: 11 },
      splitLine: { lineStyle: { color: "rgba(148, 163, 184, 0.2)" } },
    },
    series: [
      {
        name: t("audit.providerPromotionRate"),
        type: "line",
        smooth: true,
        data: rows.map((item) => Number((item.promotion_rate ?? 0) * 100)),
        lineStyle: { color: "#0f766e", width: 2.5 },
        itemStyle: { color: "#0f766e" },
      },
      {
        name: t("audit.providerFallbackRate"),
        type: "line",
        smooth: true,
        data: rows.map((item) => Number((item.fallback_rate ?? 0) * 100)),
        lineStyle: { color: "#b45309", width: 2.5 },
        itemStyle: { color: "#b45309" },
      },
    ],
  };
});
const universeSelectionHistory = computed(() =>
  audits.value
    .filter((audit) =>
      ["universe_selection_evaluated", "universe_selection_changed"].includes(
        audit.event_type,
      ),
    )
    .map((audit) => {
      const payload = audit.payload as Record<string, unknown>;
      const selectedCandidate =
        (payload.selected_candidate as Record<string, unknown> | undefined) ??
        {};
      const topCandidates = Array.isArray(payload.top_candidates)
        ? payload.top_candidates.map(
            (candidate) => candidate as Record<string, unknown>,
          )
        : [];
      const topFactors = Array.isArray(payload.top_factors)
        ? payload.top_factors.map((item) => String(item))
        : [];
      return {
        ...audit,
        selectedSymbol: String(payload.selected_symbol ?? audit.entity_id),
        previousSymbol: payload.previous_symbol
          ? String(payload.previous_symbol)
          : "--",
        candidateCount: payload.candidate_count ?? "--",
        selectionReason: String(payload.selection_reason ?? ""),
        selectedCandidate,
        topCandidates,
        topFactors,
      };
    })
    .slice(0, 10),
);

const proposalsById = computed(
  () => new Map(proposals.value.map((proposal) => [proposal.id, proposal])),
);

const decisionsByDecisionId = computed(
  () =>
    new Map(
      decisions.value.map((decision) => [decision.decision_id, decision]),
    ),
);

const decisionTimeline = computed(() =>
  [...audits.value]
    .filter((audit) => audit.decision_id && audit.decision_id !== "n/a")
    .reduce(
      (accumulator, audit) => {
        const key = audit.decision_id;
        const entry = accumulator.get(key) ?? {
          decisionId: key,
          runId: audit.run_id,
          createdAt: audit.created_at,
          events: [] as typeof audits.value,
        };
        entry.events.push(audit);
        if (audit.created_at > entry.createdAt)
          entry.createdAt = audit.created_at;
        accumulator.set(key, entry);
        return accumulator;
      },
      new Map<
        string,
        {
          decisionId: string;
          runId: string;
          createdAt: string;
          events: typeof audits.value;
        }
      >(),
    ),
);

const timelineChains = computed(() =>
  [...decisionTimeline.value.values()]
    .map((chain) => {
      const decision =
        decisionsByDecisionId.value.get(chain.decisionId) ?? null;
      const proposal = decision
        ? (proposalsById.value.get(decision.proposal_id) ?? null)
        : null;
      const sortedEvents = [...chain.events].sort((left, right) =>
        left.created_at.localeCompare(right.created_at),
      );
      return {
        ...chain,
        decision,
        proposal,
        sortedEvents,
        eventTypes: [...new Set(sortedEvents.map((item) => item.event_type))],
      };
    })
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .slice(0, 6),
);

const recentIncidents = computed(() => {
  const systemIncidents = audits.value
    .filter((audit) =>
      [
        "llm_fallback_triggered",
        "macro_provider_degraded",
        "macro_provider_recovered",
      ].includes(audit.event_type),
    )
    .slice(0, 6);

  const decisionIncidents = decisions.value
    .filter((decision) =>
      ["pause_active", "rollback_to_previous_stable", "reject"].includes(
        decision.action,
      ),
    )
    .slice(0, 6)
    .map((decision) => ({
      id: decision.id,
      type: "decision" as const,
      createdAt: decision.created_at,
      title: riskActionLabel(decision.action),
      message: decision.llm_explanation,
      detail: decision.decision_id,
      variant: actionVariant(decision.action),
    }));

  const auditIncidents = systemIncidents.map((audit) => ({
    id: audit.id,
    type: "audit" as const,
    createdAt: audit.created_at,
    title: auditEventLabel(audit.event_type),
    message: String(
      audit.payload?.message ??
        audit.payload?.provider_message ??
        audit.entity_id,
    ),
    detail: audit.decision_id,
    variant: auditVariant(audit.event_type),
  }));

  return [...decisionIncidents, ...auditIncidents]
    .sort((left, right) => right.createdAt.localeCompare(left.createdAt))
    .slice(0, 8);
});

const summaryCards = computed(() => {
  const fallbackCount = audits.value.filter(
    (audit) => audit.event_type === "llm_fallback_triggered",
  ).length;
  const degradedCount = audits.value.filter(
    (audit) => audit.event_type === "macro_provider_degraded",
  ).length;
  const rollbackCount = decisions.value.filter(
    (decision) => decision.action === "rollback_to_previous_stable",
  ).length;
  const pausedCount = decisions.value.filter(
    (decision) => decision.action === "pause_active",
  ).length;

  return [
    {
      key: "chains",
      label: t("audit.summaryChains"),
      value: timelineChains.value.length,
    },
    {
      key: "fallbacks",
      label: t("audit.summaryFallbacks"),
      value: fallbackCount,
    },
    {
      key: "degraded",
      label: t("audit.summaryMacroDegraded"),
      value: degradedCount,
    },
    {
      key: "safety",
      label: t("audit.summarySafetyActions"),
      value: rollbackCount + pausedCount,
    },
    {
      key: "readiness",
      label: t("audit.summaryReadiness"),
      value: liveReadinessHistory.value.length,
    },
  ];
});

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

function riskActionLabel(action?: string): string {
  return displayLabel(t, "riskAction", action);
}

function auditEventLabel(eventType?: string): string {
  return displayLabel(t, "auditEvent", eventType);
}

function eventTypeLabel(eventType?: string): string {
  return displayLabel(t, "eventType", eventType);
}

function entityTypeLabel(entityType?: string): string {
  return displayLabel(t, "entityType", entityType);
}

function governanceReasonLabel(reason?: string): string {
  return displayLabel(t, "governanceReason", reason);
}

function governancePhaseLabel(phase?: string): string {
  return displayLabel(t, "governancePhase", phase);
}

function governanceNextStepLabel(step?: string): string {
  return displayLabel(t, "governanceNextStep", step);
}

function resumeConditionLabel(value?: string): string {
  return displayLabel(t, "resumeCondition", value);
}

function qualityBandLabel(value?: string): string {
  return displayLabel(t, "qualityBand", value);
}

function poolSelectionLabel(value?: string): string {
  return displayLabel(t, "poolSelection", value);
}

function backtestAdmissionLabel(eligible?: boolean): string {
  if (eligible === undefined || eligible === null) return "--";
  return eligible ? t("audit.backtestPassed") : t("audit.backtestBlocked");
}

function liveReadinessStatusLabel(value?: string): string {
  return displayLabel(t, "liveReadinessStatus", value);
}

function universeReasonTagLabel(value?: string): string {
  return displayLabel(t, "universeReasonTag", value);
}

function actionVariant(
  action?: string,
): "neutral" | "success" | "warning" | "danger" | "info" {
  if (action === "rollback_to_previous_stable" || action === "reject")
    return "danger";
  if (action === "pause_active") return "warning";
  if (action === "promote_to_paper") return "success";
  if (action === "keep_candidate") return "info";
  return "neutral";
}

function auditVariant(
  eventType?: string,
): "neutral" | "success" | "warning" | "danger" | "info" {
  if (eventType === "live_readiness_evaluated") return "info";
  if (
    eventType === "llm_fallback_triggered" ||
    eventType === "macro_provider_degraded"
  )
    return "warning";
  if (
    eventType === "macro_provider_recovered" ||
    eventType === "proposal_created"
  )
    return "success";
  if (eventType === "risk_decision_recorded") return "info";
  return "neutral";
}

function chainCauseLabel(chain: (typeof timelineChains.value)[number]): string {
  const blockedReasons =
    chain.decision?.evidence_pack?.governance_report?.promotion_gate
      ?.blocked_reasons ?? [];
  if (chain.eventTypes.includes("macro_provider_degraded"))
    return t("labels.auditCause.macro_degraded");
  if (chain.eventTypes.includes("llm_fallback_triggered"))
    return t("labels.auditCause.llm_fallback");
  if (chain.decision?.action === "rollback_to_previous_stable")
    return t("labels.auditCause.rollback");
  if (blockedReasons.includes("bottom_line_failed"))
    return t("labels.auditCause.bottom_line");
  if (blockedReasons.includes("cooldown_active"))
    return t("labels.auditCause.cooldown");
  if (blockedReasons.includes("delta_below_threshold"))
    return t("labels.auditCause.score_gap");
  return t("labels.auditCause.monitoring");
}

function chainTitle(chain: (typeof timelineChains.value)[number]): string {
  if (chain.proposal?.title) return chain.proposal.title;
  if (chain.decision?.action) return riskActionLabel(chain.decision.action);
  if (chain.eventTypes.length > 0) return auditEventLabel(chain.eventTypes[0]);
  return t("common.noData");
}

function chainSummary(chain: (typeof timelineChains.value)[number]): string {
  if (chain.decision?.llm_explanation) return chain.decision.llm_explanation;
  const firstMessage = chain.sortedEvents.find(
    (event) => typeof event.payload?.message === "string",
  )?.payload?.message;
  if (typeof firstMessage === "string" && firstMessage.trim().length > 0)
    return firstMessage;
  return `${t("audit.relatedContext")}: ${chain.runId}`;
}
</script>

<template>
  <div class="space-y-4">
    <Card>
      <h3 class="text-sm font-semibold">{{ t("audit.title") }}</h3>
      <p class="mt-1 text-sm text-slate-600">{{ t("audit.subtitle") }}</p>
    </Card>

    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Card v-for="item in summaryCards" :key="item.key">
        <p class="text-xs uppercase tracking-widest text-slate-500">
          {{ item.label }}
        </p>
        <p class="mt-3 text-2xl font-semibold text-slate-900">
          {{ item.value }}
        </p>
      </Card>
    </div>

    <Card v-if="providerMigration" class="space-y-4">
      <div class="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 class="text-sm font-semibold">
            {{ t("audit.providerMigration") }}
          </h3>
          <p class="mt-1 text-sm text-slate-600">
            {{ providerMigration.summary }}
          </p>
        </div>
        <Badge variant="neutral">{{
          providerMigration.current_provider
        }}</Badge>
      </div>
      <div class="grid gap-3 md:grid-cols-2">
        <div
          class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-3 text-sm"
        >
          <p class="text-slate-500">{{ t("audit.currentProviderCohort") }}</p>
          <p class="mt-1 font-semibold text-slate-900">
            {{ providerMigration.current.real_proposal_count }}
          </p>
          <p class="mt-1 text-slate-600">
            {{ t("audit.providerPromotionRate") }}:
            {{
              `${(providerMigration.current.promotion_rate * 100).toFixed(1)}%`
            }}
          </p>
          <p class="mt-1 text-slate-600">
            {{ t("audit.providerFallbackRate") }}:
            {{
              `${(providerMigration.current.fallback_rate * 100).toFixed(1)}%`
            }}
          </p>
        </div>
        <div
          class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-3 text-sm"
        >
          <p class="text-slate-500">{{ t("audit.previousProviderCohort") }}</p>
          <template v-if="providerMigration.previous">
            <p class="mt-1 font-semibold text-slate-900">
              {{ providerMigration.previous.real_proposal_count }}
            </p>
            <p class="mt-1 text-slate-600">
              {{ t("audit.providerPromotionRate") }}:
              {{
                `${(providerMigration.previous.promotion_rate * 100).toFixed(1)}%`
              }}
            </p>
            <p class="mt-1 text-slate-600">
              {{ t("audit.providerFallbackRate") }}:
              {{
                `${(providerMigration.previous.fallback_rate * 100).toFixed(1)}%`
              }}
            </p>
          </template>
          <p v-else class="mt-1 text-slate-500">
            {{ t("audit.providerNoPreviousCohort") }}
          </p>
        </div>
      </div>
      <VChart
        v-if="providerMigrationHistory.length"
        class="h-56 w-full"
        autoresize
        :option="providerMigrationTrendOption"
      />
      <ul
        v-if="providerMigration.notes.length"
        class="list-disc space-y-1 pl-5 text-sm text-slate-600"
      >
        <li v-for="note in providerMigration.notes" :key="note">{{ note }}</li>
      </ul>
    </Card>

    <div class="grid gap-4 xl:grid-cols-[1.25fr,0.95fr]">
      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t("audit.timeline") }}</h3>
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
                  <Badge
                    v-if="chain.decision"
                    :variant="actionVariant(chain.decision.action)"
                  >
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
                  {{ chainTitle(chain) }}
                </p>
                <p class="mt-1 text-sm text-slate-600">
                  {{ chainSummary(chain) }}
                </p>
                <RouterLink
                  v-if="chain.decisionId"
                  :to="`/audit/${chain.decisionId}`"
                  class="mt-3 inline-block text-sm font-medium text-teal-700 underline-offset-2 hover:underline"
                >
                  {{ t("audit.openDetail") }}
                </RouterLink>
              </div>
              <div class="text-right text-xs text-slate-500">
                <p class="font-mono">{{ chain.decisionId }}</p>
                <p class="mt-1">{{ formatDateTime(chain.createdAt) }}</p>
              </div>
            </div>

            <div
              v-if="chain.decision"
              class="mt-3 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4"
            >
              <div
                class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
              >
                <p class="text-slate-500">{{ t("audit.phase") }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{
                    governancePhaseLabel(
                      chain.decision.evidence_pack?.governance_report?.lifecycle
                        ?.phase,
                    )
                  }}
                </p>
              </div>
              <div
                class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
              >
                <p class="text-slate-500">{{ t("audit.nextStep") }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{
                    governanceNextStepLabel(
                      chain.decision.evidence_pack?.governance_report?.lifecycle
                        ?.next_step,
                    )
                  }}
                </p>
              </div>
              <div
                class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
              >
                <p class="text-slate-500">{{ t("research.qualityBand") }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{
                    qualityBandLabel(
                      chain.decision.evidence_pack?.quality_report?.verdict
                        ?.quality_band,
                    )
                  }}
                </p>
              </div>
              <div
                class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
              >
                <p class="text-slate-500">{{ t("research.selectionState") }}</p>
                <p class="mt-1 font-semibold text-slate-900">
                  {{
                    poolSelectionLabel(
                      chain.decision.evidence_pack?.quality_report?.pool_ranking
                        ?.selection_state,
                    )
                  }}
                </p>
              </div>
            </div>

            <div
              v-if="
                chain.decision?.evidence_pack?.quality_report?.backtest_gate
              "
              class="mt-3 rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-3 text-sm"
            >
              <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p class="text-slate-500">
                    {{ t("audit.backtestAdmission") }}
                  </p>
                  <p class="mt-1 font-semibold text-slate-900">
                    {{
                      backtestAdmissionLabel(
                        chain.decision.evidence_pack?.quality_report
                          ?.backtest_gate?.eligible_for_paper,
                      )
                    }}
                  </p>
                </div>
                <Badge
                  :variant="
                    chain.decision.evidence_pack?.quality_report?.backtest_gate
                      ?.eligible_for_paper
                      ? 'success'
                      : 'warning'
                  "
                >
                  {{
                    chain.decision.evidence_pack?.quality_report?.backtest_gate
                      ?.review?.verdict ?? "--"
                  }}
                </Badge>
              </div>
              <p class="mt-2 text-slate-600">
                {{
                  chain.decision.evidence_pack?.quality_report?.backtest_gate
                    ?.summary ?? t("common.noData")
                }}
              </p>
            </div>

            <div
              v-if="
                chain.decision?.evidence_pack?.governance_report?.lifecycle
                  ?.resume_conditions?.length
              "
              class="mt-3"
            >
              <p class="text-xs uppercase tracking-widest text-slate-500">
                {{ t("candidates.resumeConditions") }}
              </p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge
                  v-for="condition in chain.decision.evidence_pack
                    .governance_report.lifecycle.resume_conditions"
                  :key="String(condition)"
                  variant="warning"
                >
                  {{ resumeConditionLabel(String(condition)) }}
                </Badge>
              </div>
            </div>

            <div
              v-if="
                chain.decision?.evidence_pack?.governance_report?.promotion_gate
                  ?.blocked_reasons?.length
              "
              class="mt-3 flex flex-wrap gap-2"
            >
              <Badge
                v-for="reason in chain.decision.evidence_pack.governance_report
                  .promotion_gate.blocked_reasons"
                :key="String(reason)"
                variant="warning"
              >
                {{ governanceReasonLabel(String(reason)) }}
              </Badge>
            </div>

            <div class="mt-4 space-y-2 border-l border-slate-200 pl-4">
              <div
                v-for="event in chain.sortedEvents.slice(0, 2)"
                :key="event.id"
                class="rounded-lg border border-slate-200/80 bg-slate-50/80 p-3"
              >
                <div class="flex flex-wrap items-center justify-between gap-3">
                  <div class="flex flex-wrap items-center gap-2">
                    <Badge :variant="auditVariant(event.event_type)">{{
                      auditEventLabel(event.event_type)
                    }}</Badge>
                    <span class="text-xs text-slate-500">{{
                      entityTypeLabel(event.entity_type)
                    }}</span>
                  </div>
                  <span class="text-xs text-slate-500">{{
                    formatDateTime(event.created_at)
                  }}</span>
                </div>
                <p class="mt-2 text-sm text-slate-700">{{ event.entity_id }}</p>
                <p
                  v-if="event.payload?.message"
                  class="mt-1 text-sm text-slate-600"
                >
                  {{ String(event.payload.message) }}
                </p>
              </div>
              <p
                v-if="chain.sortedEvents.length > 2"
                class="text-xs text-slate-500"
              >
                {{
                  t("audit.moreEventsInDetail", {
                    count: chain.sortedEvents.length - 2,
                  })
                }}
              </p>
            </div>
          </div>
        </div>
      </Card>

      <Card>
        <div
          v-if="latestLiveReadiness"
          class="mb-4 rounded-lg border border-slate-200/80 bg-slate-50/80 p-4"
        >
          <div class="flex items-center justify-between gap-3">
            <h3 class="text-sm font-semibold">
              {{ t("audit.liveReadinessLatest") }}
            </h3>
            <Badge variant="info">{{ latestLiveReadiness.score }}</Badge>
          </div>
          <div class="mt-2 flex items-center gap-2">
            <Badge variant="neutral">{{
              liveReadinessStatusLabel(latestLiveReadiness.status)
            }}</Badge>
            <span class="text-xs text-slate-500">{{
              formatDateTime(latestLiveReadiness.created_at)
            }}</span>
          </div>
          <p class="mt-3 text-sm text-slate-600">
            {{ latestLiveReadiness.summary }}
          </p>
          <div
            v-if="latestLiveReadiness.blockers.length"
            class="mt-3 flex flex-wrap gap-2"
          >
            <Badge
              v-for="item in latestLiveReadiness.blockers"
              :key="`latest-readiness-${item}`"
              variant="warning"
            >
              {{ humanizeLabel(item) }}
            </Badge>
          </div>
        </div>

        <div
          v-if="liveReadinessDelta"
          class="mb-4 rounded-lg border border-slate-200/80 bg-white/70 p-4"
        >
          <div class="flex items-center justify-between gap-3">
            <h3 class="text-sm font-semibold">
              {{ t("audit.liveReadinessChange") }}
            </h3>
            <Badge
              :variant="
                liveReadinessDelta.trend === 'improved'
                  ? 'success'
                  : liveReadinessDelta.trend === 'weakened'
                    ? 'warning'
                    : 'neutral'
              "
            >
              {{ liveReadinessDelta.scoreDelta > 0 ? "+" : ""
              }}{{ liveReadinessDelta.scoreDelta.toFixed(1) }}
            </Badge>
          </div>
          <p class="mt-2 text-sm text-slate-600">
            {{ t(`audit.liveReadinessTrend_${liveReadinessDelta.trend}`) }}
          </p>
          <div class="mt-3 grid gap-3 sm:grid-cols-2">
            <div>
              <p class="text-xs uppercase tracking-widest text-slate-500">
                {{ t("audit.liveReadinessBlockersAdded") }}
              </p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge
                  v-for="item in liveReadinessDelta.addedBlockers"
                  :key="`added-${item}`"
                  variant="warning"
                >
                  {{ humanizeLabel(item) }}
                </Badge>
                <span
                  v-if="!liveReadinessDelta.addedBlockers.length"
                  class="text-sm text-slate-500"
                  >{{ t("common.noData") }}</span
                >
              </div>
            </div>
            <div>
              <p class="text-xs uppercase tracking-widest text-slate-500">
                {{ t("audit.liveReadinessBlockersCleared") }}
              </p>
              <div class="mt-2 flex flex-wrap gap-2">
                <Badge
                  v-for="item in liveReadinessDelta.clearedBlockers"
                  :key="`cleared-${item}`"
                  variant="success"
                >
                  {{ humanizeLabel(item) }}
                </Badge>
                <span
                  v-if="!liveReadinessDelta.clearedBlockers.length"
                  class="text-sm text-slate-500"
                  >{{ t("common.noData") }}</span
                >
              </div>
            </div>
          </div>
        </div>

        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t("audit.incidents") }}</h3>
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
              <Badge :variant="incident.variant">{{
                incident.type === "decision"
                  ? t("audit.decisionIncident")
                  : t("audit.systemIncident")
              }}</Badge>
            </div>
            <p class="mt-2 text-sm text-slate-600">
              {{ incident.message || t("common.noData") }}
            </p>
            <p class="mt-2 text-xs text-slate-500">
              {{ formatDateTime(incident.createdAt) }} · {{ incident.detail }}
            </p>
          </div>
        </div>
      </Card>
    </div>

    <details class="rounded-xl border border-slate-200/80 bg-white/90 p-4">
      <summary
        class="cursor-pointer list-none text-sm font-semibold text-slate-900"
      >
        {{ t("audit.advancedSections") }}
      </summary>
      <p class="mt-2 text-sm text-slate-600">
        {{ t("audit.advancedSectionsBody") }}
      </p>
      <div class="mt-4 space-y-4">
        <details
          class="rounded-xl border border-slate-200/80 bg-slate-50/70 p-4"
          open
        >
          <summary
            class="cursor-pointer list-none text-sm font-semibold text-slate-900"
          >
            {{ t("audit.liveReadinessHistory") }}
          </summary>
          <div class="mt-4">
            <Card v-if="liveReadinessHistory.length">
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-semibold">
                  {{ t("audit.liveReadinessHistory") }}
                </h3>
                <Badge variant="info">{{ liveReadinessHistory.length }}</Badge>
              </div>
              <VChart
                class="mb-4 h-56 w-full"
                autoresize
                :option="liveReadinessTrendOption"
              />
              <div class="space-y-3">
                <div
                  v-for="item in liveReadinessHistory"
                  :key="`readiness-history-${item.id}`"
                  class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <div class="flex items-center gap-2">
                      <Badge variant="info">{{ item.score }}</Badge>
                      <Badge variant="neutral">{{
                        liveReadinessStatusLabel(item.status)
                      }}</Badge>
                    </div>
                    <span class="text-xs text-slate-500">{{
                      formatDateTime(item.created_at)
                    }}</span>
                  </div>
                  <p class="mt-2 text-sm text-slate-600">{{ item.summary }}</p>
                  <div
                    class="mt-3 grid gap-2 text-sm sm:grid-cols-2 xl:grid-cols-4"
                  >
                    <div
                      v-for="(value, key) in item.dimensions"
                      :key="`readiness-dimension-${item.id}-${String(key)}`"
                      class="rounded-lg border border-slate-200/80 bg-slate-50/80 px-3 py-2"
                    >
                      <p class="text-slate-500">
                        {{ humanizeLabel(String(key)) }}
                      </p>
                      <p class="mt-1 font-semibold text-slate-900">
                        {{ value }}
                      </p>
                    </div>
                  </div>
                  <div
                    v-if="item.blockers.length"
                    class="mt-3 flex flex-wrap gap-2"
                  >
                    <Badge
                      v-for="blocker in item.blockers"
                      :key="`${item.id}-${blocker}`"
                      variant="warning"
                    >
                      {{ humanizeLabel(blocker) }}
                    </Badge>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </details>

        <details
          class="rounded-xl border border-slate-200/80 bg-slate-50/70 p-4"
        >
          <summary
            class="cursor-pointer list-none text-sm font-semibold text-slate-900"
          >
            {{ t("audit.universeHistory") }}
          </summary>
          <div class="mt-4">
            <Card>
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-semibold">
                  {{ t("audit.universeHistory") }}
                </h3>
                <Badge variant="info">{{
                  universeSelectionHistory.length
                }}</Badge>
              </div>
              <div class="space-y-3">
                <div
                  v-for="audit in universeSelectionHistory"
                  :key="`universe-${audit.id}`"
                  class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <p class="font-medium text-slate-900">
                      {{ audit.selectedSymbol }}
                    </p>
                    <Badge
                      :variant="
                        audit.event_type === 'universe_selection_changed'
                          ? 'success'
                          : 'info'
                      "
                    >
                      {{ auditEventLabel(audit.event_type) }}
                    </Badge>
                  </div>
                  <p class="mt-1 text-xs text-slate-500">
                    {{ formatDateTime(audit.created_at) }}
                  </p>
                  <p class="mt-2 text-sm text-slate-700">
                    {{ audit.selectionReason || t("common.noData") }}
                  </p>
                  <div class="mt-3 grid gap-2 text-sm sm:grid-cols-2">
                    <p>
                      {{ t("audit.previousSymbol") }}:
                      {{ audit.previousSymbol }}
                    </p>
                    <p>
                      {{ t("audit.candidateCount") }}:
                      {{ String(audit.candidateCount) }}
                    </p>
                    <p>
                      {{ t("command.selectionScore") }}:
                      {{ String(audit.selectedCandidate.score ?? "--") }}
                    </p>
                    <p>
                      {{ t("command.turnoverMillions") }}:
                      {{
                        String(
                          audit.selectedCandidate.turnover_millions ?? "--",
                        )
                      }}
                    </p>
                  </div>
                  <div
                    v-if="audit.topFactors.length"
                    class="mt-3 flex flex-wrap gap-2"
                  >
                    <Badge
                      v-for="factor in audit.topFactors"
                      :key="`${audit.id}-${factor}`"
                      variant="success"
                    >
                      {{ universeReasonTagLabel(String(factor)) }}
                    </Badge>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </details>

        <details
          class="rounded-xl border border-slate-200/80 bg-slate-50/70 p-4"
        >
          <summary
            class="cursor-pointer list-none text-sm font-semibold text-slate-900"
          >
            {{ t("audit.riskDecisions") }}
          </summary>
          <div class="mt-4">
            <Card>
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-semibold">
                  {{ t("audit.riskDecisions") }}
                </h3>
                <Badge variant="info">{{ decisions.length }}</Badge>
              </div>
              <div class="space-y-3">
                <div
                  v-for="decision in decisions"
                  :key="decision.id"
                  class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <p class="font-medium text-slate-900">
                      {{ riskActionLabel(decision.action) }}
                    </p>
                    <Badge
                      :variant="
                        decision.bottom_line_passed ? 'success' : 'danger'
                      "
                      >{{ decision.final_score.toFixed(1) }}</Badge
                    >
                  </div>
                  <p class="mt-2 text-sm text-slate-600">
                    {{ decision.llm_explanation }}
                  </p>
                  <div class="mt-3 flex flex-wrap gap-2">
                    <Badge
                      v-for="reason in decision.evidence_pack?.governance_report
                        ?.promotion_gate?.blocked_reasons ?? []"
                      :key="String(reason)"
                      variant="warning"
                    >
                      {{ governanceReasonLabel(String(reason)) }}
                    </Badge>
                  </div>
                  <div
                    class="mt-3 grid gap-2 text-sm text-slate-600 sm:grid-cols-2"
                  >
                    <p>
                      {{ t("audit.relatedContext") }}:
                      {{
                        decision.evidence_pack?.governance_report
                          ?.active_comparison?.active_title ??
                        t("common.noData")
                      }}
                    </p>
                    <p>
                      {{ t("audit.scoreDelta") }}:
                      {{
                        decision.evidence_pack?.governance_report
                          ?.active_comparison?.score_delta ?? "--"
                      }}
                    </p>
                    <p>
                      {{ t("audit.cooldownRemaining") }}:
                      {{
                        decision.evidence_pack?.governance_report
                          ?.active_comparison?.cooldown_remaining_days ?? "--"
                      }}
                    </p>
                    <p>
                      {{ t("audit.bottomLinePassed") }}:
                      {{
                        decision.bottom_line_passed
                          ? t("common.yes")
                          : t("common.no")
                      }}
                    </p>
                    <p>
                      {{ t("research.qualityBand") }}:
                      {{
                        qualityBandLabel(
                          String(
                            decision.evidence_pack?.quality_report?.verdict
                              ?.quality_band ?? "fragile",
                          ),
                        )
                      }}
                    </p>
                    <p>
                      {{ t("research.accumulable") }}:
                      {{
                        decision.evidence_pack?.quality_report?.verdict
                          ?.accumulable
                          ? t("common.yes")
                          : t("common.no")
                      }}
                    </p>
                    <p>
                      {{ t("audit.phase") }}:
                      {{
                        governancePhaseLabel(
                          String(
                            decision.evidence_pack?.governance_report?.lifecycle
                              ?.phase ?? "candidate_watch",
                          ),
                        )
                      }}
                    </p>
                    <p>
                      {{ t("audit.nextStep") }}:
                      {{
                        governanceNextStepLabel(
                          String(
                            decision.evidence_pack?.governance_report?.lifecycle
                              ?.next_step ?? "monitor_candidate",
                          ),
                        )
                      }}
                    </p>
                  </div>
                </div>
              </div>
            </Card>
          </div>
        </details>

        <details
          class="rounded-xl border border-slate-200/80 bg-slate-50/70 p-4"
        >
          <summary
            class="cursor-pointer list-none text-sm font-semibold text-slate-900"
          >
            {{ t("audit.dailyDigests") }}
          </summary>
          <div class="mt-4">
            <Card>
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-semibold">
                  {{ t("audit.dailyDigests") }}
                </h3>
                <Badge variant="neutral">{{ digests.length }}</Badge>
              </div>
              <div class="space-y-3">
                <div
                  v-for="digest in digests"
                  :key="digest.digest_hash"
                  class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <p class="font-medium text-slate-900">
                      {{ digest.trade_date }}
                    </p>
                    <Badge variant="info">{{ digest.symbol_scope }}</Badge>
                  </div>
                  <p class="mt-2 text-sm text-slate-700">
                    {{ digest.macro_summary }}
                  </p>
                </div>
              </div>
            </Card>
          </div>
        </details>

        <details
          class="rounded-xl border border-slate-200/80 bg-slate-50/70 p-4"
        >
          <summary
            class="cursor-pointer list-none text-sm font-semibold text-slate-900"
          >
            {{ t("audit.auditEvents") }} / {{ t("audit.eventStream") }}
          </summary>
          <div class="mt-4 grid gap-4 xl:grid-cols-[1.1fr,1fr]">
            <Card>
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-semibold">
                  {{ t("audit.auditEvents") }}
                </h3>
                <Badge variant="info">{{ audits.length }}</Badge>
              </div>
              <div class="space-y-3">
                <div
                  v-for="audit in audits"
                  :key="audit.id"
                  class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <p class="font-medium text-slate-900">
                      {{ auditEventLabel(audit.event_type) }}
                    </p>
                    <span class="font-mono text-xs text-slate-500">{{
                      audit.decision_id
                    }}</span>
                  </div>
                  <p class="mt-1 text-xs text-slate-500">
                    {{ formatDateTime(audit.created_at) }}
                  </p>
                  <p class="mt-2 text-sm text-slate-700">
                    {{ entityTypeLabel(audit.entity_type) }} ·
                    {{ audit.entity_id }}
                  </p>
                </div>
              </div>
            </Card>

            <Card>
              <div class="mb-3 flex items-center justify-between">
                <h3 class="text-sm font-semibold">
                  {{ t("audit.eventStream") }}
                </h3>
                <Badge variant="neutral">{{ events.length }}</Badge>
              </div>
              <div class="space-y-3">
                <div
                  v-for="event in events"
                  :key="event.id"
                  class="rounded-lg border border-slate-200/80 bg-white/60 p-3"
                >
                  <div class="flex items-center justify-between gap-3">
                    <p class="font-medium text-slate-900">{{ event.title }}</p>
                    <Badge variant="neutral">{{
                      eventTypeLabel(event.event_type)
                    }}</Badge>
                  </div>
                  <p class="mt-1 text-xs text-slate-500">
                    {{ formatDateTime(event.published_at) }} ·
                    {{ event.source }}
                  </p>
                  <p class="mt-2 text-sm text-slate-700">
                    {{ event.tags.join(" / ") }}
                  </p>
                </div>
              </div>
            </Card>
          </div>
        </details>
      </div>
    </details>
  </div>
</template>
