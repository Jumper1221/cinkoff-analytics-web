<script setup lang="ts">
import { computed, type Ref } from 'vue'
import { useApi, fmtInt, fmtMoney, fmtMln } from '../api/client'
import { useChart, chartColors } from '../api/useChart'
import type { YearRow } from '../api/types'

const years = useApi<YearRow[]>(() => '/api/years')
const dep = computed(() => years.data.value)

const { canvas: cYears } = useChart(() => {
  const d = years.data.value; if (!d?.length) return null
  const C = chartColors()
  return {
    type: 'bar',
    data: {
      labels: d.map(y => y.year),
      datasets: [
        { label: 'Выручка, млн (исполненные)', data: d.map(y => +(y.revenue / 1e6).toFixed(1)), backgroundColor: C.accent + '88', borderRadius: 3 },
        { type: 'line', label: 'Заказов', data: d.map(y => y.cnt), borderColor: C.ok, tension: 0.3, pointRadius: 2, yAxisID: 'y2' },
      ],
    },
    options: {
      maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: {
        y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
        y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
        x: { ticks: { color: C.muted }, grid: { display: false } },
      },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } },
    },
  } as any
}, dep as Ref<unknown>)

const withPct = computed(() => (years.data.value ?? []).map(y => ({
  ...y, donePct: y.cnt ? (y.done_cnt / y.cnt * 100) : 0,
})))
</script>

<template>
  <h1>Годы</h1>
  <div class="panel">
    <h3>Выручка по годам (только исполненные: «Машина отгружена» + «Отгружен»)</h3>
    <div v-if="years.loading.value"><div v-for="r in 6" :key="r" class="skel skel-row" /></div>
    <div v-else-if="years.error.value" class="err-text">{{ years.error.value }}</div>
    <div v-else class="chart-box"><canvas ref="cYears" /></div>
  </div>
  <div class="panel">
    <table>
      <thead><tr><th>Год</th><th class="num">Заказов</th><th class="num">Исполнено</th><th class="num">% исполн.</th><th class="num">Выручка</th><th class="num">Ср. чек</th></tr></thead>
      <tbody>
        <tr v-for="y in withPct" :key="y.year">
          <td>{{ y.year }}</td>
          <td class="num">{{ fmtInt(y.cnt) }}</td>
          <td class="num">{{ fmtInt(y.done_cnt) }}</td>
          <td class="num">{{ y.donePct.toFixed(0) }}%</td>
          <td class="num">{{ fmtMln(y.revenue) }}</td>
          <td class="num">{{ fmtMoney(y.avg_check) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
