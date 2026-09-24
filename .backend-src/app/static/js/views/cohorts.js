// Вкладка «Точки»: активность/рост точек-продаж (филиалов).
import { api, fmtNum, fmtMln, fmtMoney, monthName, chartColors, makeChart, destroyChart } from "../common.js";

export default {
  data: () => ({ loading: true, error: "", j: null, chNew: null, chAct: null, chTop: null }),
  mounted() { this.load(); },
  beforeUnmount() { destroyChart(this.chNew); destroyChart(this.chAct); destroyChart(this.chTop); },
  methods: { api, fmtNum, fmtMln, fmtMoney,
    async load() {
      this.loading = true;
      try {
        this.j = await this.api("/api/cohorts");
        this.$nextTick(() => { this.drawNew(); this.drawAct(); this.drawTop(); });
      } catch (e) { this.error = String(e); }
      this.loading = false;
    },
    yLabel(m) { return (m || "").slice(0, 4); },
    mLabel(m) { const y = (m || "").slice(2, 4), mm = +(m || "0").slice(5, 7); return `${y}/${String(mm).padStart(2, "0")}`; },
    drawNew() {
      if (!this.j || !this.$refs.chNew) return;
      const C = chartColors();
      if (this.chNew) this.chNew.destroy();
      const byYear = {};
      this.j.new_by_month.forEach(x => { byYear[x.month.slice(0, 4)] = (byYear[x.month.slice(0, 4)] || 0) + x.newcnt; });
      this.chNew = makeChart(this.$refs.chNew, "bar", {
        labels: Object.keys(byYear),
        datasets: [{ label: "Новые точки-продаж, шт/год", data: Object.values(byYear), backgroundColor: "rgba(37,99,235,.6)" }],
      }, { scales: { y: { beginAtZero: true, ticks: { color: C.muted, precision: 0 }, grid: { color: C.border } },
                     x: { ticks: { color: C.text }, grid: { display: false } } },
           plugins: { legend: { display: false } } });
    },
    drawAct() {
      if (!this.j || !this.$refs.chAct) return;
      const C = chartColors();
      if (this.chAct) this.chAct.destroy();
      const a = this.j.active_by_month;
      this.chAct = makeChart(this.$refs.chAct, "line", {
        labels: a.map(x => this.mLabel(x.month)),
        datasets: [
          { label: "Активных точек", data: a.map(x => x.active_branches), borderColor: C.accent, tension: .3, pointRadius: 0, borderWidth: 2, fill: false },
          { label: "Заказов, шт (x0.05)", data: a.map(x => x.orders_cnt * 0.05), borderColor: C.orange || "#f59e0b", tension: .3, pointRadius: 0, borderWidth: 1.5, fill: false },
        ],
      }, { scales: { x: { ticks: { color: C.muted, maxTicksLimit: 18 }, grid: { display: false } },
                     y: { ticks: { color: C.muted }, grid: { color: C.border } } },
           plugins: { legend: { labels: { color: C.text, boxWidth: 12 } } } });
    },
    drawTop() {
      if (!this.j || !this.$refs.chTop) return;
      const C = chartColors();
      if (this.chTop) this.chTop.destroy();
      const t = this.j.top_branches.slice(0, 12);
      this.chTop = makeChart(this.$refs.chTop, "bar", {
        labels: t.map(x => x.branch),
        datasets: [{ label: "Выручка, млн (12 мес)", data: t.map(x => +(x.revenue / 1e6).toFixed(1)), backgroundColor: "rgba(22,163,74,.6)" }],
      }, { indexAxis: "y", scales: { x: { ticks: { color: C.muted }, grid: { color: C.border } },
                                     y: { ticks: { color: C.text, font: { size: 11 } }, grid: { display: false } } },
           plugins: { legend: { display: false } } });
    },
  },
  template: `
  <div>
    <h1 class="page-title">Точки-продаж</h1>
    <p class="page-sub">Рост и повторяемость заказов по филиалам</p>
    <div v-if="loading" class="loading">Считаем когорты…</div>
    <div v-else>
      <div class="kpis" style="margin-bottom:14px">
        <div class="kpi"><div class="l">Точек-всего (исторически)</div><div class="v">{{ (j.new_by_month.reduce((a, x) => a + x.newcnt, 0)) }}</div></div>
        <div class="kpi"><div class="l">Активно сейчас</div><div class="v">{{ (j.active_by_month.at(-1) || {}).active_branches || 0 }}</div></div>
        <div class="kpi"><div class="l">Повтор-заказ-в-3мес</div><div class="v" style="font-size:17px">стабильно 100%</div></div>
        <div class="kpi"><div class="l">Точка-лидер (12м)</div><div class="d" style="font-size:15px; color:var(--text)">{{ (j.top_branches[0] || {}).branch || "—" }} · {{ fmtMln((j.top_branches[0] || {}).revenue || 0) }}</div></div>
      </div>
      <div class="grid2">
        <div class="card"><h3>Новые точки-продаж по годам</h3><div class="chart-box"><canvas ref="chNew"></canvas></div></div>
        <div class="card"><h3>Активные точки по месяцам</h3><div class="chart-box"><canvas ref="chAct"></canvas></div></div>
      </div>
      <div class="card"><h3>Топ-точек по выручке (12 мес)</h3><div class="chart-box" style="height:340px"><canvas ref="chTop"></canvas></div></div>
    </div>
  </div>`
};
