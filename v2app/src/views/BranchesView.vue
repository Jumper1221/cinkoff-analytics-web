<script setup lang="ts">
import { computed, type Ref } from 'vue'
import { useApi, fmtInt, fmtMln } from '../api/client'
import { useChart, chartColors } from '../api/useChart'
import type { CohortsResp } from '../api/types'

const co = useApi<CohortsResp>(() => '/api/cohorts')
const dep = computed(() => co.data.value)

const { canvas: cActive } = useChart(() => {
  const d = co.data.value
  if (!d?.active_by_month?.length) return null
  const C = chartColors()
  const last = d.active_by_month.slice(-24)
  return {
    type: 'bar',
    data: {
      labels: last.map(a => a.month),
      datasets: [
        { label: 'Заказов', data: last.map(a => a.orders_cnt), backgroundColor: C.accent + '88', borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'Активных точек', data: last.map(a => a.active_branches), borderColor: C.ok, tension: 0.3, pointRadius: 2, yAxisID: 'y2' },
      ],
    },
    options: {
      maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: {
        y: { title: { display: true, text: 'заказов' }, ticks: { color: C.muted }, grid: { color: C.border } },
        y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
        x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } },
      },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } },
    },
  } as any
}, dep as Ref<unknown>)

const { canvas: cRet } = useChart(() => {
  const d = co.data.value
  if (!d?.retention?.length) return null
  const C = chartColors()
  const last = d.retention.slice(-24)
  return {
    type: 'line',
    data: {
      labels: last.map(r => r.month),
      datasets: [{ label: '% вернувшихся (3 мес)', data: last.map(r => (r.branches_this_m ? (r.returned_next3 / r.branches_this_m * 100) : 0)), borderColor: C.accent, tension: 0.3, pointRadius: 2 }],
    },
    options: {
      maintainAspectRatio: false,
      scales: { y: { title: { display: true, text: '%' }, ticks: { color: C.muted }, grid: { color: C.border } }, x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } },
    },
  } as any
}, dep as Ref<unknown>)
</script>

<template>
  <h1>Точки</h1>
  <div class="panel">
    <h3>Топ точек за 12 мес (по выручке исполненных)</h3>
    <table>
      <thead><tr><th>Точка</th><th class="num">Заказов</th><th class="num">Выручка</th></tr></thead>
      <tbody>
        <tr v-for="b in (co.data.value?.top_branches ?? [])" :key="b.branch">
          <td>{{ b.branch }}</td><td class="num">{{ fmtInt(b.orders_cnt) }}</td><td class="num">{{ fmtMln(b.revenue) }}</td>
        </tr>
      </tbody>
    </table>
  </div>
  <div class="panel">
    <h3>Активность по месяцам (24 мес)</h3>
    <div v-if="co.loading.value"><div class="skel" style="height: 300px" /></div>
    <div v-else class="chart-box"><canvas ref="cActive" /></div>
  </div>
  <div class="panel">
    <h3>Retention: возвращаемость точек через 3 мес</h3>
    <div v-if="co.loading.value"><div class="skel" style="height: 300px" /></div>
    <div v-else class="chart-box"><canvas ref="cRet" /></div>
  </div>
</template>
