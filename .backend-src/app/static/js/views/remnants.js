// Вкладка «Остатки»: снапшоты (товар x склад) — топ-наличие.
import { api, fmtNum, fmtDate, chartColors } from "../common.js";

export default {
  data: () => ({ remHist: null, remHistChart: null, loading: true, error: "", rows: [], kind: "metall", snaps: [], snap: "" }),
  watch: { kind() { this.load(); }, snap() { this.load(); } },
  mounted() { this.load(); this.loadSnaps(); this.loadHistory(); },

  methods: {
    async loadHistory() {
      try {
        this.remHist = await this.api("/api/remnants/history");
        this.$nextTick(() => this.drawRemHist());
      } catch (e) { /* тихо: 1-й снапшот — история появится позже */ }
    },
    drawRemHist() {
      if (!this.remHist || !this.remHist.series.metall || !this.$refs.remHist) return;
      const C = chartColors();
      const pts = this.remHist.series.metall;
      if (this.remHistChart) this.remHistChart.destroy();
      this.remHistChart = new Chart(this.$refs.remHist, {
        type: "line",
        data: { labels: pts.map(p => p.date),
                datasets: [
                  { label: "Металл, шт", data: pts.map(p => p.qty), borderColor: C.accent, tension: .25, pointRadius: 3 },
                  { label: "Товары, шт", data: (this.remHist.series.goods || []).map(p => p.qty), borderColor: C.orange || "#f59e0b", tension: .25, pointRadius: 3 },
                ] },
        options: { maintainAspectRatio: false,
                   scales: { x: { ticks: { color: C.muted }, grid: { display: false } },
                             y: { ticks: { color: C.muted, callback: (v) => (v/1e6).toFixed(1) + "M" }, grid: { color: C.border } } },
                   plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } },
      });
    }, api, fmtNum,
    async load() {
      this.loading = true;
      try { this.rows = await api("/api/remnants", { kind: this.kind, date: this.snap, limit: 200 }); }
      catch (e) { this.error = String(e); }
      this.loading = false;
    },
    async loadSnaps() { try { this.snaps = (await api("/api/remnants/dates")).dates; } catch {} },
  },
  template: `
  <div>
    <h1 class="page-title">Остатки</h1>
    <p class="page-sub">Снапшот 2026-09-23 · 1.23 млн строк (товар × склад)</p>
    <div class="controls">
      <div class="seg">
        <button :class="{active: kind==='metall'}" @click="kind='metall'">Металл</button>
        <button :class="{active: kind==='goods'}" @click="kind='goods'">Товары</button>
        <button :class="{active: kind==='delivery'}" @click="kind='delivery'">Ожид. поставки</button>
      </div>
    </div>
    <div class="card" style="margin-bottom:14px">
      <h3>Динамика остатков <span class="muted" style="font-weight:400; font-size:12px">(снапшотов: {{ (remHist && remHist.dates.length) || 0 }})</span></h3>
      <div class="chart-box" style="height:220px"><canvas ref="remHist"></canvas></div>
      <p class="muted" style="margin:6px 0 0; font-size:12px" v-if="!remHist || remHist.dates.length < 2">Один снапшот. Еженедельный крон начнёт копить историю — здесь появится линия.</p>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <table class="data">
      <thead><tr><th>Товар</th><th>Склад / филиал</th><th class="num">Кол-во</th><th v-if="kind==='delivery'">Дата прихода</th></tr></thead>
      <tbody>
        <tr v-for="(r, i) in rows" :key="i">
          <td>{{ r.full_name || r.nomenclature_id }}</td><td>{{ r.branch || r.storage_id }}</td>
          <td class="num">{{ fmtNum(r.qty) }}</td><td v-if="kind==='delivery'">{{ r.delivery_date }}</td>
        </tr>
      </tbody>
    </table>
  </div>`
};
