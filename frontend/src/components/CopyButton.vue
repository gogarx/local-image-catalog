<script setup>
import { ref } from 'vue'

const props = defineProps({
  text: { type: String, default: '' },
  label: { type: String, default: 'Copiar' },
})
const copied = ref(false)
let timer = null

async function copy() {
  const value = props.text ?? ''
  let ok = false
  if (navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(value)
      ok = true
    } catch {
      ok = false
    }
  }
  if (!ok) {
    ok = fallbackCopy(value)
  }
  if (ok) {
    copied.value = true
    clearTimeout(timer)
    timer = setTimeout(() => (copied.value = false), 1500)
  }
}

function fallbackCopy(value) {
  const area = document.createElement('textarea')
  area.value = value
  area.setAttribute('readonly', '')
  area.style.position = 'fixed'
  area.style.top = '0'
  area.style.left = '-9999px'
  area.style.opacity = '0'
  document.body.appendChild(area)
  area.focus()
  area.select()
  area.setSelectionRange(0, value.length)
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(area)
  return ok
}
</script>

<template>
  <button
    type="button"
    class="shrink-0 rounded border border-tokyo-border bg-tokyo-overlay px-2.5 py-1 text-xs text-tokyo-cyan transition hover:border-tokyo-cyan hover:text-tokyo-fg"
    :class="copied ? 'border-tokyo-green text-tokyo-green hover:border-tokyo-green' : ''"
    @click="copy"
  >
    {{ copied ? 'Copiado!' : label }}
  </button>
</template>
