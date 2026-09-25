<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
type Rap = { label: string; fn: () => void; on: () => boolean }
const rapid: Rap[] = [
  { label: 'Сегодня',  fn: today,    on: () => fromDate.value === iso(new Date()) && toDate.value === fromDate.value },
  { label: 'Вчера',    fn: () => { const d = new Date(); d.setDate(d.getDate() - 1); setRange(d, d) },
                       on: () => { const d = new Date(); d.setDate(d.getDate() - 1); return fromDate.value === iso(d) && toDate.value === fromDate.value } },
  { label: '7 дней',   fn: week7,    on: () => { const a = new Date(); a.setDate(a.getDate() - 6); return fromDate.value === iso(a) && !!toDate.value } },
  { label: 'Эта нед.', fn: weekThis, on: () => { const n = new Date(); const dow = (n.getDay() + 6) % 7; const m = new Date(n); m.setDate(n.getDate() - dow); return fromDate.value === iso(m) && !!toDate.value } },
  { label: 'Месяц',    fn: monthThis, on: () => fromDate.value === iso(new Date(new Date().getFullYear(), new Date().getMonth(), 1)) && !!toDate.value },
]

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
const totalPages = computed(() => Math.max(1, Math.ceil((orders.data.value?.total ?? 0) / PAGE)))

const csvUrl = computed(() => {
  const p = new URLSearchParams()
  if (q.value) p.set('q', q.value)
  if (status.value) p.set('status', status.value)
  if (fromDate.value) p.set('date_from', fromDate.value)
  if (toDate.value) p.set('date_to', toDate.value)
  return `/api/export/orders.csv?${p.toString()}`
})

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
</script>

<template>
  <h1>Заказы</h1>
  <div class="panel">
    <!-- строка 1: быстрые фильтры -->
    <div class="qf-row">
      <div class="qf-group">
        <button v-for="r in rapid" :key="r.label" class="chip" :class="{ on: r.on() }" @click="r.fn()">{{ r.label }}</button>
      </div>
      <span class="qf-total">{{ totalShown ? totalShown.toLocaleString('ru-RU') + ' зак.' : '—' }}</span>
      <button v-if="hasFilter" class="chip-ghost" @click="clearAll">✕ сброс</button>
    </div>

    <!-- строка 2: точные фильтры -->
    <div class="filters2">
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
        <button :disabled="page <= 1" @click="page--">←</button>
        <span>стр. {{ page }} из {{ totalPages }} · всего {{ fmtInt(orders.data.value?.total ?? 0) }}</span>
        <button :disabled="page >= totalPages" @click="page++">→</button>
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
          <h3>Позиции</h3>
          <table>
            <thead><tr><th>Наименование</th><th class="num">Кол-во</th><th class="num">Цена</th><th class="num">Сумма</th></tr></thead>
            <tbody>
              <tr v-for="(it, i) in (dossier.data.value.items ?? [])" :key="i">
                <td class="ellipsis" :title="it.name">{{ it.name }}</td>
                <td class="num">{{ it.qty }}</td><td class="num">{{ fmtMoney(it.price) }}</td><td class="num">{{ fmtMoney(it.total) }}</td>
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
</style>
