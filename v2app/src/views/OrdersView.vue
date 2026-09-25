<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useApi, fmtInt, fmtMoney, fmtDate } from '../api/client'
import { useUiStore } from '../stores/ui'
import type { OrderRow, OrdersPage } from '../api/types'

const ui = useUiStore()
const PAGE = 50
const page = ref(1)
const q = ref('')
const status = ref('')
const fromDate = ref('')
const toDate = ref('')

/* ── Быстрые фильтры дат ── */
function iso(d: Date) { return d.toISOString().slice(0, 10) }
function setRange(from: Date | null, to: Date | null) {
  fromDate.value = from ? iso(from) : ''
  toDate.value = to ? iso(to) : ''
}
const today = () => { const d = new Date(); setRange(d, d) }
const yesterday = () => { const d = new Date(); d.setDate(d.getDate() - 1); setRange(d, d) }
const week7 = () => { const a = new Date(); const b = new Date(); a.setDate(a.getDate() - 6); setRange(a, b) }
const weekThis = () => {
  const now = new Date(); const dow = (now.getDay() + 6) % 7  // 1=пн
  const mon = new Date(now); mon.setDate(now.getDate() - dow)
  setRange(mon, now)
}
const monthThis = () => { const n = new Date(); setRange(new Date(n.getFullYear(), n.getMonth(), 1), n) }

// ── Периоды: сегменты-быстрых (Сегодня/Вчера/7-дней/Эта-нед./Месяц) + кнопка-📅-с-поповером (месяц/год/свой) ──
const isoYM = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`
const YEARS = (() => { const y0 = 2019, y1 = new Date().getFullYear(); return Array.from({ length: y1 - y0 + 1 }, (_, i) => y1 - i) })()
const MONTHS_ALL = (() => { // последние-84-месяца (7-лет)
  const arr: string[] = []; const n = new Date()
  for (let i = 0; i < 84; i++) { const d = new Date(n.getFullYear(), n.getMonth() - i, 1); arr.push(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`) }
  return arr
})()
const MON_RU = ['', 'январь', 'февраль', 'март', 'апрель', 'май', 'июнь', 'июль', 'август', 'сентябрь', 'октябрь', 'ноябрь', 'декабрь']
const monthLabel = (ym: string) => { const [y, m] = ym.split('-'); return `${MON_RU[+m]} ${y}` }
const dd = (v: string) => (v ? v.slice(8) + '.' + v.slice(5, 7) + '.' + v.slice(2, 4) : '—')
const YEARS_ALL = YEARS  // с-2019

// поп-О-В-Е-Р-периода:
const popOpen = ref(false)
const fmMonth = ref(''); const fmYear = ref('')
const monthManual = ref(false); const yearManual = ref(false)
const watchMonth = () => { if (fmMonth.value) { const [y, m] = fmMonth.value.split('-'); const last = new Date(+y, +m, 0); const isCur = fmMonth.value === isoYM(new Date()); setRange(new Date(+y, +m - 1, 1), isCur ? new Date() : last); monthManual.value = true; yearManual.value = false; popOpen.value = false } }
const pickYear = (yv: string) => { const n = new Date(+yv, 0, 1); const isCur = +yv === new Date().getFullYear(); setRange(n, isCur ? new Date() : new Date(+yv, 11, 31)); yearManual.value = true; monthManual.value = false; popOpen.value = false }
function togglePop() { popOpen.value = !popOpen.value }
function onDocClick(e: MouseEvent) { const t = e.target as HTMLElement; if (!t.closest('.period-pop') && !t.closest('.btn-range')) popOpen.value = false }
function onKey(e: KeyboardEvent) { if (e.key === 'Escape') popOpen.value = false }
onMounted(() => { document.addEventListener('click', onDocClick); document.addEventListener('keydown', onKey) })
onBeforeUnmount(() => { document.removeEventListener('click', onDocClick); document.removeEventListener('keydown', onKey) })
function pickYearFromPopImpl(yv: string) { const n = new Date(+yv, 0, 1); const isCur = +yv === new Date().getFullYear(); setRange(n, isCur ? new Date() : new Date(+yv, 11, 31)); yearManual.value = true; monthManual.value = false; popOpen.value = false }

// лейбл-кнопки-периода: всегда-человек-П-О-Н-Я-Т-НО-(
const rangeLabel = computed(() => {
  if (monthManual.value && fmMonth.value) return monthLabel(fmMonth.value)
  if (yearManual.value && fmYear.value) return fmYear.value + ' год'
  if (fromDate.value && toDate.value) return (fromDate.value === toDate.value ? dd(fromDate.value) : dd(fromDate.value) + ' → ' + dd(toDate.value))
  return 'все-время'
})
const manualActive = computed(() => monthManual.value || yearManual.value)
function resetRange() { fromDate.value = ''; toDate.value = ''; monthManual.value = false; yearManual.value = false; fmMonth.value = ''; fmYear.value = ''; popOpen.value = false }
function setCustom() { if (cuFrom.value && cuTo.value) { setRange(new Date(cuFrom.value), new Date(cuTo.value)); monthManual.value = false; yearManual.value = false; popOpen.value = false } }
const cuFrom = ref(''); const cuTo = ref('')  // свой-диапазон-в-поповере

const qs = computed(() => {
  const p = new URLSearchParams({ limit: String(PAGE), offset: String((page.value - 1) * PAGE) })
  if (q.value) p.set('q', q.value)
  if (status.value) p.set('status', status.value)
  if (fromDate.value) p.set('since', fromDate.value)
  if (toDate.value) p.set('till', toDate.value)
  return `/api/orders?${p.toString()}`
})
const orders = useApi<OrdersPage>(() => qs.value)
watch([q, status, fromDate, toDate], () => { page.value = 1; orders.load() })
watch(page, () => { orders.load() })   // ← клик-по-странице-меняет-только-page: без-этого-watch-запрос-не-уходит
const totalPages = computed(() => Math.max(1, Math.ceil((orders.data.value?.total ?? 0) / PAGE)))

const csvUrl = computed(() => {
  const p = new URLSearchParams()
  if (q.value) p.set('q', q.value)
  if (status.value) p.set('status', status.value)
  if (fromDate.value) p.set('date_from', fromDate.value)
  if (toDate.value) p.set('date_to', toDate.value)
  return `/api/export/orders.csv?${p.toString()}`
})


/* ── страницы-с-многоточиями ── */
function pagesToShow(): (number | '...')[] {
  const T = totalPages.value, C = page.value
  if (T <= 7) return Array.from({length: T}, (_, i) => i + 1)
  const w = new Set<number>([1, 2, T - 1, T, C - 1, C, C + 1])
  const arr = [...w].filter(n => n >= 1 && n <= T).sort((a, b) => a - b)
  const out: (number | '...')[] = []
  let prev = 0
  for (const n of arr) {
    if (prev && n - prev > 1) out.push('...')
    out.push(n); prev = n
  }
  return out
}

const totalShown = computed(() => orders.data.value?.total ?? 0)
function clearAll() { q.value = ''; status.value = ''; fromDate.value = ''; toDate.value = '' }
const hasFilter = computed(() => !!(q.value || status.value || fromDate.value || toDate.value))

// досье
const dossier = useApi<any>(() => (sel.value ? `/api/order/${sel.value}/full` : ''), false)
const sel = ref<number | null>(null)
async function openOrder(id: number) {
  sel.value = id
  await dossier.load()
}
function closeOrder() { sel.value = null }

// ── «Обновить-данные»: фронт-→-POST /api/sync →-пул-статуса →-перезагрузка-таблицы ──
const syncRunning = ref(false)
const syncMsg = ref('')
const dataAsOf = ref('')
let syncTimer: number | undefined

function fmtAsOf(iso: string): string {
  if (!iso) return ''
  const d = new Date(iso.replace(' ', 'T'))
  return isNaN(+d) ? iso : d.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function pollSync() {
  try {
    const r = await fetch('/api/sync/status')
    const d = await r.json()
    if (d.data_as_of) dataAsOf.value = fmtAsOf(d.data_as_of)
    if (d.running) return                      // всё-ещё-идёт —- продолжаем-опрос
    if (syncTimer) { clearInterval(syncTimer); syncTimer = undefined }
    syncRunning.value = false
    if (d.ok === true) {
      syncMsg.value = d.result?.skipped ? String(d.result.skipped) : 'Данные обновлены'
      orders.load()                            // ← перечитываем-таблицу-свежими
    } else if (d.ok === false) {
      syncMsg.value = 'Ошибка: ' + (d.error || 'синк-не-завершился')
    }
    if (syncMsg.value) setTimeout(() => { syncMsg.value = '' }, 8000)
  } catch { /* сеть-молчит —- попробуем-на-след-тике */ }
}

async function startSync() {
  if (syncRunning.value) return
  syncRunning.value = true; syncMsg.value = ''
  try {
    const r = await fetch('/api/sync', { method: 'POST' })
    if (r.status === 409) { /* уже-идёт (напр.-крон) —- просто-продолжаем-ждать */ }
    else if (!r.ok) throw new Error('POST /api/sync → ' + r.status)
    syncTimer = window.setInterval(pollSync, 2500)
    pollSync()
  } catch (e: any) {
    syncRunning.value = false; syncMsg.value = 'Не-удалось-запустить-обновление'
  }
}
onMounted(async () => {
  try { const d = await (await fetch('/api/sync/status')).json(); if (d.data_as_of) dataAsOf.value = fmtAsOf(d.data_as_of) } catch {}
})
onBeforeUnmount(() => { if (syncTimer) clearInterval(syncTimer) })
</script>

<template>
  <h1>Заказы</h1>
  <div class="panel">
    <!-- строка 1: быстрые фильтры -->
    <div class="qf-row">
      <div class="qf-group" style="position: relative;">
        <div class="seg">
          <button class="seg-btn" :class="{ on: fromDate === iso(new Date()) && toDate === fromDate }" @click="today">Сегодня</button>
          <button class="seg-btn" :class="{ on: (() => { const d = new Date(); d.setDate(d.getDate() - 1); return fromDate === iso(d) && toDate === fromDate })() }" @click="yesterday">Вчера</button>
          <button class="seg-btn" :class="{ on: (() => { const a = new Date(); a.setDate(a.getDate() - 6); return fromDate === iso(a) && !!toDate })() }" @click="week7">7 дней</button>
          <button class="seg-btn" :class="{ on: (() => { const n = new Date(); const dow = (n.getDay() + 6) % 7; const m = new Date(n); m.setDate(n.getDate() - dow); return fromDate === iso(m) && !!toDate })() }" @click="weekThis">Эта нед.</button>
          <button class="seg-btn" :class="{ on: fromDate === iso(new Date(new Date().getFullYear(), new Date().getMonth(), 1)) && !!toDate }" @click="monthThis">Месяц</button>
        </div>
        <button class="btn-range" :class="{ act: manualActive }" @click.stop="togglePop" title="Месяц / год / свой-диапазон">📅 {{ rangeLabel }} <span class="caret">▾</span></button>
        <button v-if="manualActive" class="x-reset" @click="resetRange" title="Сбросить-период">✕</button>

        <div v-if="popOpen" class="period-pop" @click.stop>
          <div class="pop-col">
            <div class="pop-h3">Месяц</div>
            <select class="pop-sel" v-model="fmMonth" @change="watchMonth">
              <option value="">выбрать…</option>
              <option v-for="ym in MONTHS_ALL" :key="ym" :value="ym">{{ monthLabel(ym) }}</option>
            </select>
            <div class="pop-hint">месяц-целиком</div>
          </div>
          <div class="pop-sep"></div>
          <div class="pop-col">
            <div class="pop-h3">Год</div>
            <div class="pop-years">
              <button v-for="y in YEARS" :key="y" class="yr" :class="{ on: yearManual && fmYear === String(y) }" @click="pickYear(String(y))">{{ y }}</button>
            </div>
            <div class="pop-hint" v-if="yearManual && fmYear">{{ +fmYear === new Date().getFullYear() ? 'с-1-января-по-сегодня' : 'весь-год' }}</div>
          </div>
          <div class="pop-sep"></div>
          <div class="pop-col">
            <div class="pop-h3">Свой-диапазон</div>
            <div class="pop-dates">
              <input type="date" v-model="cuFrom" class="f-date2" />
              <span class="arr">→</span>
              <input type="date" v-model="cuTo" class="f-date2" />
            </div>
            <button class="pop-apply" :disabled="!cuFrom || !cuTo" @click="setCustom">Показать-за-период</button>
          </div>
        </div>
      </div>
      <span class="qf-total">{{ totalShown ? totalShown.toLocaleString('ru-RU') + ' зак.' : '—' }}</span>
      <button v-if="hasFilter" class="chip-ghost" @click="clearAll">✕ сброс</button>
    </div>

    <!-- строка 2: точные фильтры -->
    <div class="filters2">
      <button class="btn-sync" :class="{ busy: syncRunning }" :disabled="syncRunning" @click="startSync"
              :title="syncRunning ? 'Идёт-загрузка-данных-с-сервера-поставщика…' : 'Загрузить-свежие-заказы-с-сервера-поставщика'">
        <span v-if="!syncRunning">⟳ Обновить</span>
        <span v-else>⏳ Обновляется…</span>
      </button>
      <span v-if="syncMsg" class="sync-msg" :class="{ ok: syncMsg.startsWith('Д') || syncMsg.includes('крон') }">{{ syncMsg }}</span>
      <span v-else-if="dataAsOf" class="data-asof" :title="'Момент-последнего-обновления-данных'">данные-на {{ dataAsOf }}</span>
      <input v-model="q" class="f-search2" placeholder="🔍 номер / контрагент…" />
      <select v-model="status" class="f-select">
        <option value="">Все статусы</option>
        <option>Машина отгружена</option><option>Отгружен</option><option>Отменен</option>
        <option>Готов к отгрузке</option><option>Утвержден</option><option>Ожидает прихода ТМЦ</option>
        <option>Передан в производство</option><option>В пути</option><option>Рассматривается</option>
        <option>Планируется отгрузка</option><option>Передан на комплектацию</option>
      </select>
      <div class="datebox">
        <input v-model="fromDate" type="date" class="f-date2" title="с даты" />
        <span class="date-sep">→</span>
        <input v-model="toDate" type="date" class="f-date2" title="по дату" />
      </div>
      <a class="btn-csv" :href="csvUrl" title="Скачать выборку как CSV (до 5000 строк)">⬇ CSV</a>
    </div>

    <div v-if="orders.loading.value">
        <div v-for="r in 12" :key="r" class="skel skel-row" />
      </div>
    <div v-else-if="orders.error.value" class="err-text">{{ orders.error.value }}</div>
    <template v-else>
      <table>
        <thead><tr>
          <th>Номер</th><th>Дата</th><th>Контрагент</th><th>Филиал</th><th>Статус</th><th class="num">Сумма</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in (orders.data.value?.items ?? [])" :key="r.order_id" class="click" :title="'Досье ' + r.number" @click="openOrder(r.order_id)">
            <td>{{ r.number }}</td><td>{{ fmtDate(r.order_date) }}</td><td>{{ r.contractor_name }}</td>
            <td>{{ r.branch_name }}</td><td><span class="badge">{{ r.order_status }}</span></td>
            <td class="num">{{ fmtMoney(r.sum) }}</td>
          </tr>
          <tr v-if="!orders.data.value?.items?.length"><td colspan="6" class="empty"><span class="big">🔍</span>По этому фильтру заказов нет</td></tr>
        </tbody>
      </table>
      <div class="pager">
        <button :disabled="page <= 1" @click="page = 1" title="В начало">«</button>
        <button :disabled="page <= 1" @click="page--" title="Назад">←</button>
        <template v-for="(p, i) in pagesToShow()" :key="i">
          <span v-if="p === '...'" class="pg-dots">…</span>
          <button v-else :class="{ cur: p === page }" @click="page = p">{{ p }}</button>
        </template>
        <button :disabled="page >= totalPages" @click="page++" title="Вперёд">→</button>
        <button :disabled="page >= totalPages" @click="page = totalPages" title="В конец">»</button>
        <span class="pg-info">{{ fmtInt(orders.data.value?.total ?? 0) }} заказов</span>
      </div>
    </template>
  </div>

  <!-- досье-модалка -->
  <Teleport to="body">
    <div v-if="sel" class="mask" @click.self="closeOrder">
      <div class="modal">
        <button class="x" @click="closeOrder">✕</button>
        <div v-if="dossier.loading.value" class="muted">Загрузка досье…</div>
        <div v-else-if="dossier.error.value || !dossier.data.value" class="err-text">{{ dossier.error.value || 'Нет данных' }}</div>
        <template v-else>
          <h2>{{ dossier.data.value.head?.number }} · {{ fmtMoney(dossier.data.value.head?.sum) }}</h2>
          <p class="muted">{{ dossier.data.value.head?.order_status }} · {{ dossier.data.value.head?.contractor_name }} · {{ dossier.data.value.head?.branch_name }} · {{ fmtDate(dossier.data.value.head?.order_date) }}</p>
          <p class="muted">Ответственный: {{ dossier.data.value.head?.demand_responsible || '—' }}</p>
          <h3>Позиции</h3>
          <table>
            <thead><tr><th>Наименование</th><th class="num">Кол-во</th><th class="num">Цена</th><th class="num">Сумма</th></tr></thead>
            <tbody>
              <tr v-for="(it, i) in (dossier.data.value.items ?? [])" :key="i">
                <td class="ellipsis" :title="it.name">{{ it.name }}</td>
                <td class="num">{{ it.quantity ?? it.qty }}</td><td class="num">{{ fmtMoney(it.price) }}</td><td class="num">{{ fmtMoney(it.total) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.qf-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 10px; }
.qf-group { display: flex; gap: 6px; flex-wrap: wrap; }
.chip { border: 1px solid var(--line); background: var(--panel); color: var(--text);
  border-radius: 999px; padding: 5px 13px; font-size: 13px; cursor: pointer; transition: all .12s; }
.chip:hover { border-color: var(--accent); }
.chip.on { background: var(--accent); border-color: var(--accent); color: #fff; font-weight: 600; }
.chip-ghost { border: none; background: none; color: var(--muted); cursor: pointer; font-size: 12px; padding: 4px 6px; }
.chip-ghost:hover { color: var(--err); }
.qf-total { margin-left: auto; color: var(--muted); font-size: 12px; font-variant-numeric: tabular-nums; }

.filters2 { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.f-search2 { flex: 1 1 210px; min-width: 180px; padding: 7px 11px; border: 1px solid var(--line);
  border-radius: 9px; background: var(--bg); color: var(--text); font-size: 13.5px; }
.f-select { padding: 7px 9px; border: 1px solid var(--line); border-radius: 9px;
  background: var(--bg); color: var(--text); font-size: 13.5px; max-width: 200px; }
.datebox { display: inline-flex; align-items: center; border: 1px solid var(--line); border-radius: 9px; background: var(--bg); overflow: hidden; }
.f-date2, .f-date2input { border: none; background: transparent; color: var(--text); padding: 6px 8px; font-size: 13px; }
.date-sep { color: var(--muted); }
.btn-csv { display: inline-flex; align-items: center; gap: 5px; padding: 7px 15px; margin-left: auto;
  background: var(--accent); color: #fff; border-radius: 9px; font-weight: 600; font-size: 13px;
  border: none; cursor: pointer; }
.btn-csv:hover { filter: brightness(1.08); }

.seg { display: inline-flex; border: 1px solid var(--line); border-radius: 999px; overflow: hidden; }
.seg-btn { border: 0; background: transparent; color: var(--text); padding: 6px 14px; font-size: 13px; cursor: pointer; border-right: 1px solid var(--line); }
.btn-range { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 999px; padding: 6px 14px; font-size: 13px; cursor: pointer; display: inline-flex; gap: 6px; align-items: center; }
.x-reset { border: 1px solid var(--line); background: var(--panel); color: var(--muted); border-radius: 50%; width: 26px; height: 26px; cursor: pointer; line-height: 1; }
.period-pop { position: absolute; top: calc(100% + 8px); right: 0; z-index: 30; display: flex; background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 8px 28px rgba(0,0,0,.14); padding: 14px 6px; width: max-content; max-width: min(720px, calc(100vw - 320px)); }
.pop-col { padding: 0 14px; display: flex; flex-direction: column; gap: 8px; min-width: 0; }
.pop-sep { width: 1px; background: var(--line); }
.pop-sel { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 8px; padding: 6px 8px; font-size: 13px; }
.pop-years { display: flex; flex-wrap: wrap; gap: 5px; max-width: 210px; }
.yr { border: 1px solid var(--line); background: var(--panel); color: var(--text); border-radius: 8px; padding: 4px 10px; font-size: 12.5px; cursor: pointer; }
.pop-hint { font-size: 11px; color: var(--muted); }
.pop-dates { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.pop-apply { border: 1px solid var(--accent); background: var(--accent); color: #fff; border-radius: 8px; padding: 6px 12px; font-size: 12.5px; cursor: pointer; }
</style>
