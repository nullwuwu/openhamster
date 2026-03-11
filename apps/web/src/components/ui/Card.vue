<script setup lang="ts">
import { cn } from '@/lib/utils'

defineProps<{ class?: string }>()
</script>

<template>
  <section :class="cn('panel-glass rounded-xl p-4 shadow-sm', $props.class)">
    <slot />
  </section>
</template>
