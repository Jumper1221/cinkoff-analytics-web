<script setup lang="ts">
import { computed, ref } from 'vue'
import { useApi, fmtMln } from '../api/client'
import type { HeatmapResp } from '../api/types'

const metric = ref<'orders' | 'revenue' | 'avg'>('revenue')
const h = useApi<HeatmapResp>(() => `/api/heatmap?metric=${metric.value}`)
watch(metric, () => h.load())
import { watch } from 'vue'

const MONTHS = ['янв', 'фев', 'мар', 'апр', 'май', 'июн', 'июл', 'авг', 'сен', 'окт', 'ноя', 'дек']

interface Cell { v: number; y: number; m: number; alpha: number }
const cells = computed<Cell[]>(() => {
  const d = h.data.value
  if (!d?.matrix) return []
  const all = Object.values(d.matrix).flat()
  const max = Math.max(...all, 1)
  const out: Cell[] = []
  for (const y of d.years) {
    const arr = d.matrix[String(y)] ?? []
    for (let m = 0; m < 12; m++) out.push({ v: arr[m] ?? 0, y, m: m + 1, alpha: (arr[m] ?? 0) / max })
  }
  return out
})
const bg = (c: Cell) => `color-mix(in srgb, var(--accent) ${Math.round(12 + c.alpha * 88)}%, transparent)`
const cellVal = (c: Cell) => (metric.value === 'orders' ? String(Math.round(c.v)) : fmtMln(c.v))
const curYear = computed(() => new Date().getFullYear())
</script>

<template>
  <h1>Тепловая карта</h1>
  <div class="panel">
    <div class="cmp-bar">
      <span class="muted">Метрика:</span>
      <label v-for="m in (['revenue','orders','avg'] as const)" :key="m" class="seg" :class="{ on: metric === m }">
        <input type="radio" :value="m" v-model="metric" />
        {{ { revenue: 'Выручка', orders: 'Заказы', avg: 'Ср.чек' }[m] }}
      </label>
    </div>
    <div v-if="h.loading.value" class="muted">Загрузка…</div>
    <div v-else-if="h.error.value" class="err-text">{{ h.error.value }}</div>
    <div v-else class="hm">
      <div class="hm-row hm-head">
        <div class="hm-ylab"></div>
        <div v-for="mn in MONTHS" :key="mn" class="hm-cell hm-mlab">{{ mn }}</div>
      </div>
      <div v-for="y in (h.data.value?.years ?? [])" :key="y" class="hm-row">
        <div class="hm-ylab" :class="{ cur: y === curYear }">{{ y }}</div>
        <div v-for="c in (cells.filter(c => c.y === y))" :key="c.m" class="hm-cell" :style="{ background: bg(c) }" :title="`${y}-${String(c.m).padStart(2, '0')}: ${cellVal(c)}`">
          {{ c.v ? cellVal(c) : '' }}
        </div>
      </div>
    </div>
  </div>
</template>
