// Вкладка «Заказы»: таблица + поиск + фильтр периода/статуса.
import { api, fmtMoney, fmtDate, fmtNum } from "../common.js";

export default {
  data: () => ({ loading: true, error: "", rows: [], total: 0, page: 1, per: 50,
                 q: "", status: "", from: "", to: "", statuses: [], dossierOpen: false, dossier: null, dossierError: "" }),
  watch: { q() { this.debounced(); }, status() { this.load(); }, from() { this.load(); }, to() { this.load(); }, page() { this.load(); } },
  created() { this.debounced = (() => { let t; return () => { clearTimeout(t); t = setTimeout(() => { this.page = 1; this.load(); }, 350); }; })(); },
  mounted() { this.load(); this.loadStatuses(); },
  methods: { api, fmtMoney, fmtDate, fmtNum,
    async openOrder(oid) {
      this.dossier = null; this.dossierOpen = true; this.dossierError = "";
      try { this.dossier = await this.api(`/api/order/${oid}/full`); }
      catch (e) { this.dossierError = String(e); }
    },
    closeDossier() { this.dossierOpen = false; this.dossier = null; this.dossierError = ""; },
    async load() {
      this.loading = true;
      try {
        const j = await api("/api/orders", { q: this.q, status: this.status, from: this.from, to: this.to, page: this.page, per: this.per });
        this.rows = j.items; this.total = j.total;
      } catch (e) { this.error = String(e); }
      this.loading = false;
    },
    async loadStatuses() { try { const s = await api("/api/status_breakdown", { days: 0 }); this.statuses = s.map(x => x.status); } catch {} },
    totalPages() { return Math.max(1, Math.ceil(this.total / this.per)); },
    prev() { if (this.page > 1) this.page--; },
    next() { if (this.page < this.totalPages()) this.page++; },
  },
  beforeUnmount() { clearTimeout(this._t); },
  template: `
  <div>
    <h1 class="page-title">Заказы</h1>
    <p class="page-sub">{{ total }} заказов · страница {{ page }} из {{ totalPages() }}</p>
    <div class="controls">
      <input type="search" v-model="q" placeholder="Поиск: номер, контрагент…" style="min-width:280px">
      <select v-model="status"><option value="">Все статусы</option><option v-for="s in statuses" :value="s">{{ s }}</option></select>
      <input type="date" v-model="from" title="с даты">
      <input type="date" v-model="to" title="по дату">
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <table v-else class="data">
      <thead><tr><th>Номер</th><th>Дата</th><th>Контрагент</th><th>Филиал</th><th>Статус</th><th class="num">Сумма</th></tr></thead>
      <tbody>
        <tr v-for="r in rows" :key="r.order_id">
          <td>{{ r.number }}</td><td>{{ fmtDate(r.order_date) }}</td><td>{{ r.contractor_name }}</td>
          <td>{{ r.branch_name }}</td><td><span class="badge">{{ r.order_status }}</span></td><td class="num">{{ fmtMoney(r.sum) }}</td>
        </tr>
      </tbody>
    </table>
    <div class="pager">
      <button class="ghost" @click="prev" :disabled="page<=1">←</button>
      <span>{{ page }} / {{ totalPages() }}</span>
      <button class="ghost" @click="next" :disabled="page>=totalPages()">→</button>
    </div>
    <div v-if="dossierOpen" class="modal-mask" @click.self="closeDossier">
    <div class="modal" v-if="dossier">
      <button class="modal-x" @click="closeDossier">×</button>
      <h2>Заказ {{ dossier.head.number }} <span class="badge">{{ dossier.head.order_status }}</span></h2>
      <p class="muted">{{ dossier.head.contractor_name }} · {{ dossier.head.branch_name }} · дата: {{ fmtDate(dossier.head.order_date) }} · сумма: <b>{{ fmtMoney(dossier.head.sum) }}</b></p>
      <div class="grid2">
        <div class="card"><h3>Позиции ({{ dossier.items.length }})</h3>
          <table class="data">
            <thead><tr><th>Название</th><th>Кол-во</th><th>Цена</th><th>Скидка</th><th>Сумма</th></tr></thead>
            <tbody><tr v-for="(it, i) in dossier.items" :key="i">
              <td>{{ (it.name || "—").slice(0, 55) }}</td><td class="num">{{ it.quantity }}</td>
              <td class="num">{{ fmtMoney(it.price) }}</td><td class="num">{{ it.discount_pct ? it.discount_pct + "%" : "—" }}</td>
              <td class="num"><b>{{ fmtMoney(it.total) }}</b></td>
            </tr></tbody>
          </table>
        </div>
        <div>
          <div class="card" v-if="dossier.shipments.length"><h3>Отгрузки</h3>
            <table class="data"><tbody>
              <tr v-for="(sp, i) in dossier.shipments" :key="i">
                <td>{{ sp.shipment_number || "б/н" }}</td><td>{{ sp.state || "—" }}</td>
                <td>{{ (sp.driver_name || "—") + " " + (sp.driver_phone || "") }}</td><td class="badge">{{ sp.source }}</td>
              </tr>
            </tbody></table>
          </div>
          <div class="card" v-if="dossier.sales.length"><h3>Реализации</h3>
            <table class="data"><tbody>
              <tr v-for="(sl, i) in dossier.sales" :key="i">
                <td>{{ sl.number }}</td><td>{{ sl.posted ? "проведён" : "не пров." }}</td>
                <td class="num">{{ fmtMoney(sl.total_sum) }}</td><td>{{ (sl.sales_date || "").slice(0,10) }}</td>
              </tr>
            </tbody></table>
          </div>
          <div class="card" v-if="dossier.demand_items.length"><h3>Отгружено (demand)</h3>
            <table class="data"><tbody>
              <tr v-for="(d, i) in dossier.demand_items.slice(0, 10)" :key="i">
                <td>{{ (d.name || "—").slice(0, 45) }}</td><td class="num">{{ d.quantity }}</td><td class="num">{{ fmtMoney(d.total) }}</td>
              </tr>
            </tbody></table>
          </div>
        </div>
      </div>
    </div>
    <div class="modal" v-else><div class="loading">Загрузка досье…</div></div>
  </div>
</div>`
};
