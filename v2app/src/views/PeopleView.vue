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
interface DayRow { day: string; deals: number; revenue: number }

const qsSum = computed(() => {
  const p = new URLSearchParams({ months: String(months.value) })
  if (dayFrom.value) p.set('ship_from', dayFrom.value)
  if (dayTo.value) p.set('ship_to', dayTo.value)
  return `/api/people/summary?${p.toString()}`
})
const sum = useApi<any>(() => qsSum.value)
const detail = useApi<MonthRespExtra>(() => (selected.value ? (() => {
  const p = new URLSearchParams({ person: selected.value, months: String(months.value) })
  if (dayFrom.value) p.set('ship_from', dayFrom.value)
  if (dayTo.value) p.set('ship_to', dayTo.value)
  return `/api/people/monthly?${p.toString()}`
})() : ''), false)
type MonthRespExtra = MonthResp
interface MonthResp { person: string; months: number; monthly: MonthRow[]; prev_year_same_month: PYRow[] }
interface MonthRow { month: string; deals: number; revenue: number; avg_check: number }
interface PYRow { pm: string; deals: number; revenue: number; avg_check: number }

const cmpApi = useApi<CompareResp>(() => (cmpMode.value && cmpPeople.value.length >= 1 ? (() => {
  // ВАЖНО:URLSearchParams-сам-кодирует-—-лишний-encodeURIComponent-давал-двойное-кодирование
  // (бэк-получал-%D0%95...-вместо-Ермолаева-→-пустые-серии-→-график-сравнения-никогда-не-рисовался)
  const p = new URLSearchParams({ people: cmpPeople.value.join(';'), months: String(months.value) })
  if (dayFrom.value) p.set('ship_from', dayFrom.value)
  if (dayTo.value) p.set('ship_to', dayTo.value)
  return `/api/people/compare?${p.toString()}`
})() : ''), false)
interface CompareRespX { months: string[]; series: Record<string, MonthDeal[]> }
interface MonthDeal { month: string; deals: number; revenue: number }

// ВАЖНО: dep-графиков-должен-покрывать-ВСЁ,-что-читает-функция-рисования:
// в-дневном-режиме-графики-2/3-рисуются-из-sum.data.by_day (+презеты-дней) —- раньше-dep-их-не-включал,
// и-порядок-прихода-ответов (sum-раньше-cmpApi-или-наоборот)-решал,-перерисуется-ли-график-—-«жил-своей-жизнью».
const dep = computed(() => [sum.data.value, months.value] as unknown)
const depD = computed(() => [detail.data.value, selected.value, months.value, sum.data.value, presetDays.value, dayFrom.value, dayTo.value] as unknown)
const depC = computed(() => [cmpApi.data.value, cmpPeople.value, sum.data.value, presetDays.value, dayFrom.value, dayTo.value] as unknown)

const persons = computed(() => (sum.data.value?.summary ?? []).map((s: any) => s.person))
watch(persons, (ps) => {
  if (!selected.value && ps.length) selected.value = ps[0]
  if (cmpPeople.value.length === 0 && ps.length) {
    cmpPeople.value = ps.slice(0, 3) // топ-3-по-умолчанию
    cmpMode.value = true
  }
})

const dayFrom = ref(''); const dayTo = ref('')
const presetDays = ref(false)
function isoD(d: Date) { return d.toISOString().slice(0, 10) }
const todayChip = () => { dayFrom.value = dayTo.value = isoD(new Date()); presetDays.value = true }
const yestChip = () => { const d = new Date(); d.setDate(d.getDate() - 1); dayFrom.value = dayTo.value = isoD(d); presetDays.value = true }
const weekChip = () => { const a = new Date(); const b = new Date(); a.setDate(a.getDate() - 6); dayFrom.value = isoD(a); dayTo.value = isoD(b); presetDays.value = true }
// клик-по-человеку:面板-появляется-в-DOM-ПОЗЖЕ-данных —- грузим-деталку-ЯВНО (даже-если-человек-тот-же):
function pickPerson(p: string) {
  const changed = selected.value !== p
  selected.value = p
  cmpMode.value = false
  if (!changed) detail.load() // если-тот-же: watch-не-сработает —- перезагружаем-вручную
}
// ── ПЕРЕЗАГРУЗКИ (useApi-здесь-без-авто-watch —- вызываем-вручную) ──
watch(months, () => {
  sum.load()
  if (selected.value && !cmpMode.value) detail.load()
  if (cmpMode.value && cmpPeople.value.length) cmpApi.load()
})
watch(selected, (v) => { if (v && !cmpMode.value) detail.load() })
watch([cmpPeople, cmpMode], () => { if (cmpMode.value && cmpPeople.value.length) cmpApi.load() })
watch([dayFrom, dayTo], () => {
  sum.load()
  if (selected.value && !cmpMode.value) detail.load()
  if (cmpMode.value && cmpPeople.value.length) cmpApi.load()
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

// ── график-2: динамика-выбранного-человека (дни-при-дневном-фильтре, месяцы-иначе) ──
const { canvas: cPerson } = useChart(() => {
  const d = detail.data.value
  const s = sum.data.value as any
  if (presetDays.value) {
    // ── дневной-режим: столбики-по-ДНЯМ (ось-общая-для-обоих-людей: пропущенные-дни = нули) ──
    const all = new Set<string>()
    for (const arr of Object.values(s?.by_day ?? {})) for (const r of (arr as DayRow[])) all.add(r.day)
    const labels = [...all].sort()
    if (!labels.length) return null
    const C = chartColors()
    // один-день (Сегодня/Вчера): прямые-линии-уровня-значения (не-«0→X»)
    if (labels.length === 1) {
      const day = labels[0]
      const rev = +(((s.by_day[selected.value] || []).find((r: DayRow) => r.day === day)?.revenue ?? 0) / 1e6).toFixed(3)
      const deals = ((s.by_day[selected.value] || []).find((r: DayRow) => r.day === day)?.deals ?? 0)
      return {
        type: 'line',
        data: { labels: [shortDay(day) + ' 0ч', shortDay(day) + ' 24ч'],
          datasets: [
            { label: `Выручка: ${rev} млн`, data: [rev, rev], borderColor: C.accent, tension: 0, pointRadius: 0, borderWidth: 2, yAxisID: 'y' },
            { label: `Сделок: ${deals}`, data: [deals, deals], borderColor: C.ok, tension: 0, pointRadius: 0, borderWidth: 2, yAxisID: 'y2', borderDash: [6, 3] },
          ] },
        options: { maintainAspectRatio: false,
          scales: { y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
                    y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
                    x: { ticks: { color: C.muted }, grid: { display: false } } },
          plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
      } as any
    }
    return {
      type: 'bar',
      data: { labels,
        datasets: [
          { type: 'bar', label: 'Выручка, млн/день', data: labels.map(l => +(((s.by_day[selected.value] || []).find((r: DayRow) => r.day === l)?.revenue ?? 0) / 1e6).toFixed(2)), backgroundColor: C.accent + 'CC', borderRadius: 3, yAxisID: 'y' },
          { type: 'line', label: 'Сделок', data: labels.map(l => (s.by_day[selected.value] || []).find((r: DayRow) => r.day === l)?.deals ?? 0), borderColor: C.ok, tension: 0.3, pointRadius: 2, yAxisID: 'y2' },
        ] },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: { y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
                y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
                x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
    } as any
  }
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

// ── график-3: сравнение-людей (месяцы-ИЛИ-дни —- в-дневном-режиме-ось-по-ДНЯМ) ──
const cmpPalette = ['#3b82f6', '#16a34a', '#f59e0b', '#a855f7', '#ef4444']
const { canvas: cCmp } = useChart(() => {
  const C = chartColors()
  const s = sum.data.value as any
  if (presetDays.value) {
    // дневная-ось-О-Б-Щ-А-Я: все-дни-с-диапазона-фильтра, пропуски = нули
    const all = new Set<string>()
    for (const arr of Object.values(s?.by_day ?? {})) for (const r of (arr as DayRow[])) all.add(r.day)
    if (dayFrom.value && dayTo.value) { // заполнить-пропущенные-дни-ряда
      for (let d0 = new Date(dayFrom.value + 'T12:00:00'); d0 <= new Date(dayTo.value + 'T12:00:00'); d0.setDate(d0.getDate() + 1)) all.add(d0.toISOString().slice(0, 10))
    }
    const labels = [...all].sort()
    if (!labels.length) return null
    const people = Object.keys(s?.by_day ?? {}).filter((p: string) => cmpPeople.value.includes(p))
    if (!people.length) return null
    // один-день (Сегодня/Вчера): линия-«каждому-своя-горизонталь» —- ось-2-точки (Д), значение-константа,-не-«0→X»
    if (labels.length === 1) {
      return {
        type: 'line',
        data: { labels: [shortDay(labels[0]) + ' 0ч', shortDay(labels[0]) + ' 24ч'],
          datasets: people.map((p, i) => {
            const rev = +(((s.by_day[p] || []).find((r: DayRow) => r.day === labels[0])?.revenue ?? 0) / 1e6).toFixed(3)
            const deals = ((s.by_day[p] || []).find((r: DayRow) => r.day === labels[0])?.deals ?? 0)
            return { label: `${shortName(p)}: ${rev} млн / ${deals} сд`,
              data: [rev, rev], borderColor: cmpPalette[i % 6], backgroundColor: cmpPalette[i % 6] + '55', tension: 0, pointRadius: 0, borderWidth: 2, fill: false }
          }) },
        options: { maintainAspectRatio: false,
          scales: { y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
                    x: { ticks: { color: C.muted }, grid: { display: false } } },
          plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
      } as any
    }
    return {
      type: 'line',
      data: { labels: labels.map(shortDay),
        datasets: people.map((p, i) => ({ label: shortName(p),
          data: labels.map(l => +(((s.by_day[p] || []).find((r: DayRow) => r.day === l)?.revenue ?? 0) / 1e6).toFixed(3)),
          borderColor: cmpPalette[i % 6], backgroundColor: cmpPalette[i % 6] + '55', tension: 0.3, pointRadius: 2, fill: false })) },
      options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        scales: { y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
                  x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } } },
        plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
    } as any
  }
  const d = cmpApi.data.value as CompareResp | null
  if (!d?.months?.length || !d?.series) return null
  const people = Object.keys(d.series)
  if (!people.length) return null
  return {
    type: 'line',
    data: { labels: d.months,
      datasets: people.map((p, i) => ({ label: shortName(p), data: (d.series[p] || []).map(x => +(x.revenue / 1e6).toFixed(2)), borderColor: cmpPalette[i % 6], backgroundColor: cmpPalette[i % 6] + '55', tension: 0.3, pointRadius: 2, fill: false })) },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: { y: { title: { display: true, text: 'млн ₽' }, ticks: { color: C.muted }, grid: { color: C.border } },
                x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
  } as any
}, depC as unknown as Ref<unknown>)

// сравнение-таблица: последний-месяц-vs-предыдущий-и-год-к-году
const cmpTable = computed(() => {
  const d = cmpApi.data.value as CompareResp | null
  if (!d?.months?.length) return []
  // последний-ПОЛНЫЙ-месяц = прошлый-месяц от-сегодня (сейчас-сент-2026-недокатился —- берём-август)
  const now = new Date()
  const curYM = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const lastIdx = d.months.indexOf(curYM) >= 0 ? d.months.indexOf(curYM) : d.months.length - 1
  if (lastIdx < 1) return []
  const lm = d.months[lastIdx]
  const prev = d.months[lastIdx - 1] || lm
  const lmPrevYear = (() => { // тот-же-месяц-год-назад
    const [y, m] = lm.split('-').map(Number)
    return `${y - 1}-${String(m).padStart(2, '0')}`
  })()
  // если-года-назад-месяца-нет-в-оси (короткое-окно) —- показываем-прочерк, а-не-«+100%»
  const hasPY = (p: string) => (d.series[p] || []).some(x => x.month === lmPrevYear && x.deals + x.revenue > 0)
  return Object.keys(d.series).map(p => {
    const find = (mm: string) => (d.series[p] || []).find(x => x.month === mm)
    const a = (find(lm)?.revenue ?? 0), b = (find(prev)?.revenue ?? 0), c = (find(lmPrevYear)?.revenue ?? 0)
    const dMoM = b ? +(((a - b) / b) * 100).toFixed(0) : (a ? 100 : 0)
    const dYoY = c ? +(((a - c) / c) * 100).toFixed(0) : (hasPY(p) ? 0 : (a ? 100 : 0))
    return { person: p, rev: a, deals: find(lm)?.deals ?? 0, dMoM, dYoY, lm: lm !== curYM || !a ? lm : prev }
  }).sort((x, y) => y.rev - x.rev)
})

const shortDay = (iso: string) => (iso ? iso.slice(8) + '.' + iso.slice(5, 7) : '—')  // 25.09
const fmtShortMonth = (iso: string) => {
  if (!iso) return '—'
  const [y, m] = iso.split('-')
  const names = ['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек']
  return `${names[+m - 1]} ${y}`
}

// ── быстрые-периоды (как-в-«Заказах»): чипы-вместо-выпадашки-«месяцев» ──
type PChip = { label: string; months: number }
const PERIODS: PChip[] = [
  { label: 'Месяц',   months: 1 },
  { label: 'Квартал', months: 3 },
  { label: 'Полгода', months: 6 },
  { label: 'Год',     months: 12 },
  { label: '2 года',  months: 24 },
  { label: '3 года',  months: 36 },
  { label: 'Всё',     months: 60 },
]
const pChip = ref(12) // активный-период-в-месяцах
watch(pChip, (v) => { months.value = v })

// ── быстрые-ДНИ/НЕДЕЛЯ (сегодня/вчера/неделя —- по-датам-отгрузки) ──
</script>

<template>
  <h1>Люди (продажи)</h1>

  <div class="panel">
    <div class="hdr-row">
      <h3>Выручка по ответственным (отгруженные заказы)</h3>
      <div class="qf-group">
        <button class="chip" :class="{ on: presetDays && dayFrom === isoD(new Date()) }" @click="todayChip">Сегодня</button>
        <button class="chip" :class="{ on: presetDays && (() => { const d = new Date(); d.setDate(d.getDate() - 1); return dayFrom === isoD(d) })() }" @click="yestChip">Вчера</button>
        <button class="chip" :class="{ on: presetDays && (() => { const a = new Date(); a.setDate(a.getDate() - 6); return dayFrom === isoD(a) && dayTo === isoD(new Date()) })() }" @click="weekChip">Неделя</button>
        <span class="chip-sep">·</span>
        <button v-for="p in PERIODS" :key="p.months" class="chip" :class="{ on: !presetDays && months === p.months }" @click="months = p.months; presetDays = false; dayFrom = ''; dayTo = ''">{{ p.label }}</button>
      </div>
    </div>
    <div class="chart-box" style="height: 300px"><canvas ref="cTop"></canvas></div>
    <table>
      <thead><tr><th>Ответственный</th><th class="num">Сделок</th><th class="num">В-среднем/мес</th><th class="num">Выручка</th></tr></thead>
      <tbody>
        <tr v-for="s in (sum.data.value?.summary ?? [])" :key="s.person" class="click" @click="pickPerson(s.person)">
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
      <h3>{{ selected }} —- динамика ({{ presetDays ? (dayFrom === dayTo ? dayFrom : dayFrom + " → " + dayTo) : months + " мес" }})</h3>
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
.qf-group { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { border: 1px solid var(--line); background: var(--panel); color: var(--text);
  border-radius: 999px; padding: 5px 13px; font-size: 13px; cursor: pointer; transition: all .12s; }
.chip:hover { border-color: var(--accent); }
.chip.on { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.hint { color: var(--muted); font-size: 12px; margin-top: 8px; }
.chip-sep { color: var(--muted); padding: 0 2px; }
.cmp-pick { display: flex; gap: 5px; flex-wrap: wrap; }
.cmp-pick .chip { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 999px; padding: 4px 11px; font-size: 12.5px; cursor: pointer; }
.cmp-pick .chip.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.up { color: var(--ok); } .down { color: var(--err); }
</style>