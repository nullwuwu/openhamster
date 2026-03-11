<script setup lang="ts">
import { cva } from 'class-variance-authority'
import { computed } from 'vue'

import { cn } from '@/lib/utils'

const badgeVariants = cva('inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold', {
  variants: {
    variant: {
      neutral: 'bg-slate-200 text-slate-800',
      success: 'bg-emerald-100 text-emerald-700',
      warning: 'bg-amber-100 text-amber-700',
      danger: 'bg-rose-100 text-rose-700',
      info: 'bg-cyan-100 text-cyan-700',
    },
  },
  defaultVariants: {
    variant: 'neutral',
  },
})

interface Props {
  variant?: 'neutral' | 'success' | 'warning' | 'danger' | 'info'
  class?: string
}

const props = defineProps<Props>()
const classes = computed(() => cn(badgeVariants({ variant: props.variant }), props.class))
</script>

<template>
  <span :class="classes"><slot /></span>
</template>
