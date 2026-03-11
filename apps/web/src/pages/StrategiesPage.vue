<script setup lang="ts">
import { useQuery } from '@tanstack/vue-query'
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

import Badge from '@/components/ui/Badge.vue'
import Card from '@/components/ui/Card.vue'
import { api } from '@/lib/api'

const { t } = useI18n()

const strategiesQuery = useQuery({
  queryKey: ['strategies'],
  queryFn: api.getStrategies,
  refetchInterval: 30_000,
})

const strategies = computed(() => strategiesQuery.data.value ?? [])
</script>

<template>
  <div class="space-y-4">
    <Card>
      <h3 class="text-sm font-semibold">{{ t('strategies.title') }}</h3>
      <p class="mt-1 text-sm text-slate-600">{{ t('strategies.subtitle') }}</p>
    </Card>

    <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      <Card v-for="strategy in strategies" :key="strategy.strategy_name" class="space-y-3">
        <div class="flex items-center justify-between">
          <h4 class="font-semibold">{{ strategy.strategy_name }}</h4>
          <Badge :variant="strategy.enabled ? 'success' : 'warning'">
            {{ strategy.enabled ? t('common.enabled') : t('common.disabled') }}
          </Badge>
        </div>
        <p class="text-sm text-slate-600">{{ strategy.description }}</p>
        <pre class="overflow-x-auto rounded bg-slate-900 p-3 text-xs text-slate-100">{{ JSON.stringify(strategy.default_params, null, 2) }}</pre>
      </Card>
    </div>
  </div>
</template>
