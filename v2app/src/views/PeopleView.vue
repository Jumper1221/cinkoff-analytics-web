<script setup lang="ts">
import { computed, ref, watch, onMounted, onUnmounted, type Ref } from 'vue'
import { useApi, fmtInt, fmtMln, fmtMoney, moneyAuto } from '../api/client'
import { useChart, chartColors } from '../api/useChart'

// ── состояние: период, выбор-человека, режим-сравнения ──
const months = ref(12)
const selected = ref('')
const cmpPeople = ref<string[]>([])
const cmpMode = ref(false)

interface SumResp {
  period_months: number
  summary: { person: string; deals_total: number; revenue_mln: number; deals_per_month: number; avg_month_revenue_mln?: number; first_month: string }[]
  by_month: Record<string, { month: string; deals: number; revenue: number }[]>
}
interface MonthResp {
  monthly: { month: string; deals: number; revenue: number; avg_check: number }[]
  prev_year_same_month: { pm: string; deals: number; revenue: number; avg_check: number }[]
}
interface CompareResp { gran?: 'day' | 'week' | 'month'; months: string[]; series: Record<string, MonthDeal[]>; months_monthly?: string[]; series_monthly?: Record<string, MonthDeal[]> }
interface MonthDeal { month: string; deals: number; revenue: number }
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
interface GranRow { month: string; deals: number; revenue: number; avg_check?: number }
type MonthRespExtra = MonthResp & { gran?: 'day' | 'week' | 'month'; series?: GranRow[] }
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
interface DayRow { day: string; deals: number; revenue: number }

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
// ── РУЧНОЙ-ФИЛЬТР:месяц / год / произвольный-диапазон (mode-—-кто-в-С-И-Л-Е) ──
const fmMode = ref<'preset' | 'month' | 'year' | 'custom'>('preset')
const fmMonth = ref('')   // 'YYYY-MM'
const fmYear = ref('')    // 'YYYY'
const cuFrom = ref(''); const cuTo = ref('')  // свободный-диапазон
const YEARS = (() => { const y0 = 2019, y1 = new Date().getFullYear(); return Array.from({ length: y1 - y0 + 1 }, (_, i) => y1 - i) })()
const MONTHS_ALL = (() => { // последние-84-месяца (7-лет)-дл-я-се-л-Е-К-Т-А-—-свежие-в-К-О-Н-Ц-Е-(
  const arr: string[] = []; const n = new Date()
  for (let i = 0; i < 84; i++) { const d = new Date(n.getFullYear(), n.getMonth() - i, 1); arr.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`) }
  return arr
})()
const MON_RU = ['', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const monthLabel = (ym: string) => { const [y, m] = ym.split('-'); return `${MON_RU[+m]} ${y}` }
// применение-выбранного-режима:пишет-в-dayFrom/dayTo-и-Е-ДИ-Н-СТ-В-Е-Н-Н-Ы-Й-источник-правды-фильтра
function applyMonthFilter() {
  if (!fmMonth.value) { dayFrom.value = ''; dayTo.value = ''; presetDays.value = false; return }
  const [y, m] = fmMonth.value.split('-').map(Number)
  const last = new Date(+y, +m, 0).getDate() // последний-день-месяца
  const now = new Date()
  const end = (y === now.getFullYear() && +m === now.getMonth() + 1) ? isoD(now) : `${y}-${String(m).padStart(2, '0')}-${String(last).padStart(2, '0')}`
  dayFrom.value = `${y}-${String(m).padStart(2, '0')}-01`; dayTo.value = end
  presetDays.value = true
}
function applyYear() {
  if (!fmYear.value) { dayFrom.value = ''; dayTo.value = ''; presetDays.value = false; return }
  const y = fmYear.value; const n = new Date()
  dayFrom.value = (y === String(n.getFullYear())) ? (new Date(n.getFullYear(), n.getMonth(), 1).toISOString().slice(0, 10)) : `${y}-01-01`
  dayTo.value = isoD(new Date()) // по-сегодня
  presetDays.value = true
}
function applyCustom() {
  if (!cuFrom.value && !cuTo.value) { presetDays.value = false; return }
  presetDays.value = true
}
// смена-режима-гасит-чужие-активности-—-пресеты-сегодня/вчера/неделя-остаются-в-fmMode=preset
function setMode(m: 'preset' | 'month' | 'year' | 'custom') {
  fmMode.value = m
  if (m === 'month' && fmMonth.value) applyMonthFilter()
  else if (m === 'year' && fmYear.value) applyYear()
  else if (m === 'custom') { /* ждём-даты-из-инпутов — применит watch ниже */
    if (!cuFrom.value && !cuTo.value) { dayFrom.value = ''; dayTo.value = ''; presetDays.value = false }
  } else if (m === 'preset') { dayFrom.value = ''; dayTo.value = ''; presetDays.value = false }
}
// кастомный-диапазон:применяется-на-лету-когда-оба-поля-заполнены
watch([cuFrom, cuTo], () => {
  if (fmMode.value !== 'custom') return
  if (cuFrom.value && cuTo.value) { dayFrom.value = cuFrom.value; dayTo.value = cuTo.value; presetDays.value = true }
})
// месячный/год-селекты-тоже-на-лету:
watch(fmMonth, () => { if (fmMode.value === 'month' && fmMonth.value) applyMonthFilter() })
watch(fmYear, () => { if (fmMode.value === 'year' && fmYear.value) applyYear() })

// ── ПОПОВЕР-ПЕРИОДА (кнопка-📅-с-тек-У-Щ-И-М-диапазоном; внутри-месяц/год/свои-даты) ──
const popOpen = ref(false)
function togglePop() { popOpen.value = !popOpen.value }
function closePop() { popOpen.value = false }
// клик-вне-и-Escape-закрывают-поповер-(-са-М-О-ве-Б-станд-А-Р-Т-Н-О-Е-пов-Е-Д-Е-Н-И-Е-д-А-Т-П-И-К-К-Е-Р-О-В-(
function onDocClick(e: MouseEvent) {
  const t = e.target as HTMLElement
  if (!t.closest('.period-pop') && !t.closest('.btn-range')) popOpen.value = false
}
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') popOpen.value = false }
onMounted(() => { document.addEventListener('click', onDocClick); document.addEventListener('keydown', onKey) })
onUnmounted(() => { document.removeEventListener('click', onDocClick); document.removeEventListener('keydown', onKey) })

function applyCustomRange() {
  if (!cuFrom.value || !cuTo.value) return
  dayFrom.value = cuFrom.value
  dayTo.value = cuTo.value
  presetDays.value = true
  fmMode.value = 'custom'
  popOpen.value = false
}
function pickMonth(ym: string) { fmMode.value = 'month'; fmMonth.value = ym; applyMonthFilter(); popOpen.value = false }
function pickYear(yv: string) { fmMode.value = 'year'; fmYear.value = yv; applyYear(); popOpen.value = false }
// активен-ли-«ручной»-режим (для-подсветки-кнопки-📅 и-гашения-пресетных-чипов):
const manualActive = computed(() => (fmMode.value !== 'preset' || presetDays.value) && !!dayFrom.value)
// человеко-понятный-лейбл-тек-У-Щ-Е-ГО-диапазона-(-са-М-О-ве-Б-в-К-Н-О-П-К-Е-📅-(
const dd = (iso: string) => (iso ? iso.slice(8) + '.' + iso.slice(5, 7) + '.' + iso.slice(2, 4) : '—')  // 25.09.26
const rangeLabel = computed(() => {
  if (fmMode.value === 'month' && fmMonth.value) return monthLabel(fmMonth.value)
  if (fmMode.value === 'year' && fmYear.value) return fmYear.value + ' год'
  if (dayFrom.value && dayTo.value) return (dayFrom.value === dayTo.value ? dd(dayFrom.value) : dd(dayFrom.value) + ' → ' + dd(dayTo.value))
  return '12 мес' // скользящий-Год-по-ум-О-Л-Ч-А-Н-И-Ю
})
// сброс-в-деф-О-Л-Т-(-са-М-О-ве-Б-скользящий-Год-(
function resetRange() {
  fmMode.value = 'preset'; presetDays.value = false
  dayFrom.value = ''; dayTo.value = ''; cuFrom.value = ''; cuTo.value = ''
  fmMonth.value = ''; fmYear.value = ''
  months.value = 12
  popOpen.value = false
}
// год-назад-для-дефолта-лейбла-когда-нет-дат-(-са-М-О-ве-Б-подсказка-(
const slideHint = computed(() => {
  if (dayFrom.value || fmMode.value !== 'preset' || presetDays.value) return ''
  const a = new Date(); a.setMonth(a.getMonth() - 12); a.setDate(a.getDate() + 1)
  return '25.09.25 → 25.09.26-подобное-скользящее-окно'
})
function isoD(d: Date) { return d.toISOString().slice(0, 10) }
const todayChip = () => { dayFrom.value = dayTo.value = isoD(new Date()); presetDays.value = true }
const yestChip = () => { const d = new Date(); d.setDate(d.getDate() - 1); dayFrom.value = dayTo.value = isoD(d); presetDays.value = true }
const weekChip = () => { const a = new Date(); const b = new Date(); a.setDate(a.getDate() - 6); dayFrom.value = isoD(a); dayTo.value = isoD(b); presetDays.value = true }
// клик-по-человеку: панель-появляется-в-DOM-ПОЗЖЕ-данных — грузим-деталку-ЯВНО (даже-если-человек-тот-же)
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
  // авто-градация: если-все-суммы-малые (<1 млн на-человека) —- рисуем-в-тысячах, иначе-в-млн
  const useThousand = (s as any[]).length > 0 && (s as any[]).every((r: any) => Math.abs(r.revenue_mln) < 1)
  const unitTop = useThousand ? 'тыс ₽' : 'млн ₽'
  const data = (s as any[]).map((r: any) => useThousand ? +(r.revenue_mln * 1000).toFixed(0) : +r.revenue_mln.toFixed(2))
  return {
    type: 'bar',
    data: { labels: (s as any[]).map(r => shortName(r.person)),
      datasets: [{ label: 'Выручка, ' + unitTop, data, backgroundColor: C.accent + 'CC', borderRadius: 4 }] },
    options: { maintainAspectRatio: false,
      scales: { y: { title: { display: true, text: unitTop }, ticks: { color: C.muted }, grid: { color: C.border } },
                x: { ticks: { color: C.muted, autoSkip: false, maxRotation: 35 }, grid: { display: false } } },
      plugins: { legend: { display: false } } },
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
      const revRaw = +(((s.by_day[selected.value] || []).find((r: DayRow) => r.day === day)?.revenue ?? 0))
      const deals = ((s.by_day[selected.value] || []).find((r: DayRow) => r.day === day)?.deals ?? 0)
      const th = Math.abs(revRaw) < 1e6 && revRaw !== 0
      const unit = th ? 'тыс ₽' : 'млн ₽'
      const rev = th ? +(revRaw / 1e3).toFixed(1) : +(revRaw / 1e6).toFixed(3)
      return {
        type: 'line',
        data: { labels: [shortDay(day) + ' 0ч', shortDay(day) + ' 24ч'],
          datasets: [
            { label: `Выручка: ${moneyAuto(revRaw)}`, data: [rev, rev], borderColor: C.accent, tension: 0, pointRadius: 0, borderWidth: 2, yAxisID: 'y' },
            { label: `Сделок: ${deals}`, data: [deals, deals], borderColor: C.ok, tension: 0, pointRadius: 0, borderWidth: 2, yAxisID: 'y2', borderDash: [6, 3] },
          ] },
        options: { maintainAspectRatio: false,
          scales: { y: { title: { display: true, text: unit }, ticks: { color: C.muted }, grid: { color: C.border } },
                    y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
                    x: { ticks: { color: C.muted }, grid: { display: false } } },
          plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
      } as any
    }
    const raws = labels.map(l => (((s.by_day[selected.value] || []).find((r: DayRow) => r.day === l)?.revenue ?? 0)))
    const useT = raws.length > 0 && raws.every(v => Math.abs(v) < 1e6)
    const unitD = useT ? 'тыс ₽/день' : 'млн ₽/день'
    return {
      type: 'bar',
      data: { labels,
        datasets: [
          { type: 'bar', label: 'Выручка, ' + (useT ? 'тыс/день' : 'млн/день'), data: raws.map(v => useT ? +(v / 1e3).toFixed(1) : +(v / 1e6).toFixed(2)), backgroundColor: C.accent + 'CC', borderRadius: 3, yAxisID: 'y' },
          { type: 'line', label: 'Сделок', data: labels.map(l => (s.by_day[selected.value] || []).find((r: DayRow) => r.day === l)?.deals ?? 0), borderColor: C.ok, tension: 0.3, pointRadius: 2, yAxisID: 'y2' },
        ] },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: { y: { title: { display: true, text: unitD }, ticks: { color: C.muted }, grid: { color: C.border } },
                y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
                x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
    } as any
  }
  // месячный-режим (gran-из-бэка: month=помесячно+YoY, week=понедельно, day=подневно; presetDays-перекрыт-веткой-выше)
  if (!d?.series?.length) return null
  const C = chartColors()
  const ser = d.series as GranRow[]
  // АВТО-ГРАДАЦИЯ: все-значения-периода <1 млн → тысячи, иначе-миллионы (ось-подписана-единицами)
  const maxV = Math.max(...ser.map(m => Math.abs(m.revenue)), 0)
  const useT = maxV < 1e6
  const div = useT ? 1e3 : 1e6
  const unitD = (useT ? 'тыс' : 'млн') + (d.gran === 'day' ? ' ₽/день' : (d.gran === 'week' ? ' ₽/нед' : ' ₽'))
  const unit = (useT ? 'тыс' : 'млн') + (d.gran === 'day' ? '/день' : (d.gran === 'week' ? '/нед' : ''))
  const shortP = (p: string) => (d.gran === 'month' ? fmtShortMonth(p) : (p ? p.slice(8) + '.' + p.slice(5, 7) : '—'))
  const labels = ser.map((m) => shortP(m.month))
  const revData = ser.map((m) => +(m.revenue / div).toFixed(useT ? 1 : 2))
  const datasets: any[] = [
    { type: 'bar', label: 'Выручка, ' + unit, data: revData, backgroundColor: C.accent + 'CC', borderRadius: 3, yAxisID: 'y' },
    { type: 'line', label: 'Сделок', data: ser.map((m) => m.deals), borderColor: C.ok, tension: 0.3, pointRadius: 2, yAxisID: 'y2' },
  ]
  if (d.gran === 'month') { // YoY-пунктир-имеет-смысл-только-в-помесячном-режиме
    const pyMap: Record<string, MonthRow> = {}
    for (const r of (d.prev_year_same_month ?? []) as PYRow[]) pyMap[r.pm] = { month: r.pm, deals: r.deals, revenue: r.revenue, avg_check: r.avg_check }
    datasets.push({ type: 'line', label: 'Тот-же-месяц-год-назад (млн)', data: ser.map((m) => +((pyMap[m.month]?.revenue ?? 0) / 1e6).toFixed(2)), borderColor: C.muted, borderDash: [5, 4], tension: 0.25, pointRadius: 1.5, yAxisID: 'y' })
  }
  return {
    type: 'bar',
    data: { labels, datasets },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: { y: { title: { display: true, text: unitD }, ticks: { color: C.muted }, grid: { color: C.border } },
                y2: { position: 'right', ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
                x: { ticks: { color: C.muted, maxTicksLimit: 14, maxRotation: 45 }, grid: { display: false } } },
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
      const val = (p: string) => ((s.by_day[p] || []).find((r: DayRow) => r.day === labels[0])?.revenue ?? 0)
      const maxV = Math.max(...people.map(val), 0)
      const useT = maxV < 1e6 && maxV > 0
      const div = useT ? 1e3 : 1e6
      const unitC = useT ? 'тыс ₽' : 'млн ₽'
      return {
        type: 'line',
        data: { labels: [shortDay(labels[0]) + ' 0ч', shortDay(labels[0]) + ' 24ч'],
          datasets: people.map((p, i) => {
            const deals = ((s.by_day[p] || []).find((r: DayRow) => r.day === labels[0])?.deals ?? 0)
            return { label: `${shortName(p)}: ${moneyAuto(val(p))} / ${deals} сд`,
              data: [val(p) / div, val(p) / div], borderColor: cmpPalette[i % 6], backgroundColor: cmpPalette[i % 6] + '55', tension: 0, pointRadius: 0, borderWidth: 2, fill: false }
          }) },
        options: { maintainAspectRatio: false,
          scales: { y: { title: { display: true, text: unitC }, ticks: { color: C.muted }, grid: { color: C.border } },
                    x: { ticks: { color: C.muted }, grid: { display: false } } },
          plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
      } as any
    }
    const allVals = people.flatMap((p: string) => (s.by_day[p] || []).map((r: DayRow) => Math.abs(r.revenue)))
    const useT = allVals.length > 0 && Math.max(...allVals, 0) < 1e6
    const div = useT ? 1e3 : 1e6
    const unitC = useT ? 'тыс ₽' : 'млн ₽'
    return {
      type: 'line',
      data: { labels: labels.map(shortDay),
        datasets: people.map((p, i) => ({ label: shortName(p),
          data: labels.map(l => +(((s.by_day[p] || []).find((r: DayRow) => r.day === l)?.revenue ?? 0) / div).toFixed(3)),
          borderColor: cmpPalette[i % 6], backgroundColor: cmpPalette[i % 6] + '55', tension: 0.3, pointRadius: 2, fill: false })) },
      options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
        scales: { y: { title: { display: true, text: unitC }, ticks: { color: C.muted }, grid: { color: C.border } },
                  x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { display: false } } },
        plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
    } as any
  }
  const d = cmpApi.data.value as CompareResp | null
  if (!d?.months?.length || !d?.series) return null
  const people = Object.keys(d.series)
  if (!people.length) return null
  const allVals = people.flatMap((p: string) => (d.series[p] || []).map(x => Math.abs(x.revenue)))
  const useT = allVals.length > 0 && Math.max(...allVals, 0) < 1e6
  const div = useT ? 1e3 : 1e6
  const unitC = useT ? 'тыс ₽' : 'млн ₽'
  const lbl = (iso: string) => (d.gran === 'month' ? iso : shortDay(iso)) // ось-месяцев-или-недель-датой
  return {
    type: 'line',
    data: { labels: d.months.map(lbl),
      datasets: people.map((p, i) => ({ label: shortName(p), data: (d.series[p] || []).map(x => +(x.revenue / div).toFixed(3)), borderColor: cmpPalette[i % 6], backgroundColor: cmpPalette[i % 6] + '55', tension: 0.3, pointRadius: 2, fill: false })) },
    options: { maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      scales: { y: { title: { display: true, text: unitC }, ticks: { color: C.muted }, grid: { color: C.border } },
                x: { ticks: { color: C.muted, maxTicksLimit: 12, maxRotation: 45 }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
  } as any
}, depC as unknown as Ref<unknown>)

// сравнение-таблица: последний-месяц-vs-предыдущий-и-год-к-году
const cmpTable = computed(() => {
  const d = cmpApi.data.value as CompareResp | null
  // ДЕЛЬТЫ-ВСЕГДА-ПО-МЕСЯЦАМ (months_monthly/series_monthly от-бэка; при-gran=month-это-сами-поля-графика)
  const mAxis = d?.months_monthly?.length ? d.months_monthly : (d?.months ?? [])
  const mSer = (p: string) => (d?.series_monthly?.[p] ?? d?.series?.[p] ?? [])
  if (!mAxis.length) return []
  const now = new Date()
  const curYM = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
  const lastIdx = mAxis.indexOf(curYM) >= 0 ? mAxis.indexOf(curYM) : mAxis.length - 1
  if (lastIdx < 1) return []
  const lm = mAxis[lastIdx]
  const prev = mAxis[lastIdx - 1] || lm
  const lmPrevYear = (() => {
    const [y, m] = lm.split('-').map(Number)
    return `${y - 1}-${String(m).padStart(2, '0')}`
  })()
  const hasPY = (p: string) => mSer(p).some(x => x.month === lmPrevYear && x.deals + x.revenue > 0)
  return Object.keys(d?.series ?? {}).map(p => {
    const find = (mm: string) => mSer(p).find(x => x.month === mm)
    const a = (find(lm)?.revenue ?? 0), b = (find(prev)?.revenue ?? 0), c = (find(lmPrevYear)?.revenue ?? 0)
    const dMoM = b ? +(((a - b) / b) * 100).toFixed(0) : (a ? 100 : 0)
    const dYoY = c ? +(((a - c) / c) * 100).toFixed(0) : (hasPY(p) ? 0 : (a ? 100 : 0))
    return { person: p, rev: a, deals: find(lm)?.deals ?? 0, dMoM, dYoY, lm: lm !== curYM || !a ? lm : prev }
  }).sort((x, y) => y.rev - x.rev)
})

const detailRows = computed(() => {
  const d = detail.data.value as any
  if (d?.gran && d.gran !== 'month') return (d.series ?? []).map((r: any) => ({ period: r.month, deals: r.deals, revenue: r.revenue }))
  return (d?.monthly ?? []).map((m: any) => ({ period: m.month, deals: m.deals, revenue: m.revenue, avg_check: m.avg_check }))
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

</script>

<template>
  <h1>Люди (продажи)</h1>

  <div class="panel">
    <div class="hdr-row">
      <h3>Выручка по ответственным (отгруженные заказы)</h3>
      <div class="qf-group">
        <div class="seg">
          <button class="seg-btn" :class="{ on: presetDays && dayFrom === isoD(new Date()) && dayTo === isoD(new Date()) }" @click="todayChip">Сегодня</button>
          <button class="seg-btn" :class="{ on: presetDays && (() => { const d = new Date(); d.setDate(d.getDate() - 1); return dayFrom === isoD(d) && dayTo === isoD(d) })() }" @click="yestChip">Вчера</button>
          <button class="seg-btn" :class="{ on: presetDays && (() => { const a = new Date(); a.setDate(a.getDate() - 6); return dayFrom === isoD(a) && dayTo === isoD(new Date()) })() }" @click="weekChip">Неделя</button>
        </div>
        <button class="btn-range" :class="{ act: manualActive }" @click.stop="togglePop" :title="slideHint || 'Изменить период'">
          📅 {{ rangeLabel }} <span class="caret">▾</span>
        </button>
        <button v-if="manualActive" class="x-reset" @click="resetRange" title="Сбросить-на-скользящий-год">✕</button>

        <div v-if="popOpen" class="period-pop" @click.stop>
          <div class="pop-col">
            <div class="pop-h">Месяц</div>
            <select class="pop-sel" :value="fmMonth" @change="pickMonth(($event.target as HTMLSelectElement).value)">
              <option value="">выбрать…</option>
              <option v-for="ym in MONTHS_ALL" :key="ym" :value="ym">{{ monthLabel(ym) }}</option>
            </select>
            <div class="pop-hint" v-if="!fmMonth">месяц-целиком; текущий-—-по-сегодня</div>
          </div>
          <div class="pop-sep"></div>
          <div class="pop-col">
            <div class="pop-h3">Год</div>
            <div class="pop-years">
              <button v-for="y in YEARS" :key="y" class="yr" :class="{ on: fmYear === String(y) && fmMode === 'year' }" @click="pickYear(String(y))">{{ y }}</button>
            </div>
            <div class="pop-hint" v-if="fmMode === 'year' && fmYear">с-1-января-по-сегодня</div>
          </div>
          <div class="pop-sep"></div>
          <div class="pop-col">
            <div class="pop-h3">Свой-диапазон</div>
            <div class="pop-dates">
              <input type="date" v-model="cuFrom" class="qf-date" />
              <span class="arr">→</span>
              <input type="date" v-model="cuTo" class="qf-date" />
            </div>
            <button class="pop-apply" :disabled="!cuFrom || !cuTo" @click="applyCustomRange">Показать-за-период</button>
          </div>
        </div>
      </div>
    </div>
    <div class="chart-box" style="height: 300px"><canvas ref="cTop"></canvas></div>
    <table>
      <thead><tr><th>Ответственный</th><th class="num">Сделок</th><th class="num" title="Выручка-за-период ÷ кол-во-месяцев-в-периоде (средняя-по-месяцам-с-отгрузками)">Сред. выручка/мес</th><th class="num">Выручка за период</th></tr></thead>
      <tbody>
        <tr v-for="s in (sum.data.value?.summary ?? [])" :key="s.person" class="click" @click="pickPerson(s.person)">
          <td>{{ s.person }}</td>
          <td class="num">{{ fmtInt(s.deals_total) }}</td>
          <td class="num" title="средняя-выручка-в-месяцы-с-отгрузками (за-выбранный-период)">{{ moneyAuto(s.avg_month_revenue_mln * 1e6) }}</td>
          <td class="num">{{ moneyAuto(s.revenue_mln * 1e6) }}</td>
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
    <table v-if="detailRows.length">
      <thead><tr><th>{{ detail.data.value?.gran === 'day' ? 'День' : (detail.data.value?.gran === 'week' ? 'Неделя (с' : 'Месяц') }}</th><th class="num">Сделок</th><th class="num">Выручка</th><th v-if="detail.data.value?.gran === 'month'" class="num">Средний чек, ₽</th><th v-if="detail.data.value?.gran === 'month'" class="num">Год-к-году</th></tr></thead>
      <tbody>
        <tr v-for="m in detailRows" :key="m.period">
          <td>{{ detail.data.value?.gran === 'month' ? fmtShortMonth(m.period) : (detail.data.value?.gran === 'week' ? m.period + ')' : m.period) }}</td>
          <td class="num">{{ fmtInt(m.deals) }}</td>
          <td class="num">{{ moneyAuto(m.revenue) }}</td>
          <td class="num" v-if="detail.data.value?.gran === 'month'">{{ moneyAuto((m as any).avg_check) }}</td>
          <td class="num" v-if="detail.data.value?.gran === 'month'">—</td>
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
          <td>{{ r.person }}</td><td class="num">{{ moneyAuto(r.rev) }}</td><td class="num">{{ fmtInt(r.deals) }}</td>
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
.qf-group { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; position: relative; }
.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
.seg-btn { border: 0; background: transparent; color: var(--text); padding: 6px 14px; font-size: 13px; cursor: pointer; border-right: 1px solid var(--line); }
.seg-btn:last-child { border-right: 0; }
.seg-btn:hover { background: rgba(59,130,246,.08); }
.seg-btn.on { background: var(--accent); color: #fff; font-weight: 600; }
.btn-range { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 999px; padding: 6px 14px; font-size: 13px; cursor: pointer; display: inline-flex; gap: 6px; align-items: center; }
.btn-range.act { border-color: var(--accent); color: var(--accent); font-weight: 600; }
.btn-range .caret { opacity: .55; font-size: 10px; }
.x-reset { border: 1px solid var(--line); background: var(--panel); color: var(--muted); border-radius: 50%; width: 26px; height: 26px; cursor: pointer; line-height: 1; }
.x-reset:hover { color: var(--err); border-color: var(--err); }
.period-pop { position: absolute; top: calc(100% + 8px); right: 0; z-index: 30; display: flex; gap: 0; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 8px 28px rgba(0,0,0,.14); padding: 14px; min-width: 560px; }
.pop-col { padding: 0 14px; min-width: 150px; display: flex; flex-direction: column; gap: 8px; }
.pop-col:first-child { padding-left: 0; }
.pop-sep { width: 1px; background: var(--line); }
.pop-h { font-size: 11.5px; text-transform: uppercase; letter-spacing: .4px; color: var(--muted); }
.pop-sel { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 8px; padding: 6px 8px; font-size: 13px; }
.pop-years { display: flex; flex-wrap: wrap; gap: 5px; max-width: 190px; }
.yr { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 8px; padding: 4px 10px; font-size: 12.5px; cursor: pointer; }
.yr.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.pop-hint { font-size: 11px; color: var(--muted); }
.pop-dates { display: flex; gap: 6px; align-items: center; }
.pop-dates .arr { color: var(--muted); }
.pop-apply { border: 1px solid var(--accent); background: var(--accent); color: #fff; border-radius: 8px; padding: 6px 12px; font-size: 12.5px; cursor: pointer; }
.pop-apply:disabled { opacity: .45; cursor: default; }
.chip { border: 1px solid var(--line); background: var(--panel); color: var(--text);
  border-radius: 999px; padding: 5px 13px; font-size: 13px; cursor: pointer; transition: all .12s; }
.chip:hover { border-color: var(--accent); }
.chip.on { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.hint { color: var(--muted); font-size: 12px; margin-top: 8px; }
.chip-sep { color: var(--muted); padding: 0 2px; }
.qf-select, .qf-date { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 999px; padding: 4px 10px; font-size: 12.5px; }
.qf-select:focus, .qf-date:focus { outline: none; border-color: var(--accent); }
.chip-ghosty { opacity: .85; }
.cmp-pick { display: flex; gap: 5px; flex-wrap: wrap; }
.cmp-pick .chip { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 999px; padding: 4px 11px; font-size: 12.5px; cursor: pointer; }
.cmp-pick .chip.on { background: var(--accent); border-color: var(--accent); color: #fff; }
.up { color: var(--ok); } .down { color: var(--err); }
</style>