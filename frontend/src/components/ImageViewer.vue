<script setup>
import { ref, watch } from 'vue'
import { apiUrl } from '../api/client'

const props = defineProps({
  open: { type: Boolean, default: false },
  image: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['close', 'toggle-details'])
const failed = ref(false)

watch(
  () => (props.image ? props.image.id : null),
  () => {
    failed.value = false
  }
)
</script>

<template>
  <div class="fixed inset-0 z-50" :class="open ? '' : 'pointer-events-none'">
    <div
      class="absolute inset-0 bg-black/85 transition-opacity duration-300"
      :class="open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'"
      @click.self="emit('close')"
    ></div>

    <div v-if="open" class="absolute inset-0 flex flex-col">
      <header class="flex shrink-0 items-center justify-between gap-4 px-4 py-3">
        <span class="truncate text-xs text-tokyo-dim">
          {{ image ? image.file_name : 'Carregando…' }}
        </span>
        <div class="flex shrink-0 items-center gap-2">
          <button
            type="button"
            class="rounded-lg border border-tokyo-border bg-tokyo-surface/80 px-3 py-1.5 text-xs text-tokyo-fg transition hover:border-tokyo-blue hover:text-tokyo-blue"
            @click="emit('toggle-details')"
          >
            Detalhes
          </button>
          <button
            type="button"
            class="rounded-lg border border-tokyo-border bg-tokyo-surface/80 px-3 py-1.5 text-xs text-tokyo-fg transition hover:border-tokyo-red hover:text-tokyo-red"
            @click="emit('close')"
          >
            Fechar
          </button>
        </div>
      </header>

      <div
        class="flex min-h-0 flex-1 items-center justify-center p-4"
        @click="emit('close')"
      >
        <img
          v-if="image && image.media_url && !failed"
          :src="apiUrl(image.media_url)"
          :alt="image.file_name"
          class="max-h-full max-w-full rounded-lg object-contain shadow-2xl"
          @click.stop="emit('toggle-details')"
          @error="failed = true"
        />
        <p v-else-if="loading" class="animate-pulse text-sm text-tokyo-dim">
          Carregando…
        </p>
        <p v-else-if="error" class="text-sm text-tokyo-red">{{ error }}</p>
        <p v-else-if="image" class="max-w-md break-all text-center text-sm text-tokyo-dim">
          {{ image.file_name }}
        </p>
      </div>

      <footer class="shrink-0 pb-3 text-center text-[11px] text-tokyo-dim/70">
        Rolar o scroll: anterior / próxima · Esc fecha · clique na imagem: detalhes
      </footer>
    </div>
  </div>
</template>
