<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import ImageCard from './ImageCard.vue'

const props = defineProps({
  items: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
  page: { type: Number, default: 0 },
  pageCount: { type: Number, default: 1 },
  selectedId: { type: Number, default: null },
  searching: { type: Boolean, default: false },
})
const emit = defineEmits(['select', 'prev', 'next'])

const gridRef = ref(null)
const columnCount = ref(7)

function columnsFor(width) {
  if (width < 500) return 2
  if (width < 768) return 3
  if (width < 1024) return 4
  if (width < 1280) return 5
  if (width < 1440) return 6
  return 7
}

const columns = computed(() => {
  const buckets = Array.from({ length: columnCount.value }, () => [])
  props.items.forEach((item, index) => {
    buckets[index % columnCount.value].push(item)
  })
  return buckets.filter((bucket) => bucket.length > 0)
})

let resizeObserver = null
let resizeTimer = null

onMounted(() => {
  resizeObserver = new ResizeObserver((entries) => {
    clearTimeout(resizeTimer)
    resizeTimer = setTimeout(() => {
      const width = Math.round(entries[entries.length - 1]?.contentRect.width ?? 0)
      const next = columnsFor(width)
      if (next !== columnCount.value) columnCount.value = next
    }, 120)
  })
  if (gridRef.value) resizeObserver.observe(gridRef.value)
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  clearTimeout(resizeTimer)
})
</script>

<template>
  <div ref="gridRef">
    <div
      v-if="items.length === 0"
      class="flex min-h-64 flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-tokyo-border bg-tokyo-surface/40 p-8 text-center"
    >
      <p v-if="loading" class="animate-pulse text-sm text-tokyo-dim">Carregando…</p>
      <template v-else>
        <p class="text-sm text-tokyo-dim">
          {{ searching ? 'Nenhum resultado para esta busca.' : 'Nenhuma imagem catalogada.' }}
        </p>
        <p v-if="!searching" class="text-xs text-tokyo-dim/70">
          Rode scanner.py e depois extractor.py no backend.
        </p>
      </template>
    </div>

    <div
      v-else
      class="flex gap-2 transition-opacity duration-200 sm:gap-3"
      :class="loading ? 'opacity-40' : 'opacity-100'"
    >
      <div
        v-for="(column, columnIndex) in columns"
        :key="columnIndex"
        class="flex min-w-0 flex-1 flex-col gap-2 sm:gap-3"
      >
        <ImageCard
          v-for="item in column"
          :key="item.id"
          :item="item"
          :active="item.id === selectedId"
          @select="emit('select', $event)"
        />
      </div>
    </div>

    <nav v-if="pageCount > 1" class="mt-6 flex items-center justify-center gap-4">
      <button
        type="button"
        class="rounded-lg border border-tokyo-border bg-tokyo-overlay px-3 py-1.5 text-sm text-tokyo-fg transition hover:border-tokyo-blue hover:text-tokyo-blue disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-tokyo-border disabled:hover:text-tokyo-fg"
        :disabled="page === 0"
        @click="emit('prev')"
      >
        ← Anterior
      </button>
      <span class="text-xs text-tokyo-dim">Página {{ page + 1 }} de {{ pageCount }}</span>
      <button
        type="button"
        class="rounded-lg border border-tokyo-border bg-tokyo-overlay px-3 py-1.5 text-sm text-tokyo-fg transition hover:border-tokyo-blue hover:text-tokyo-blue disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-tokyo-border disabled:hover:text-tokyo-fg"
        :disabled="page + 1 >= pageCount"
        @click="emit('next')"
      >
        Próximo →
      </button>
    </nav>
  </div>
</template>
