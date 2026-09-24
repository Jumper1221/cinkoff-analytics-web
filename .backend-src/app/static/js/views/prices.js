// Вкладка «Цены»: история по товару (version_date) + сравнение филиалов.
import { api, fmtMoney, fmtDate, chartColors, makeChart } from "../common.js";
let ch = null;
export default {
  data: () => ({ loading: false, error: "", q: "", results: [], sel: null, history: [], spreadChart: null, spreadRows: [], spreadPct: 0 }),
  created() { this.debSearch = (() => { let t; return () => { clearTimeout(t); t = setTimeout(this.search, 350); }; })(); },
  methods: { api, fmtMoney, chartColors, makeChart, fmtDate,
    async search() {
      if (this.q.length < 2) { this.results = []; return; }
      this.loading = true;
      try { this.results = await api("/api/catalog/search", { s: this.q, limit: 15 }); }
      catch (e) { this.error = String(e); }
      this.loading = false;
    },
    async pick(r) {
      this.sel = r;
      this.history = await api(`/api/catalog/price_history/${r.id_1c}`);
      this.$nextTick(() => this.draw());
    },
    draw() {
      const C = chartColors();
      if (ch) ch.destroy();
      const byDate = {};
      this.history.forEach(h => { (byDate[h.version_date?.slice(0,10)] ||= []).push(h); });
      const labels = Object.keys(byDate).sort();
      const data = labels.map(d => Math.min(...byDate[d].map(h => +h.discount_price || +h.price)));
      ch = makeChart("c-price", {
        type: "line",
        data: { labels, datasets: [{ label: this.sel?.full_name?.slice(0, 40), data, borderColor: C.accent, tension: .3, pointRadius: 2 }] },
        options: { maintainAspectRatio: false, plugins: { legend: { labels: { color: C.text } } },
                   scales: { x: { ticks: { color: C.muted, maxTicksLimit: 12 }, grid: { color: C.border } },
                             y: { ticks: { color: C.muted }, grid: { color: C.border } } } },
      });
    },
  },
  template: `
  <div>
    <h1 class="page-title">Цены</h1>
    <p class="page-sub">История прайса (version_date) · 6.7M строк</p>
    <div class="controls"><input type="search" v-model="q" @input="debSearch && debSearch()" placeholder="Товар для истории цены…" style="min-width:320px"></div>
    <div v-if="results.length && !sel" class="card" style="margin-bottom:14px">
      <div v-for="r in results" :key="r.id_1c" @click="pick(r)" style="padding:6px 4px; cursor:pointer">
        {{ r.full_name && r.full_name.slice(0, 80) }} <span class="badge">выбрать</span>
      </div>
    </div>
    <div class="card" v-if="sel">
      <h3>{{ sel.full_name && sel.full_name.slice(0, 90) }}</h3>
      <div class="chart-box"><canvas id="c-price"></canvas></div>
      <table class="data" style="margin-top:12px">
        <thead><tr><th>Версия</th><th>Филиал</th><th>Цена</th><th>Скидка</th></tr></thead>
        <tbody><tr v-for="(h, i) in history.slice(0, 40)" :key="i"><td>{{ (h.version_date||"").slice(0,10) }}</td><td>{{ h.branch }}</td><td class="num">{{ fmtMoney(h.price,2) }}</td><td class="num">{{ fmtMoney(h.discount_price,2) }}</td></tr></tbody>
      </table>
    </div>
  </div>`
};
