<script setup lang="ts">
import { computed, ref, watch, type Ref } from 'vue'
import { useApi, fmtInt, fmtMoney, fmtMln } from '../api/client'
import { useChart, chartColors } from '../api/useChart'
import type { MonthlyRow, StatusRow, TopItem, TopContractor, LeadRow, CancelRow, CompareRow } from '../api/types'

const kpi = useApi<any>(() => '/api/kpi')
const months = useApi<MonthlyRow[]>(() => '/api/monthly?months=12')
const statuses = useApi<StatusRow[]>(() => '/api/status_breakdown')
const topItems = useApi<TopItem[]>(() => '/api/top/items?limit=8&days=30')
const topCntr = useApi<TopContractor[]>(() => '/api/top/contractors?limit=5&days=30')
const lead = useApi<LeadRow[]>(() => '/api/leadtime?months=12')
const cancels = useApi<CancelRow[]>(() => '/api/cancel_rate?months=12')

// ── месяцы: bar-выручка + line-заказов
const monthsData = computed(() => months.data)
const { canvas: cMonths } = useChart(() => {
  const d = months.data.value; if (!d?.length) return null
  const C = chartColors()
  return {
    type: 'bar',
    data: {
      labels: d.map(m => `${m.year}-${String(m.month).padStart(2, '0')}`),
      datasets: [
        { label: 'Выручка, млн', data: d.map(m => +(m.total / 1e6).toFixed(2)), backgroundColor: C.accent + '88', borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'Заказов', data: d.map(m => m.cnt), borderColor: C.ok, tension: 0.3, pointRadius: 2, yAxisID: 'y2' },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      scales: {
        y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
        y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
        x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } },
      },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } },
    },
  } as any
}, monthsData as Ref<unknown>)

// ── статусы: doughnut
const stData = computed(() => statuses.data)
const { canvas: cStatus } = useChart(() => {
  const d = statuses.data.value; if (!d?.length) return null
  const C = chartColors()
  const palette = [C.accent, C.err, C.ok, '#f0a13c', '#8e6fc1', '#3bb0c9', '#c767a5', C.muted]
  return {
    type: 'doughnut',
    data: { labels: d.map(s => s.status), datasets: [{ data: d.map(s => s.cnt), backgroundColor: palette, borderWidth: 0 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { position: 'right', labels: { color: C.text, boxWidth: 10, font: { size: 10 } } } } },
  } as any
}, stData as Ref<unknown>)

// ── скорость+отмены (bar-медиана, line-p90, line-%отмен)
const opsDep = computed(() => [lead.data, cancels.data])
const { canvas: cOps } = useChart(() => {
  const l = lead.data.value, c = cancels.data.value
  if (!l?.length || !c?.length) return null
  const C = chartColors()
  return {
    data: {
      labels: l.map(x => x.label),
      datasets: [
        { type: 'bar', label: 'Медиана, дней', data: l.map(x => +(x.median_days).toFixed(1)), backgroundColor: C.accent + '88', borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'p90, дней', data: l.map(x => +(x.p90_days).toFixed(1)), borderColor: '#f0a13c', tension: 0.3, pointRadius: 2, yAxisID: 'y' },
        { type: 'line', label: '% отмен', data: c.map(x => x.pct), borderColor: C.err, tension: 0.3, pointRadius: 2, yAxisID: 'y2' },
      ],
    },
    options: {
      maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: {
        y: { position: 'left', title: { display: true, text: 'дней' }, ticks: { color: C.muted }, grid: { color: C.border } },
        y2: { position: 'right', title: { display: true, text: '% отмен' }, ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
        x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } },
      },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } },
    },
  } as any
}, opsDep as Ref<unknown>)

// ── сравнение периодов
const cmpKind = ref<'month' | 'quarter' | 'year'>('month')
const cmpAnchor = ref('2026-09')
const cmp = useApi<CompareRow[]>(() => `/api/compare?period=${cmpKind.value}&anchor=${cmpAnchor.value}&steps=2`)
watch([cmpKind, cmpAnchor], () => cmp.load())
const rows = computed(() => (cmp.data.value ?? []).slice(1)) // [0]-сам-якорь, дальше-дельты-в-строках

const topItemsRows = computed(() => topItems.data.value ?? [])
const topCntrRows = computed(() => topCntr.data.value ?? [])
const deltas = computed(() => (cmp.data.value ?? []).filter((r: CompareRow) => r.p_orders !== undefined).map((r: CompareRow) => ({
  label: r.label, orders: r.orders, revenue: r.revenue,
  pOrders: r.p_orders!, pRevenue: r.p_revenue!, dRev: r.d_revenue!,
  cancels: r.canceled, cancelPct: r.orders ? (r.canceled / r.orders * 100) : 0,
})))
const arrow = (p: number) => (p > 0 ? '▲' : p < 0 ? '▼' : '·')
const signCls = (p: number) => (p > 0 ? 'up' : p < 0 ? 'down' : '')
</script>

<template>
  <h1>Дашборд</h1>

  <div v-if="kpi.loading.value" class="kpis">
    <div v-for="i in 4" :key="i" class="panel kpi"><div class="v skel"></div><div class="l">…</div></div>
  </div>
  <div v-else-if="kpi.error.value" class="panel err-text">{{ kpi.error.value }}</div>
  <div v-else class="kpis">
    <div class="panel kpi"><div class="v">{{ fmtInt(kpi.data.value?.orders_today) }}</div><div class="l">Заказов сегодня</div></div>
    <div class="panel kpi"><div class="v">{{ fmtInt(kpi.data.value?.orders_30d) }}</div><div class="l">Заказов, 30 дней</div></div>
    <div class="panel kpi"><div class="v">{{ fmtMoney(kpi.data.value?.sum_30d) }}</div><div class="l">Выручка, 30 дней</div></div>
    <div class="panel kpi"><div class="v">{{ fmtMoney(kpi.data.value?.avg_30) }}</div><div class="l">Ср. чек, 30 дней</div></div>
  </div>

  <div class="panel">
    <h3>Сравнение периодов</h3>
    <div class="cmp-bar">
      <label v-for="k in (['month','quarter','year'] as const)" :key="k" class="seg" :class="{ on: cmpKind === k }">
        <input type="radio" :value="k" v-model="cmpKind" /> {{ { month: 'Месяц', quarter: 'Квартал', year: 'Год' }[k] }}
      </label>
      <input class="anchor" type="month" v-model="cmpAnchor" @change="cmp.load()" />
    </div>
    <div v-if="cmp.loading.value" class="muted">Считаю…</div>
    <div v-else-if="cmp.error.value" class="err-text">{{ cmp.error.value }}</div>
    <table v-else-if="deltas.length">
      <thead><tr><th>Период</th><th class="num">Заказов</th><th class="num">Δ%</th><th class="num">Выручка</th><th class="num">Δ выручки</th><th class="num">% отмен</th></tr></thead>
      <tbody>
        <tr v-for="d in deltas" :key="d.label">
          <td>{{ d.label }}</td>
          <td class="num">{{ fmtInt(d.orders) }}</td>
          <td class="num" :class="signCls(d.pOrders)">{{ arrow(d.pOrders) }} {{ Math.abs(d.pOrders).toFixed(1) }}%</td>
          <td class="num">{{ fmtMln(d.revenue) }}</td>
          <td class="num" :class="signCls(d.pRevenue)">{{ arrow(d.pRevenue) }} {{ (Math.abs(d.dRev) / 1e6).toFixed(2) }} млн</td>
          <td class="num">{{ d.cancelPct.toFixed(1) }}%</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="panel">
    <h3>Месяцы: выручка и заказы</h3>
    <div class="chart-box"><canvas ref="cMonths" /></div>
  </div>

  <div class="cols">
    <div class="panel">
      <h3>Статусы заказов (всего)</h3>
      <div class="chart-box sq"><canvas ref="cStatus" /></div>
    </div>
    <div class="panel">
      <h3>Скорость: дни заказ→отгрузка + % отмен</h3>
      <div class="chart-box"><canvas ref="cOps" /></div>
    </div>
  </div>

  <div class="cols">
    <div class="panel">
      <h3>Топ товаров, 30 дней</h3>
      <table>
        <thead><tr><th>Товар</th><th class="num">Шт</th><th class="num">Сумма</th></tr></thead>
        <tbody>
          <tr v-for="i in topItemsRows" :key="i.name">
            <td class="ellipsis" :title="i.name">{{ i.name }}</td>
            <td class="num">{{ (+i.units).toFixed(0) }}</td>
            <td class="num">{{ fmtMoney(i.revenue) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="panel">
      <h3>Топ контрагентов, 30 дней</h3>
      <table>
        <thead><tr><th>Контрагент</th><th class="num">Заказов</th><th class="num">Сумма</th></tr></thead>
        <tbody>
          <tr v-for="c in topCntrRows" :key="c.name">
            <td>{{ c.name }}</td><td class="num">{{ fmtInt(c.orders) }}</td><td class="num">{{ fmtMoney(c.revenue) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>
