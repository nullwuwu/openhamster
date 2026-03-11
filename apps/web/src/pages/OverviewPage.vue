<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { LineChart } from 'echarts/charts'
import VChart from 'vue-echarts'

import Card from '@/components/ui/Card.vue'
import Badge from '@/components/ui/Badge.vue'
import { api } from '@/lib/api'

use([CanvasRenderer, GridComponent, TooltipComponent, LegendComponent, LineChart])
const { t } = useI18n()

const overviewQuery = useQuery({
  queryKey: ['overview'],
  queryFn: api.getOverview,
  refetchInterval: 12_000,
})

const navQuery = useQuery({
  queryKey: ['paper-nav-mini'],
  queryFn: api.getPaperNav,
  refetchInterval: 15_000,
})

const overview = computed(() => overviewQuery.data.value)
const navRows = computed(() => navQuery.data.value ?? [])

const navOption = computed(() => {
  const nav = [...navRows.value].reverse()
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 20, top: 24, bottom: 36 },
    xAxis: {
      type: 'category',
      data: nav.map((item) => item.trade_date),
      axisLabel: { color: '#4b5563' },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#4b5563' },
      splitLine: { lineStyle: { color: '#dbe8ef' } },
    },
    series: [
      {
        name: t('overview.totalEquity'),
        type: 'line',
        smooth: true,
        data: nav.map((item) => item.total_equity),
        lineStyle: { color: '#11839f', width: 2.5 },
        itemStyle: { color: '#11839f' },
        areaStyle: {
          color: 'rgba(17,131,159,0.16)',
        },
      },
    ],
  }
})
</script>

<template>
  <div class="space-y-4">
    <div class="metric-grid">
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('overview.backtests') }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ overview?.total_backtest_runs ?? 0 }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('overview.experiments') }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ overview?.total_experiment_runs ?? 0 }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('overview.runningJobs') }}</p>
        <p class="mt-2 text-2xl font-semibold">{{ overview?.running_jobs ?? 0 }}</p>
      </Card>
      <Card>
        <p class="text-xs uppercase tracking-widest text-slate-500">{{ t('overview.latestEquity') }}</p>
        <p class="mt-2 text-2xl font-semibold">
          {{ overview?.latest_total_equity?.toLocaleString() ?? '--' }}
        </p>
      </Card>
    </div>

    <div class="grid gap-4 xl:grid-cols-[2fr,1fr]">
      <Card>
        <div class="mb-3 flex items-center justify-between">
          <h3 class="text-sm font-semibold">{{ t('overview.paperEquityCurve') }}</h3>
          <Badge variant="info">{{ t('common.polling') }}</Badge>
        </div>
        <VChart class="h-[320px] w-full" :option="navOption" autoresize />
      </Card>

      <Card class="space-y-4">
        <div>
          <h3 class="text-sm font-semibold">{{ t('overview.latestBacktest') }}</h3>
          <p class="mt-1 text-xs text-slate-500">{{ overview?.latest_backtest?.id ?? t('overview.noRunYet') }}</p>
        </div>
        <div class="space-y-2 text-sm">
          <p>{{ t('overview.strategy') }}: <strong>{{ overview?.latest_backtest?.strategy_name ?? '--' }}</strong></p>
          <p>{{ t('overview.symbol') }}: <strong>{{ overview?.latest_backtest?.symbol ?? '--' }}</strong></p>
          <p>{{ t('overview.status') }}: <strong>{{ overview?.latest_backtest?.status ?? '--' }}</strong></p>
        </div>
        <div>
          <h3 class="text-sm font-semibold">{{ t('overview.latestExperiment') }}</h3>
          <p class="mt-1 text-xs text-slate-500">{{ overview?.latest_experiment?.id ?? t('overview.noRunYet') }}</p>
        </div>
      </Card>
    </div>
  </div>
</template>
