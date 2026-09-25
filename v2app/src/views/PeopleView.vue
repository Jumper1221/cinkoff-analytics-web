<script setup lang="ts">
import { computed, ref, watch, type Ref } from 'vue'
import { useApi, fmtInt, fmtMln, fmtMoney } from '../api/client'
import { useChart, chartColors } from '../api/useChart'

// ── состояние: период, выбор-человека, режим-сравнения ──
const months = ref(12)
const selected = ref('')
const cmpPeople = ref<string[]>([])
const cmpMode = ref(false)

interface SumResp {
  period_months: number
  summary: { person: string; deals_total: number; revenue_mln: number; deals_per_month: number; first_month: string }[]
  by_month: Record<string, { month: string; deals: number; revenue: number }[]>
}
interface MonthResp {
  monthly: { month: string; deals: number; revenue: number; avg_check: number }[]
  prev_year_same_month: { pm: string; deals: number; revenue: number; avg_check: number }[]
}
interface CompareResp { months: string[]; series: Record<string, { month: string; deals: number; revenue: number }[]> }

const sum = useApi<any>(() => `/api/people/summary?months=${months.value}`)
const detail = useApi<MonthRespExtra>(() => (selected.value ? `/api/people/monthly?person=${encodeURIComponent(selected.value)}&months=${months.value}` : ''), false)
type MonthRespExtra = MonthResp
interface MonthResp { person: string; months: number; monthly: MonthRow[]; prev_year_same_month: PYRow[] }
interface MonthRow { month: string; deals: number; revenue: number; avg_check: number }
interface PYRow { pm: string; deals: number; revenue: number; avg_check: number }

const cmpApi = useApi<CompareResp>(() => (cmpMode.value && cmpPeople.value.length >= 1
  ? `/api/people/compare?people=${cmpPeople.value.map(encodeURIComponent).join(';')}&months=${months.value}` : ''), false)
interface CompareRespX { months: string[]; series: Record<string, MonthDeal[]> }
interface MonthDeal { month: string; deals: number; revenue: number }

const dep = computed(() => [sum.data.value, months.value] as unknown)
const depD = computed(() => [detail.data.value, selected.value, months.value] as unknown)
const depC = computed(() => [cmpApi.data.value, cmpPeople.value] as unknown)

const persons = computed(() => (sum.data.value?.summary ?? []).map((s: any) => s.person))
watch(persons, (ps) => {
  if (!selected.value && ps.length) selected.value = ps[0]
  if (cmpPeople.value.length === 0 && ps.length) {
    cmpPeople.value = ps.slice(0, 3) // топ-3-по-умолчанию
    cmpMode.value = true
  }
})

function shortName(full: string): string {
  const p = (full || '').split(' ')
  return p.length >= 3 ? `${p[0]} ${p[1][0]}.${p[2][0]}.` : (full || '—')
}

// ── график-1: топ-людей (выручка-за-период) ──
const { canvas: cTop } = useChart(() => {
  const s = (sum.data.value?.summary ?? []).slice(0, 10)
  if (!s.length) return null
  const C = chartColors()
  return {
    type: 'bar',
    data: { labels: (s as any[]).map(r => shortName(r.person)),
      datasets: [{ label: 'Выручка, млн', data: (s as any[]).map(r => r.revenue_mln), backgroundColor: C.accent + 'CC', borderRadius: 4 }] },
    options: { maintainAspectRatio: false, scales: { y: { ticks: { color: C.muted }, grid: { color: C.border } }, x: { ticks: { color: C.muted, autoSkip: false, maxRotation: 35 }, grid: { display: false } } }, plugins: { legend: { display: false } } },
  } as any
}, dep as Ref<unknown>)

// ── график-2: помесячная-динамика-выбранного-человека + прошлый-год-в-тот-же-месяц ──
const { canvas: cPerson } = useChart(() => {
  const d = detail.data.value
  if (!d?.monthly?.length) return null
  const C = chartColors()
  const labels = d.monthly.map((m: MonthRow) => m.month)
  const pyMap: Record<string, MonthRow> = {}
  for (const r of (d.prev_year_same_month ?? []) as PYRow[]) pyMap[r.pm] = { month: r.pm, deals: r.deals, revenue: r.revenue, avg_check: r.avg_check }
  return {
    type: 'bar',
    data: { labels,
      datasets: [
        { type: 'bar', label: 'Выручка, млн', data: d.monthly.map((m: MonthRow) => +(m.revenue / 1e6).toFixed(2)), backgroundColor: C.accent + 'CC', borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'Сделок', data: d.monthly.map((m: MonthRow) => m.deals), borderColor: C.ok, tension: 0.3, pointRadius: 2, yAxisID: 'y2' },
        { type: 'line', label: 'Тот-же-месяц-год-назад (млн)', data: labels.map(l => +((pyMap[l]?.revenue ?? 0) / 1e6).toFixed(2)), borderColor: C.muted, borderDash: [5, 4], tension: 0.25, pointRadius: 1.5, yAxisID: 'y' },
      ] },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: { y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
                y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
                x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
  } as any
}, depD as Ref<unknown>)

// ── график-3: сравнение-людей ──
const cmpPalette = ['#3b82f6', '#16a34a', '#f59e0b', '#a855f7', '#ef4444']
const { canvas: cCmp } = useChart(() => {
  const d = cmpApi.data.value as CompareResp | null
  if (!d?.months?.length || !d?.series) return null
  const C = chartColors()
  const people = Object.keys(d.series)
  if (!people.length) return null
  return {
    type: 'line',
    data: { labels: d.months,
      datasets: people.map((p, i) => ({ label: shortName(p), data: (d.series[p] || []).map(x => +(x.revenue / 1e6).toFixed(2)), borderColor: cmpPalette[i % 6], backgroundColor: cmpPalette[i % 6] + '55', tension: 0.3, pointRadius: 2, fill: i === 0 ? false : false })) },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: { y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
                x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
  } as any
}, dep as unknown as Ref<unknown>)

// сравнение-таблица: последний-месяц-vs-предыдущий-и-год-к-году
const cmpTable = computed(() => {
  const d = cmpApi.data.value as CompareResp | null
  if (!d?.months?.length) return []
  const lm = d.months[d.months.length - 1]
  const prev = d.months[d.months.length - 2] || lm
  const lmPrevYear = (() => { // тот-же-месяц-год-назад
    const [y, m] = lm.split('-').map(Number)
    return `${y - 1}-${String(m).padStart(2, '0')}`
  })()
  return Object.keys(d.series).map(p => {
    const find = (mm: string) => (d.series[p] || []).find(x => x.month === mm)
    const a = (find(lm)?.revenue ?? 0), b = (find(prev)?.revenue ?? 0), c = (find(lmPrevYear)?.revenue ?? 0)
    const dMoM = b ? +(((a - b) / b) * 100).toFixed(0) : (a ? 100 : 0)
    const dYoY = c ? +(((a - c) / c) * 100).toFixed(0) : (a ? 100 : 0)
    return { person: p, rev: a, deals: find(lm)?.deals ?? 0, dMoM, dYoY }
  }).sort((x, y) => y.rev - x.rev)
})

const fmtShortMonth = (iso: string) => {
  if (!iso) return '—'
  const [y, m] = iso.split('-')
  const names = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
  return `${names[+m - 1]} ${y}`
}
</script>

<template>
  <h1>Люди (продажи)</h1>

  <div class="panel">
    <div class="hdr-row">
      <h3>Выручка по ответственным (отгруженные заказы)</h3>
      <label class="period">
        Период:
        <select v-model.number="months" class="p-select">
          <option :value="6">6 мес</option><option :value="12">12 мес</option>
          <option :value="24">24 мес</option><option :value="36">36 мес</option><option :value="60">Всё</option>
        </select>
      </label>
    </div>
    <div class="chart-box" style="height: 300px"><canvas ref="cTop"></canvas></div>
    <table>
      <thead><tr><th>Ответственный</th><th class="num">Сделок</th><th class="num">В-среднем/мес</th><th class="num">Выручка</th></tr></thead>
      <tbody>
        <tr v-for="s in (sum.data.value?.summary ?? [])" :key="s.person" class="click" @click="selected = s.person; cmpMode = false">
          <td>{{ s.person }}</td>
          <td class="num">{{ fmtInt(s.deals_total) }}</td>
          <td class="num">{{ s.deals_per_month.toFixed(1) }}</td>
          <td class="num">{{ fmtMln(s.revenue_mln * 1e6) }}</td>
        </tr>
        <tr v-if="!sum.loading.value && !sum.data.value?.summary?.length"><td colspan="4" class="empty">Нет-отгруженных-заказов-с-ответственным-за-период</td></tr>
      </tbody>
    </table>
    <p class="hint">Продажа = заказ со-ставленной-датой-отгрузки (исполненный). Клик-по-человеку —- его-помесячная-динамика ниже.</p>
  </div>

  <div class="panel" v-if="selected && !cmpMode">
    <div class="hdr-row">
      <h3>{{ selected }} —- помесячно ({{ months }} мес)</h3>
      <button class="chip-ghost" @click="cmpMode = true">← к-сравнению</button>
    </div>
    <div class="chart-box" style="height: 320px"><canvas ref="cPerson"></canvas></div>
    <table v-if="detail.data.value?.monthly?.length">
      <thead><tr><th>Месяц</th><th class="num">Сделок</th><th class="num">Выручка</th><th class="num">Средний-чек</th><th class="num">Год-к-году</th></tr></thead>
      <tbody>
        <tr v-for="(m, i) in detail.data.value.monthly" :key="m.month">
          <td>{{ m.month.slice(0, 7) }}</td>
          <td class="num">{{ fmtInt(m.deals) }}</td>
          <td class="num">{{ fmtMln(m.revenue) }}</td>
          <td class="num">{{ fmtMln(m.avg_check) }}</td>
          <td class="num" v-if="detail.data.value.prev_year_same_month?.length">—</td>
          <td class="num" v-else>—</td>
        </tr>
      </tbody>
    </table>
  </div>

  <div class="panel" v-if="cmpMode && cmpPeople.length">
    <div class="hdr-row">
      <h3>Сравнение: {{ cmpPeople.map(shortName).join(', ') }}</h3>
      <div class="cmp-pick">
        <span v-for="p in persons" :key="p" class="chip" :class="{ on: cmpPeople.includes(p) }"
              @click="cmpPeople.includes(p) ? (cmpPeople = cmpPeople.filter(x => x !== p)) : (cmpPeople = [...cmpPeople, p].slice(-5))">
          {{ shortName(p) }}
        </span>
      </div>
    </div>
    <div class="chart-box" style="height: 320px"><canvas ref="cCmp"></canvas></div>
    <table v-if="cmpTable.length">
      <thead><tr><th>Ответственный</th><th class="num">Выручка-посл-мес</th><th class="num">Сделок</th><th class="num">к-прошл-мес</th><th class="num">Год-к-году</th></tr></thead>
      <tbody>
        <tr v-for="r in cmpTable" :key="r.person">
          <td>{{ r.person }}</td><td class="num">{{ fmtMln(r.rev) }}</td><td class="num">{{ fmtInt(r.deals) }}</td>
          <td class="num"><span :class="r.dMoM >= 0 ? 'up' : 'down'">{{ r.dMoM >= 0 ? '▲' : '▼' }} {{ Math.abs(r.dMoM) }}%</span></td>
          <td class="num"><span :class="r.dYoY >= 0 ? 'up' : 'down'">{{ r.dYoY >= 0 ? '▲' : '▼' }} {{ Math.abs(r.dYoY) }}%</span></td>
        </tr>
      </tbody>
    </table>
    <p class="hint">Клик-по-чипу-сверху —- добавить/убрать-человека из-сравнения (до-5). «Год-к-году» = против-того-же-месяца-прошлого-года.</p>
  </div>
</template>

<style scoped>
.hdr-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.period { font-size: 12.5px; color: var(--muted); display: flex; gap: 6px; align-items: center; }
.period select { padding: 5px 8px; border: 1px solid var(--line); border-radius: 8px; background: var(--bg); color: var(--text); }
.hint { color: var(--muted); font-size: 12px; margin-top: 8px; }
.cmp-pick { display: flex; gap: 5px; flex-wrap: wrap; }
.cmp-pick .chip { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 999px; padding: 4px 11px; font-size: 12.5px; cursor: pointer; }
.cmp-pick .chip.on { background: var(--accent); border-color: var(--accent); color: #fff; }
</style>
