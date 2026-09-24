<script setup lang="ts">
import { computed, ref, watch, type Ref } from 'vue'
import { useApi, fmtMoney } from '../api/client'
import { useChart, chartColors } from '../api/useChart'
import type { CatalogHit, PricePoint } from '../api/types'

const s = ref('')
const hits = ref<CatalogHit[]>([])
const searching = ref(false)
let tm: number | undefined
watch(s, (v) => {
  clearTimeout(tm)
  if (!v || v.length < 2) { hits.value = []; return }
  tm = window.setTimeout(async () => {
    searching.value = true
    try {
      const r = await fetch(`/api/catalog/search?s=${encodeURIComponent(v)}&limit=8`)
      hits.value = (await r.json()) as CatalogHit[]
    } finally { searching.value = false }
  }, 350)
})

const sel = ref<CatalogHit | null>(null)
const prices = useApi<PricePoint[]>(() => (sel.value ? `/api/catalog/price_history/${sel.value.id_1c}` : ''), false)
const dep = computed(() => prices.data.value)

const { canvas: cPrice } = useChart(() => {
  const d = prices.data.value
  if (!d?.length) return null
  const C = chartColors()
  // агрегат-по-филиалам: последняя-цена-на-филиал + разброс
  const byBranch = new Map<string, number[]>()
  for (const p of d) {
    if (!byBranch.has(p.branch)) byBranch.set(p.branch, [])
    byBranch.get(p.branch)!.push(p.discount_price)
  }
  const rows = [...byBranch.entries()].map(([b, arr]) => ({ b, min: Math.min(...arr), last: arr[arr.length - 1] })).sort((x, y) => x.last - y.last)
  const mins = rows.map(r => r.min), lasts = rows.map(r => r.last)
  return {
    type: 'bar',
    data: {
      labels: rows.map(r => r.b),
      datasets: [
        { label: 'Последняя (со скидкой)', data: lasts, backgroundColor: C.accent + '88', borderRadius: 3 },
        { type: 'line', label: 'Минимум за историю', data: mins, borderColor: C.err, pointRadius: 2, tension: 0.2 },
      ],
    },
    options: {
      indexAxis: 'y', maintainAspectRatio: false,
      scales: { x: { ticks: { color: C.muted }, grid: { color: C.border } }, y: { ticks: { color: C.text, font: { size: 10 } }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 10 } } },
    },
  } as any
}, dep as Ref<unknown>)

const spread = computed(() => {
  const d = prices.data.value
  if (!d?.length) return null
  const byB = new Map<string, number[]>()
  for (const p of d) { if (!byB.has(p.branch)) byB.set(p.branch, []); byB.get(p.branch)!.push(p.discount_price) }
  const lasts = [...byB.values()].map(a => a[a.length - 1])
  const mn = Math.min(...lasts), mx = Math.max(...lasts)
  return { mn, mx, pct: mn ? ((mx - mn) / mn * 100) : 0, n: lasts.length }
})
</script>

<template>
  <h1>Цены</h1>
  <div class="panel">
    <input v-model="s" class="f-search" style="width: 100%" placeholder="найти товар (от 2 букв) — например: штакетник" />
    <div v-if="searching" class="muted">Ищу…</div>
    <div v-if="hits.length" class="hits">
      <div v-for="h in hits" :key="h.id_1c" class="hit click" @click="sel = h; prices.load()">
        {{ h.full_name }}
      </div>
    </div>
  </div>
  <div v-if="sel" class="panel">
    <h3>{{ sel.full_name }}</h3>
    <div v-if="prices.loading.value" class="muted">История цен…</div>
    <div v-else-if="prices.error.value" class="err-text">{{ prices.error.value }}</div>
    <template v-else>
      <p v-if="spread" class="muted">
        Разброс-последних-цен по {{ spread.n }} филиалам: {{ fmtMoney(spread.mn) }} … {{ fmtMoney(spread.mx) }} ({{ spread.pct.toFixed(1) }}%)
      </p>
      <div class="chart-box tall"><canvas ref="cPrice" /></div>
    </template>
  </div>
</template>
