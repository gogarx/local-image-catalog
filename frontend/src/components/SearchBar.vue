<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['search'])
const term = ref(props.modelValue)
let timer = null

watch(
  () => props.modelValue,
  (value) => {
    if (value !== term.value) term.value = value
  }
)

watch(term, (value) => {
  clearTimeout(timer)
  timer = setTimeout(() => emit('search', value.trim()), 300)
})
</script>

<template>
  <div class="relative w-full max-w-xl">
    <input
      v-model="term"
      type="search"
      placeholder="Buscar nos prompts e workflows (FTS5)…"
      class="w-full rounded-lg border border-tokyo-border bg-tokyo-surface py-2 pl-10 pr-4 text-sm text-tokyo-fg placeholder:text-tokyo-dim focus:border-tokyo-blue focus:outline-none focus:ring-2 focus:ring-tokyo-blue/40"
      @keydown.escape="term = ''"
    />
    <svg
      class="absolute left-3 top-2.5 h-4 w-4 text-tokyo-dim"
      fill="none"
      viewBox="0 0 24 24"
      stroke="currentColor"
      stroke-width="2"
    >
      <path
        stroke-linecap="round"
        stroke-linejoin="round"
        d="m21 21-4.35-4.35M17 10.5a6.5 6.5 0 1 1-13 0 6.5 6.5 0 0 1 13 0Z"
      />
    </svg>
  </div>
</template>
