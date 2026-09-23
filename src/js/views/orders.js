// Вкладка «Заказы»: таблица + поиск + фильтр периода/статуса.
import { api, fmtMoney, fmtDate, fmtNum } from "../common.js";

export default {
  data: () => ({ loading: true, error: "", rows: [], total: 0, page: 1, per: 50,
                 q: "", status: "", from: "", to: "", statuses: [] }),
  watch: { q() { this.debounced(); }, status() { this.load(); }, from() { this.load(); }, to() { this.load(); }, page() { this.load(); } },
  created() { this.debounced = (() => { let t; return () => { clearTimeout(t); t = setTimeout(() => { this.page = 1; this.load(); }, 350); }; })(); },
  mounted() { this.load(); this.loadStatuses(); },
  methods: { api, fmtMoney, fmtDate, fmtNum,
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
  </div>`
};
