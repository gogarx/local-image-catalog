<script setup>
import { computed, ref } from 'vue'
import { apiUrl } from '../api/client'

const props = defineProps({
  item: { type: Object, required: true },
  active: { type: Boolean, default: false },
  reveladas: { type: Set, default: () => new Set() },
})
const emit = defineEmits(['select', 'reveal'])
const failed = ref(false)
const loaded = ref(false)
const ofuscada = computed(
  () => Boolean(props.item.is_nsfw) && !props.reveladas.has(props.item.id),
)
</script>

<template>
  <button
    type="button"
    class="group relative block w-full overflow-hidden rounded-lg border bg-tokyo-surface text-left transition hover:border-tokyo-blue focus:outline-none focus-visible:ring-2 focus-visible:ring-tokyo-blue"
    :class="active ? 'border-tokyo-blue ring-2 ring-tokyo-blue' : 'border-tokyo-border'"
    @click="emit('select', props.item.id)"
  >
    <div
      class="relative w-full overflow-hidden bg-tokyo-overlay"
      :class="loaded ? '' : 'min-h-32'"
    >
      <img
        v-if="!failed && props.item.media_url"
        :src="apiUrl(props.item.media_url)"
        :alt="props.item.file_name"
        loading="lazy"
        class="block w-full transition-all duration-300"
        :class="[
          loaded ? 'opacity-100' : 'opacity-0',
          ofuscada ? 'blur-xl select-none pointer-events-none' : '',
        ]"
        @load="loaded = true"
        @error="failed = true"
      />
      <div
        v-if="!loaded || failed"
        class="absolute inset-0 flex items-center justify-center p-3"
      >
        <span class="break-all text-center text-xs text-tokyo-dim">{{ props.item.file_name }}</span>
      </div>
      <div
        v-if="ofuscada"
        class="absolute inset-0 z-10 flex flex-col items-center justify-center bg-black/70 p-2 text-center text-xs"
        @click.stop
      >
        <span class="font-semibold tracking-widest text-tokyo-red">NSFW</span>
        <span class="mt-1 text-tokyo-dim">Conteúdo sensível</span>
        <span
          role="button"
          tabindex="0"
          class="mt-2 rounded border border-tokyo-border bg-tokyo-overlay px-2 py-0.5 text-tokyo-fg transition hover:border-tokyo-blue hover:text-tokyo-blue"
          @click.stop="emit('reveal', props.item.id)"
          @keydown.enter.stop="emit('reveal', props.item.id)"
        >
          Revelar
        </span>
      </div>
    </div>
    <span
      class="absolute inset-x-0 bottom-0 truncate bg-tokyo-bg-deep/80 px-2 py-1 text-xs text-tokyo-fg backdrop-blur-sm"
    >
      {{ props.item.file_name }}
    </span>
  </button>
</template>
