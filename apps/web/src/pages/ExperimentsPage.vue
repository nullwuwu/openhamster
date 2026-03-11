<script setup lang="ts">
import { useMutation, useQuery, useQueryClient } from '@tanstack/vue-query'
import { computed, reactive } from 'vue'
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/Badge.vue'
import Button from '@/components/ui/Button.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'

const queryClient = useQueryClient()
const { t } = useI18n()

const form = reactive({
  symbol: '000300.SH',
  strategy_name: 'ma_cross',
  provider_name: 'stooq',
  start_date: '2020-01-01',
  end_date: '2025-01-01',
  top_n: 10,
  train_months: 12,
  test_months: 3,
  step_months: 3,
})

const runsQuery = useQuery({
  queryKey: ['experiment-runs'],
  queryFn: api.getExperiments,
  refetchInterval: 5000,
})
const runs = computed(() => runsQuery.data.value ?? [])

const optimizerMutation = useMutation({
  mutationFn: (payload: Record<string, unknown>) => api.createOptimizerRun(payload),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiment-runs'] }),
})

const walkforwardMutation = useMutation({
  mutationFn: (payload: Record<string, unknown>) => api.createWalkforwardRun(payload),
  onSuccess: () => queryClient.invalidateQueries({ queryKey: ['experiment-runs'] }),
})

function statusVariant(status: string): 'success' | 'warning' | 'danger' | 'neutral' {
  if (status === 'succeeded') return 'success'
  if (status === 'running' || status === 'queued') return 'warning'
  if (status === 'failed') return 'danger'
  return 'neutral'
}
</script>

<template>
  <div class="space-y-4">
    <Card>
      <h3 class="text-sm font-semibold">{{ t('experiments.createTitle') }}</h3>
      <div class="mt-3 grid gap-3 md:grid-cols-3">
        <input v-model="form.symbol" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" :placeholder="t('experiments.form.symbol')" />
        <input v-model="form.strategy_name" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" :placeholder="t('experiments.form.strategy')" />
        <input v-model="form.provider_name" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" :placeholder="t('experiments.form.provider')" />
        <input v-model="form.start_date" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" :placeholder="t('experiments.form.start')" />
        <input v-model="form.end_date" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" :placeholder="t('experiments.form.end')" />
        <input v-model.number="form.top_n" type="number" class="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm" :placeholder="t('experiments.form.topN')" />
      </div>
      <div class="mt-4 flex flex-wrap items-center gap-3">
        <Button @click="optimizerMutation.mutate({ ...form })">{{ t('experiments.optimizerAction') }}</Button>
        <Button variant="secondary" @click="walkforwardMutation.mutate({ ...form })">
          {{ t('experiments.walkforwardAction') }}
        </Button>
      </div>
    </Card>

    <Card>
      <h3 class="text-sm font-semibold">{{ t('experiments.runsTitle') }}</h3>
      <div class="mt-3 overflow-x-auto">
        <table class="w-full text-left text-sm">
          <thead>
            <tr class="text-slate-500">
              <th class="pb-2">{{ t('common.id') }}</th>
              <th class="pb-2">{{ t('experiments.kind') }}</th>
              <th class="pb-2">{{ t('common.symbol') }}</th>
              <th class="pb-2">{{ t('common.strategy') }}</th>
              <th class="pb-2">{{ t('common.status') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="run in runs" :key="run.id" class="border-t border-slate-200">
              <td class="py-2 font-mono text-xs">{{ run.id }}</td>
              <td class="py-2">{{ run.kind }}</td>
              <td class="py-2">{{ run.symbol }}</td>
              <td class="py-2">{{ run.strategy_name }}</td>
              <td class="py-2"><Badge :variant="statusVariant(run.status)">{{ run.status }}</Badge></td>
            </tr>
          </tbody>
        </table>
      </div>
    </Card>
  </div>
</template>
