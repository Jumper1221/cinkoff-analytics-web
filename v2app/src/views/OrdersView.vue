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

const qs = computed(() => {
  const p = new URLSearchParams({ limit: String(PAGE), offset: String((page.value - 1) * PAGE) })
  if (q.value) p.set('q', q.value)
  if (status.value) p.set('status', status.value)
  if (fromDate.value) p.set('from', fromDate.value)
  if (toDate.value) p.set('to', toDate.value)
  return `/api/orders?${p.toString()}`
})
const orders = useApi<OrdersPage>(() => qs.value)
watch([q, status, fromDate, toDate], () => { page.value = 1; orders.load() })
const totalPages = computed(() => Math.max(1, Math.ceil((orders.data.value?.total ?? 0) / PAGE)))

const csvUrl = computed(() => {
  const p = new URLSearchParams()
  if (q.value) p.set('q', q.value)
  if (status.value) p.set('status', status.value)
  if (fromDate.value) p.set('from', fromDate.value)
  if (toDate.value) p.set('to', toDate.value)
  return `/api/export/orders.csv?${p.toString()}`
})

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
    <div class="filters">
      <input v-model="q" class="f-search" placeholder="поиск: номер/контрагент…" />
      <input v-model="status" class="f-status" placeholder="статус" list="st-list" />
      <datalist id="st-list">
        <option>Машина отгружена</option><option>Отгружен</option><option>Отменен</option>
        <option>Готов к отгрузке</option><option>Утвержден</option><option>Ожидает прихода ТМЦ</option>
      </datalist>
      <input v-model="fromDate" type="date" class="f-date" />
      <input v-model="toDate" type="date" class="f-date" />
      <a class="csv" :href="csvUrl">CSV</a>
    </div>
    <div v-if="orders.loading.value" class="muted">Загрузка…</div>
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
          <tr v-if="!orders.data.value?.items?.length"><td colspan="6" class="muted">Ничего не найдено</td></tr>
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
