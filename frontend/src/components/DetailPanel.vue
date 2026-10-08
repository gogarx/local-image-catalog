<script setup>
import CopyButton from './CopyButton.vue'
import { apiUrl } from '../api/client'

defineProps({
  open: { type: Boolean, default: false },
  image: { type: Object, default: null },
  loading: { type: Boolean, default: false },
  error: { type: String, default: '' },
})
const emit = defineEmits(['close', 'tag-click'])

function formatSize(bytes) {
  if (!Number.isFinite(bytes)) return '—'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let value = bytes
  let unit = 0
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024
    unit += 1
  }
  return `${value.toFixed(value >= 10 || unit === 0 ? 0 : 1)} ${units[unit]}`
}

function formatTime(mtime) {
  if (!Number.isFinite(mtime)) return '—'
  return new Date(mtime * 1000).toLocaleString('pt-BR')
}
</script>

<template>
  <div class="fixed inset-0 z-[60]" :class="open ? '' : 'pointer-events-none'">
    <div
      class="absolute inset-0 bg-black/60 transition-opacity duration-300"
      :class="open ? 'pointer-events-auto opacity-100' : 'pointer-events-none opacity-0'"
      @click.self="emit('close')"
    ></div>
    <aside
      class="pointer-events-auto absolute right-0 top-0 z-50 flex h-screen w-full max-w-xl flex-col border-l border-tokyo-border bg-tokyo-surface shadow-2xl transition-transform duration-300"
      :class="open ? 'translate-x-0' : 'translate-x-full'"
    >
      <header
        class="flex shrink-0 items-center justify-between border-b border-tokyo-border bg-tokyo-surface px-4 py-3"
      >
        <h2 class="text-sm font-semibold text-tokyo-fg">Detalhes da imagem</h2>
        <button
          type="button"
          class="rounded px-2 py-1 text-xs text-tokyo-dim transition hover:bg-tokyo-overlay hover:text-tokyo-fg"
          @click="emit('close')"
        >
          Fechar
        </button>
      </header>

      <div class="flex-1 overflow-y-auto overscroll-contain">
        <div v-if="loading" class="flex min-h-64 items-center justify-center">
          <span class="animate-pulse text-sm text-tokyo-dim">Carregando metadados…</span>
        </div>

        <div v-else-if="error" class="p-4">
          <p class="rounded-lg border border-tokyo-red/40 bg-tokyo-red/10 px-4 py-3 text-sm text-tokyo-red">
            {{ error }}
          </p>
        </div>

        <div v-else-if="image" class="flex flex-col gap-4 p-4">
          <img
            v-if="image.media_url"
            :src="apiUrl(image.media_url)"
            :alt="image.file_name"
            class="max-h-64 w-full rounded-lg border border-tokyo-border bg-tokyo-bg-deep object-contain"
          />

          <dl
            class="grid grid-cols-2 gap-x-4 gap-y-2 rounded-lg border border-tokyo-border bg-tokyo-bg-deep p-3 text-xs"
          >
            <dt class="text-tokyo-dim">Arquivo</dt>
            <dd class="break-all text-tokyo-fg">{{ image.file_name }}</dd>
            <dt class="text-tokyo-dim">ID</dt>
            <dd class="text-tokyo-fg">{{ image.id }}</dd>
            <dt class="text-tokyo-dim">Tamanho</dt>
            <dd class="text-tokyo-fg">{{ formatSize(image.file_size) }}</dd>
            <dt class="text-tokyo-dim">Modificado</dt>
            <dd class="text-tokyo-fg">{{ formatTime(image.mtime) }}</dd>
            <dt class="text-tokyo-dim">Caminho</dt>
            <dd class="col-span-2 break-all font-mono text-tokyo-cyan">{{ image.file_path }}</dd>
          </dl>

          <section
          v-if="image.tags && image.tags.length > 0"
          class="flex flex-wrap gap-1.5"
        >
          <button
            v-for="tag in image.tags"
            :key="tag"
            type="button"
            class="rounded border border-tokyo-blue/50 bg-tokyo-blue/10 px-2 py-0.5 text-xs text-tokyo-blue transition hover:border-tokyo-blue hover:bg-tokyo-blue/25 hover:text-tokyo-fg"
            @click="emit('tag-click', tag)"
          >
            {{ tag }}
          </button>
        </section>

        <section class="rounded-lg border border-tokyo-green/30 bg-tokyo-bg-deep">
            <header class="flex items-center justify-between border-b border-tokyo-green/20 px-3 py-2">
              <h3 class="text-xs font-semibold text-tokyo-green">Prompt positivo</h3>
              <CopyButton :text="image.prompt_positivo" />
            </header>
            <pre class="whitespace-pre-wrap break-words p-3 text-xs text-tokyo-fg">{{ image.prompt_positivo || '—' }}</pre>
          </section>

          <section class="rounded-lg border border-tokyo-red/30 bg-tokyo-bg-deep">
            <header class="flex items-center justify-between border-b border-tokyo-red/20 px-3 py-2">
              <h3 class="text-xs font-semibold text-tokyo-red">Prompt negativo</h3>
              <CopyButton :text="image.prompt_negativo" />
            </header>
            <pre class="whitespace-pre-wrap break-words p-3 text-xs text-tokyo-fg">{{ image.prompt_negativo || '—' }}</pre>
          </section>

          <section class="rounded-lg border border-tokyo-purple/30 bg-tokyo-bg-deep">
            <header class="flex items-center justify-between border-b border-tokyo-purple/20 px-3 py-2">
              <h3 class="text-xs font-semibold text-tokyo-purple">Workflow</h3>
              <CopyButton :text="image.workflow_json" />
            </header>
            <pre class="whitespace-pre-wrap break-words p-3 text-xs text-tokyo-fg">{{ image.workflow_json || '—' }}</pre>
          </section>
        </div>
      </div>
    </aside>
  </div>
</template>
