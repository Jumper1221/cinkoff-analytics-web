// Вьюха «Дашборд»: KPI, заказы по месяцам, по годам, топы.
import { api, fmtMoney, fmtNum, fmtMln, monthName, chartColors, makeChart, destroyChart } from "../common.js";

let chartMonths = null, chartStatus = null, chartTop = null;

export default {
  data: () => ({ loading: true, error: "", kpi: null, years: [], months: [], contractors: [], topItems: [], statuses: [], fresh: {},
  cmp: null, cmpKind: "month", cmpAnchor: "", cmpLoading: false, cmpError: "" }),
  async mounted() {
    try {
      const [kpi, years, months, contractors, topItems, statuses, fresh] = await Promise.all([
        api("/api/kpi"), api("/api/years"), api("/api/monthly?months=24"),
        api("/api/top/contractors?limit=10"), api("/api/top/items?limit=10"),
        api("/api/status_breakdown", {days: 365}), api("/api/freshness"),
      ]);
      this.kpi = kpi; this.years = years; this.months = months;
      this.contractors = contractors; this.topItems = topItems; this.statuses = statuses; this.fresh = fresh;
    } catch (e) { this.error = String(e); }
    this.loading = false;
    await this.$nextTick();
    this.loadCompare();
    this.renderAll();
    this._unwatch = this.$watch(() => document.documentElement.dataset.theme, () => this.renderAll(), { deep: false });
    window.addEventListener("resize", this.renderAll = this.renderAll || (() => this.renderAll.call(this)));
  },
  beforeUnmount() { this._unwatch && this._unwatch(); },
  methods: { fmtMoney, fmtNum, fmtMln, monthName, api, chartColors, makeChart,
    async loadCompare() {
      this.cmpLoading = true; this.cmpError = "";
      try {
        this.cmp = await this.api("/api/compare", { period: this.cmpKind, anchor: this.cmpAnchor, steps: 2 });
      } catch (e) { this.cmpError = String(e); }
      this.cmpLoading = false;
    },
    setAnchor(ev) { this.cmpAnchor = ev.target.value; this.loadCompare(); },
   renderAll() { this.renderMonths(); this.renderStatus(); this.renderTop(); },
    renderMonths() {
      const C = chartColors();
      if (chartMonths) chartMonths.destroy();
      this.chartMonths = makeChart("c-months", {
        type: "bar",
        data: {
          labels: this.months.map(m => `${monthName(m.month)} '${String(m.year).slice(2)}`),
          datasets: [
            { label: "Сумма, млн ₽", data: this.months.map(m => +(m.total / 1e6).toFixed(2)),
              backgroundColor: C.accent + "99", borderRadius: 4, yAxisID: "y" },
            { type: "line", label: "Заказов, шт", data: this.months.map(m => m.cnt),
              borderColor: C.orange, backgroundColor: C.orange, tension: .35, pointRadius: 2, yAxisID: "y2" },
          ],
        },
        options: {
          responsive: true, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
          scales: {
            y:  { position: "left",  title: { display: true, text: "млн ₽" }, ticks: { color: C.muted }, grid: { color: C.border } },
            y2: { position: "right", title: { display: true, text: "шт" },    ticks: { color: C.muted }, grid: { drawOnChartArea: false } },
            x:  { ticks: { color: C.muted, maxRotation: 45, autoSkip: true, maxTicksLimit: 24 }, grid: { display: false } },
          },
          plugins: { legend: { labels: { color: C.text } }, tooltip: { callbacks: { label: (c) => `${c.dataset.label}: ${c.formattedValue}` } } },
        },
      });
    },
    renderStatus() {
      const C = chartColors();
      if (chartStatus) chartStatus.destroy();
      chartStatus = makeChart("c-status", {
        type: "doughnut",
        data: { labels: this.statuses.map(s => s.status),
                datasets: [{ data: this.statuses.map(s => s.cnt),
                             backgroundColor: [C.accent, C.green, C.orange, C.red, "#8b5cf6", "#14b8a6", "#f472b6"] }] },
        options: { maintainAspectRatio: false, plugins: { legend: { position: "right", labels: { color: C.text, boxWidth: 12 } } } },
      });
    },
    renderTop() {
      const C = chartColors();
      if (chartTop) chartTop.destroy();
      chartTop = makeChart("c-top", {
        type: "bar",
        data: { labels: this.topItems.map(t => t.name.slice(0, 30)),
                datasets: [{ label: "Выручка, млн", data: this.topItems.map(t => +(t.revenue / 1e6).toFixed(2)),
                             backgroundColor: C.green + "88", borderRadius: 4 }] },
        options: { indexAxis: "y", maintainAspectRatio: false,
                   plugins: { legend: { display: false } },
                   scales: { x: { ticks: { color: C.muted }, grid: { color: C.border } },
                             y:  { ticks: { color: C.muted }, grid: { display: false } } } },
      });
    },
  },
  template: `
  <div>
    <h1 class="page-title">Дашборд</h1>
    <p class="page-sub">Всё по заказам с 2019 · обновлено: {{ fresh && fresh.last_order ? fresh.last_order : "…" }}</p>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-else-if="loading">
      <div class="kpis">
        <div class="kpi" v-for="i in 5" :key="i"><div class="skeleton" style="height:24px"></div><div class="skeleton" style="height:12px; width:60%"></div></div>
      </div>
      <div class="card" style="height:360px"><div class="skeleton" style="height:100%"></div></div>
    </div>
    <template v-else>
      <div class="kpis">
        <div class="kpi"><div class="l">Заказов сегодня</div><div class="v">{{ kpi.orders_today }}</div></div>
        <div class="kpi"><div class="l">Заказов 30 дней</div><div class="v">{{ kpi.orders_30d }}</div><div class="d">{{ kpi.shipped_30 }} отгружено</div></div>
        <div class="kpi"><div class="l">Сумма 30 дней</div><div class="v">{{ fmtMln(kpi.sum_30d) }}</div></div>
        <div class="kpi"><div class="l">Средний чек 30 дн</div><div class="v">{{ fmtMoney(kpi.avg_30) }}</div></div>
        <div class="kpi"><div class="l">Заказов всего</div><div class="v">{{ fmtNum(fresh.total_orders) }}</div><div class="d">с 2019</div></div>
      </div>
      <div class="card">
        <h3>Сравнение периодов</h3>
        <div class="controls" style="margin-bottom:10px">
          <div class="seg">
            <button :class="{active: cmpKind==='month'}" @click="cmpKind='month'; loadCompare()">Месяц</button>
            <button :class="{active: cmpKind==='quarter'}" @click="cmpKind='quarter'; loadCompare()">Квартал</button>
            <button :class="{active: cmpKind==='year'}" @click="cmpKind='year'; loadCompare()">Год</button>
          </div>
          <input type="text" :placeholder="cmpKind==='year' ? '2026' : (cmpKind==='quarter' ? '2026-Q3' : '2026-09')" v-model="cmpAnchor" @keyup.enter="loadCompare" style="width:130px">
          <button class="ghost" @click="loadCompare" :disabled="cmpLoading">{{ cmpLoading ? "…" : "Сравнить" }}</button>
        </div>
        <div v-if="cmpError" class="error">{{ cmpError }}</div>
        <div v-else-if="cmp" class="kpis" style="margin-bottom:0">
          <div class="kpi" v-for="(c, i) in cmp" :key="c.label">
            <div class="l">{{ c.label }}</div>
            <div class="v">{{ fmtNum(c.orders) }} <span class="d">заказов</span></div>
            <div class="d">{{ fmtMln(c.revenue) }} · средний {{ fmtMoney(c.avg_check) }}</div>
            <div class="d" v-if="i + 1 < cmp.length">
              <span :style="{color: (c.d_orders >= 0 ? 'var(--green)' : 'var(--red)')}">
                {{ c.d_orders >= 0 ? "▲" : "▼" }} {{ Math.abs(c.d_orders) }} ({{ c.p_orders }}%)
              </span>
              ·
              <span :style="{color: (c.d_revenue >= 0 ? 'var(--green)' : 'var(--red)')}">
                {{ c.d_revenue >= 0 ? "▲" : "▼" }} {{ fmtMln(Math.abs(c.d_revenue)) }}
              </span>
              против {{ cmp[i+1].label }}
            </div>
            <div class="d">отмен: {{ c.canceled }} ({{ c.orders ? Math.round(100*c.canceled/c.orders) : 0 }}%)</div>
          </div>
        </div>
        <div v-else class="loading">…</div>
      </div>
      <div class="card"><h3>Заказы по месяцам</h3><div class="chart-box"><canvas id="c-months"></canvas></div></div>
      <div class="grid2">
        <div class="card"><h3>По годам</h3>
          <table class="data"><thead><tr><th>Год</th><th>Заказов</th><th>Сумма</th><th>Средний</th></tr></thead>
          <tbody><tr v-for="y in years" :key="y.year"><td>{{ y.year }}</td><td class="num">{{ fmtNum(y.cnt) }}</td><td class="num">{{ fmtMln(y.revenue) }}</td><td class="num">{{ fmtMoney(y.avg_check) }}</td></tr></tbody></table>
        </div>
        <div class="card"><h3>Статусы за 365 дней</h3><div class="chart-box"><canvas id="c-status"></canvas></div></div>
      </div>
      <div class="grid2">
        <div class="card"><h3>Топ-10 контрагентов</h3>
          <table class="data"><thead><tr><th>Контрагент</th><th>Заказов</th><th>Сумма</th></tr></thead>
          <tbody><tr v-for="c in contractors" :key="c.name"><td>{{ c.name }}</td><td class="num">{{ fmtNum(c.orders) }}</td><td class="num">{{ fmtMln(c.revenue) }}</td></tr></tbody></table>
        </div>
        <div class="card"><h3>Топ-10 позиций (25 мес)</h3><div class="chart-box lg"><canvas id="c-top"></canvas></div>
          <table class="data"><thead><tr><th>Позиция</th><th>Ед.</th><th>Выручка</th></tr></thead>
          <tbody><tr v-for="t in topItems" :key="t.name"><td>{{ t.name.slice(0,60) }}</td><td class="num">{{ fmtNum(t.units) }}</td><td class="num">{{ fmtMln(t.revenue) }}</td></tr></tbody></table>
        </div>
      </div>
    </div>
  </div>`
};
