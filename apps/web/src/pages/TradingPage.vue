<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { GridComponent, TooltipComponent } from 'echarts/components'
import { BarChart, LineChart } from 'echarts/charts'
import VChart from 'vue-echarts'

import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'

use([CanvasRenderer, GridComponent, TooltipComponent, LineChart, BarChart])
const { t } = useI18n()

const navQuery = useQuery({ queryKey: ['paper-nav'], queryFn: api.getPaperNav, refetchInterval: 10_000 })
const ordersQuery = useQuery({ queryKey: ['paper-orders'], queryFn: api.getPaperOrders, refetchInterval: 10_000 })
const positionsQuery = useQuery({ queryKey: ['paper-positions'], queryFn: api.getPaperPositions, refetchInterval: 10_000 })
const orders = computed(() => ordersQuery.data.value ?? [])
const positions = computed(() => positionsQuery.data.value ?? [])

const equityOption = computed(() => {
  const nav = [...(navQuery.data.value ?? [])].reverse()
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 18, top: 24, bottom: 36 },
    xAxis: { type: 'category', data: nav.map((item) => item.trade_date) },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'line',
        smooth: true,
        data: nav.map((item) => item.total_equity),
        lineStyle: { color: '#f97316', width: 2.5 },
        itemStyle: { color: '#f97316' },
      },
    ],
  }
})

const positionOption = computed(() => {
  const current = positions.value
  return {
    tooltip: { trigger: 'axis' },
    grid: { left: 48, right: 18, top: 24, bottom: 36 },
    xAxis: { type: 'category', data: current.map((item) => item.symbol) },
    yAxis: { type: 'value' },
    series: [
      {
        type: 'bar',
        data: current.map((item) => item.market_value),
        itemStyle: { color: '#11839f' },
      },
    ],
  }
})
</script>

<template>
  <div class="space-y-4">
    <div class="grid gap-4 xl:grid-cols-2">
      <Card>
        <h3 class="mb-3 text-sm font-semibold">{{ t('trading.equity') }}</h3>
        <VChart class="h-[280px] w-full" :option="equityOption" autoresize />
      </Card>
      <Card>
        <h3 class="mb-3 text-sm font-semibold">{{ t('trading.positions') }}</h3>
        <VChart class="h-[280px] w-full" :option="positionOption" autoresize />
      </Card>
    </div>

    <Card>
      <h3 class="text-sm font-semibold">{{ t('trading.latestOrders') }}</h3>
      <div class="mt-3 overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="text-slate-500">
              <th class="pb-2">{{ t('common.time') }}</th>
              <th class="pb-2">{{ t('common.symbol') }}</th>
              <th class="pb-2">{{ t('common.side') }}</th>
              <th class="pb-2">{{ t('common.qty') }}</th>
              <th class="pb-2">{{ t('common.price') }}</th>
              <th class="pb-2">{{ t('common.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="order in orders" :key="order.id" class="border-t border-slate-200">
              <td class="py-2">{{ order.created_at }}</td>
              <td class="py-2">{{ order.symbol }}</td>
              <td class="py-2">{{ order.side }}</td>
              <td class="py-2">{{ order.quantity }}</td>
              <td class="py-2">{{ order.price.toFixed(2) }}</td>
              <td class="py-2">{{ order.status }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
