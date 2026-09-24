<script setup lang="ts">
import { computed, ref, watch, type Ref } from 'vue'
import { useApi, fmtInt, fmtMoney, fmtDate } from '../api/client'
import { useChart, chartColors } from '../api/useChart'
import type { AbcRow, CatalogHit, PricePoint } from '../api/types'

const mode = ref<'top' | 'abc'>('top')
const q = ref('')
const days = ref(30)
const qs = computed(() => `/api/top/items?limit=30&days=${days.value}`)
const top = useApi<any[]>(() => qs.value)

const abc = useApi<AbcRow[]>(() => (mode.value === 'abc' ? '/api/abc?days=365' : ''), false)
watch(mode, (m) => { if (m === 'abc' && !abc.data.value) abc.load() })

const hit = ref<CatalogHit | null>(null)
const prices = useApi<PricePoint[]>(() => (hit.value ? `/api/catalog/prices/${hit.value.id_1c}` : ''), false)
const priceDep = computed(() => prices.data.value)
const { canvas: cPrice } = useChart(() => {
  const d = prices.data.value
  if (!d?.length || !hit.value) return null
  const C = chartColors()
  return {
    type: 'bar',
    data: {
      labels: d.map(p => p.branch),
      datasets: [
        { label: 'Цена', data: d.map(p => p.price), backgroundColor: C.muted + '66', borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'С нашей скидкой', data: d.map(p => p.discount_price), borderColor: C.accent, tension: 0.25, pointRadius: 3, yAxisID: 'y' },
      ],
    },
    options: {
      indexAxis: 'y', maintainAspectRatio: false,
      scales: { x: { ticks: { color: C.muted }, grid: { color: C.border } }, y: { ticks: { color: C.text, font: { size: 10 } }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 10 } } },
    },
  } as any
}, priceDep as Ref<unknown>)

const abcCls = (a: string) => (a === 'A' ? 'up' : a === 'C' ? 'down' : '')
const totalRev = computed(() => (abc.data.value ?? []).reduce((s, r) => s + (r.revenue || 0), 0))
</script>

<template>
  <h1>Товары</h1>
  <div class="panel">
    <div class="cmp-bar">
      <label class="seg" :class="{ on: mode === 'top' }"><input type="radio" value="top" v-model="mode" /> Топ-30, 30 дней</label>
      <label class="seg" :class="{ on: mode === 'abc' }"><input type="radio" value="abc" v-model="mode" /> ABC-анализ (365 дн)</label>
    </div>

    <div v-if="mode === 'top'">
      <div v-if="top.loading.value">
        <div v-for="r in 8" :key="r" class="skel skel-row" />
      </div>
      <div v-else-if="top.error.value" class="err-text">{{ top.error.value }}</div>
      <table v-else>
        <thead><tr><th>#</th><th>Товар</th><th class="num">Шт</th><th class="num">Выручка</th></tr></thead>
        <tbody>
          <tr v-for="(i, ix) in (top.data.value ?? [])" :key="ix" class="click" @click="hit = { id_1c: i.id_1c, full_name: i.name }; prices.load()">
            <td>{{ ix + 1 }}</td><td class="ellipsis" :title="i.name">{{ i.name }}</td>
            <td class="num">{{ (+i.units).toFixed(0) }}</td><td class="num">{{ fmtMoney(i.revenue) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else>
      <div v-if="abc.loading.value">
          <div v-for="r in 10" :key="r" class="skel skel-row" />
        </div>
      <div v-else-if="abc.error.value" class="err-text">{{ abc.error.value }}</div>
      <template v-else>
        <p class="muted">A — 80% выручки, B — след. 15%, C — хвост 5%. Всего: {{ fmtMoney(totalRev) }} за 365 дн</p>
        <table>
          <thead><tr><th>#</th><th>Товар</th><th class="num">Выручка</th><th class="num">Шт</th><th class="num">Доля</th><th class="num">Кум.доля</th><th>Класс</th></tr></thead>
          <tbody>
            <tr v-for="(r, ix) in (abc.data.value ?? [])" :key="ix">
              <td>{{ ix + 1 }}</td><td class="ellipsis" :title="r.name">{{ r.name }}</td>
              <td class="num">{{ fmtMoney(r.revenue) }}</td><td class="num">{{ (+r.units).toFixed(0) }}</td>
              <td class="num">{{ r.share_pct.toFixed(1) }}%</td><td class="num">{{ r.cum_share_pct.toFixed(1) }}%</td>
              <td><span class="badge" :class="abcCls(r.abc)">{{ r.abc }}</span></td>
            </tr>
          </tbody>
        </table>
      </template>
    </div>
  </div>

  <Teleport to="body">
    <div v-if="hit" class="mask" @click.self="hit = null">
      <div class="modal">
        <button class="x" @click="hit = null">✕</button>
        <h2>{{ hit.full_name }}</h2>
        <div v-if="prices.loading.value" class="muted">Цены…</div>
        <div v-else-if="prices.error.value" class="err-text">{{ prices.error.value }}</div>
        <div v-else class="chart-box"><canvas ref="cPrice" /></div>
      </div>
    </div>
  </Teleport>
</template>
