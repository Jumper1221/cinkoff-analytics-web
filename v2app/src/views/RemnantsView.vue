<script setup lang="ts">
import { computed, ref, watch, type Ref } from 'vue'
import { useApi, fmtInt } from '../api/client'
import { useChart, chartColors } from '../api/useChart'
import type { RemRow, RemDates, RemHistPoint } from '../api/types'

const dates = useApi<RemDates>(() => '/api/remnants/dates')
const snapDate = ref('')
watch(dates.data, (d) => { if (d?.dates?.length && !snapDate.value) snapDate.value = d.dates[0] })

const qs = computed(() => `/api/remnants?limit=100&date=${snapDate.value || ''}`)
const rem = useApi<RemRow[]>(() => qs.value)
watch(snapDate, () => rem.load())

const hist = useApi<{ dates: string[]; series: Record<string, RemHistPoint[]> }>(() => '/api/remnants/history')
const histDep = computed(() => hist.data.value)
const KINDS: Record<string, string> = { goods: 'Товары', metall: 'Металл', delivery: 'Доставка', service: 'Услуги' }
const KIND_COLORS: Record<string, string> = { goods: '#1a66ff', metall: '#f0a13c', delivery: '#188a4c', service: '#8e6fc1' }

const { canvas: cHist } = useChart(() => {
  const h = hist.data.value
  if (!h?.series) return null
  const C = chartColors()
  const kinds = Object.keys(h.series)
  return {
    type: 'line',
    data: {
      labels: h.dates,
      datasets: kinds.map(k => ({
        label: KINDS[k] ?? k,
        data: h.series[k].map((p: RemHistPoint) => +((p.qty || 0) / 1e6).toFixed(3)),
        borderColor: KIND_COLORS[k] ?? C.accent,
        backgroundColor: (KIND_COLORS[k] ?? C.accent) + '22',
        tension: 0.25, pointRadius: 3, fill: true,
      })),
    },
    options: {
      maintainAspectRatio: false,
      scales: { y: { title: { display: true, text: 'млн шт' }, ticks: { color: C.muted }, grid: { color: C.border } }, x: { ticks: { color: C.muted }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } },
    },
  } as any
}, histDep as Ref<unknown>)
</script>

<template>
  <h1>Остатки</h1>
  <div class="panel">
    <h3>Динамика по видам (по всем снапшотам: {{ (hist.data.value?.dates ?? []).length }})</h3>
    <div v-if="hist.loading.value"><div class="skel" style="height: 300px" /></div>
    <div v-else-if="hist.error.value" class="err-text">{{ hist.error.value }}</div>
    <div v-else class="chart-box"><canvas ref="cHist" /></div>
  </div>
  <div class="panel">
    <div class="cmp-bar">
      <span class="muted">Снапшот:</span>
      <select v-model="snapDate" class="anchor">
        <option v-for="d in (dates.data.value?.dates ?? [])" :key="d" :value="d">{{ d }}</option>
      </select>
    </div>
    <div v-if="rem.loading.value"><div v-for="r in 10" :key="r" class="skel skel-row" /></div>
    <div v-else-if="rem.error.value" class="err-text">{{ rem.error.value }}</div>
    <table v-else>
      <thead><tr><th>Товар</th><th>Филиал</th><th class="num">Кол-во</th><th>Приход</th></tr></thead>
      <tbody>
        <tr v-for="(r, ix) in (rem.data.value ?? [])" :key="ix">
          <td class="ellipsis" :title="r.full_name ?? r.nomenclature_id">{{ r.full_name ?? r.nomenclature_id }}</td>
          <td>{{ r.branch }}</td><td class="num">{{ fmtInt(r.qty) }}</td>
          <td>{{ r.delivery_date ? r.delivery_date.slice(0, 10) : '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
