<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { useUiStore } from './stores/ui'
import { useSearchStore } from './stores/search'
import SearchOverlay from './components/SearchOverlay.vue'

const ui = useUiStore()
const search = useSearchStore()
function onKey(e: KeyboardEvent) {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); search.toggle() }
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
const nav = [
  { to: '/', label: 'Дашборд' },
  { to: '/orders', label: 'Заказы' },
  { to: '/items', label: 'Товары' },
  { to: '/remnants', label: 'Остатки' },
  { to: '/prices', label: 'Цены' },
  { to: '/years', label: 'Годы' },
  { to: '/forecast', label: 'Прогноз' },
  { to: '/branches', label: 'Точки' },
  { to: '/heatmap', label: 'Тепловая' },
  { to: '/people', label: 'Люди' },
]
</script>

<template>
  <div class="layout">
    <aside class="sidebar">
      <div class="brand">Cinkoff Analytics</div>
      <RouterLink v-for="n in nav" :key="n.to" :to="n.to" class="nav-item">
        <span class="lbl">{{ n.label }}</span>
      </RouterLink>
      <div class="sidebar-foot">v2 · Vue3+Vite</div>
    </aside>
    <main class="main">
      <button class="theme-btn" @click="ui.toggleTheme()">{{ ui.theme === 'light' ? '☾' : '☀' }}</button>
      <RouterView />
      <div class="toasts">
        <div v-for="t in ui.toasts" :key="t.id" class="toast" :class="{ err: t.kind === 'err' }">{{ t.text }}</div>
      </div>
    </main>
    <SearchOverlay />
  </div>
</template>
