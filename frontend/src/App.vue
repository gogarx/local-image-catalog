<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import SearchBar from './components/SearchBar.vue'
import ImageGrid from './components/ImageGrid.vue'
import ImageViewer from './components/ImageViewer.vue'
import DetailPanel from './components/DetailPanel.vue'
import { fetchImage, fetchImages, searchImages } from './api/catalog'

const PAGE_SIZE = 24
const query = ref('')
const page = ref(0)
const items = ref([])
const total = ref(0)
const loading = ref(false)
const error = ref('')
const selectedImage = ref(null)
const selectedImageId = ref(null)
const loadingDetail = ref(false)
const detailError = ref('')
const detailOpen = ref(false)
const reveladas = reactive(new Set())

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / PAGE_SIZE)))
const searching = computed(() => query.value.trim().length > 0)
const viewerOpen = computed(
  () => loadingDetail.value || selectedImage.value !== null || detailError.value !== '',
)

let requestSeq = 0
let detailSeq = 0
let lastWheel = 0

async function load() {
  const seq = ++requestSeq
  loading.value = true
  const offset = page.value * PAGE_SIZE
  const term = query.value.trim()
  try {
    const data = term
      ? await searchImages(term, { limit: PAGE_SIZE, offset })
      : await fetchImages({ limit: PAGE_SIZE, offset })
    if (seq !== requestSeq) return
    items.value = data.items
    total.value = data.total
    error.value = ''
  } catch (err) {
    if (seq !== requestSeq) return
    items.value = []
    total.value = 0
    error.value = err.message
  } finally {
    if (seq === requestSeq) loading.value = false
  }
}

function onSearch(term) {
  if (term === query.value) return
  query.value = term
  page.value = 0
  load()
}

function goPrev() {
  if (page.value > 0) {
    page.value -= 1
    load()
  }
}

function goNext() {
  if (page.value + 1 < pageCount.value) {
    page.value += 1
    load()
  }
}

async function openDetail(imageId) {
  const seq = ++detailSeq
  selectedImageId.value = imageId
  selectedImage.value = null
  detailError.value = ''
  loadingDetail.value = true
  detailOpen.value = false
  try {
    const data = await fetchImage(imageId)
    if (seq !== detailSeq) return
    selectedImage.value = data
  } catch (err) {
    if (seq !== detailSeq) return
    detailError.value = err.message
  } finally {
    if (seq === detailSeq) loadingDetail.value = false
  }
}

function closePanel() {
  detailSeq += 1
  selectedImage.value = null
  selectedImageId.value = null
  loadingDetail.value = false
  detailError.value = ''
  detailOpen.value = false
  if (document.activeElement instanceof HTMLElement) {
    document.activeElement.blur()
  }
}

function toggleDetails() {
  detailOpen.value = !detailOpen.value
}

function closeDetails() {
  detailOpen.value = false
}

function showPrev() {
  if (selectedImageId.value === null || items.value.length === 0) return
  const index = items.value.findIndex((item) => item.id === selectedImageId.value)
  if (index > 0) openDetail(items.value[index - 1].id)
}

function showNext() {
  if (selectedImageId.value === null || items.value.length === 0) return
  const index = items.value.findIndex((item) => item.id === selectedImageId.value)
  if (index !== -1 && index < items.value.length - 1) {
    openDetail(items.value[index + 1].id)
  }
}

function onTagClick(tag) {
  closePanel()
  query.value = tag
  page.value = 0
  load()
}

function revelarImagem(imageId) {
  reveladas.add(imageId)
}

function onWheel(event) {
  if (!viewerOpen.value || detailOpen.value) return
  if (event.timeStamp - lastWheel < 200) return
  if (event.deltaY < 0) {
    lastWheel = event.timeStamp
    showPrev()
  } else if (event.deltaY > 0) {
    lastWheel = event.timeStamp
    showNext()
  }
}

function onKeydown(event) {
  if (event.key !== 'Escape') return
  if (detailOpen.value) {
    closeDetails()
    return
  }
  if (viewerOpen.value) closePanel()
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('wheel', onWheel, { passive: true })
  load()
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('wheel', onWheel)
})
</script>

<template>
  <div class="flex h-screen flex-col overflow-hidden">
    <header class="border-b border-tokyo-border bg-tokyo-bg-deep">
      <div class="mx-auto flex max-w-7xl items-center gap-4 px-4 py-3">
        <h1 class="hidden text-lg font-semibold tracking-tight text-tokyo-blue md:block">
          local-image-catalog
        </h1>
        <SearchBar class="flex-1" :model-value="query" @search="onSearch" />
        <span class="hidden shrink-0 text-xs text-tokyo-dim sm:block">
          {{ total }} {{ searching ? 'resultados' : 'imagens' }}
        </span>
      </div>
    </header>

    <main class="flex-1 overflow-y-auto">
      <div class="mx-auto w-full max-w-7xl px-4 py-4">
        <p
          v-if="error"
          class="rounded-lg border border-tokyo-red/40 bg-tokyo-red/10 px-4 py-3 text-sm text-tokyo-red"
        >
          {{ error }}
        </p>
        <ImageGrid
          v-else
          :items="items"
          :loading="loading"
          :page="page"
          :page-count="pageCount"
          :selected-id="selectedImageId"
          :searching="searching"
          :reveladas="reveladas"
          @select="openDetail"
          @prev="goPrev"
          @next="goNext"
          @reveal="revelarImagem"
        />
      </div>
    </main>

    <ImageViewer
      :open="viewerOpen"
      :image="selectedImage"
      :loading="loadingDetail"
      :error="detailError"
      @close="closePanel"
      @toggle-details="toggleDetails"
    />

    <DetailPanel
      :open="detailOpen"
      :image="selectedImage"
      :loading="loadingDetail"
      :error="detailError"
      @close="closeDetails"
      @tag-click="onTagClick"
    />
  </div>
</template>
