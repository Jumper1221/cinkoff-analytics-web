// Вкладка «Годы»: тепловая карта месяц×год (заказы / выручка / средний).
import { api, fmtMln, fmtNum, fmtMoney } from "../common.js";

export default {
  data: () => ({ metric: "orders", years: [], matrix: {}, maxV: 0, loading: true }),
  computed: {
    monthNames: () => ["Янв", "Фев", "Мар", "Апр", "Май", "Июн", "Июл", "Авг", "Сен", "Окт", "Ноя", "Дек"],
  },
  watch: { metric() { this.load(); } },
  mounted() { this.load(); },
  methods: { api, fmtMln, fmtNum, fmtMoney,
    async load() {
      this.loading = true;
      try {
        const j = await this.api("/api/heatmap", { metric: this.metric });
        this.years = j.years; this.matrix = j.matrix;
        this.maxV = Math.max(...j.years.flatMap(y => j.matrix[y]));
      } catch (e) { this.error = String(e); }
      this.loading = false;
    },
    cell(y, m) {
      const v = (this.matrix[y] || [])[m] || 0;
      const a = this.maxV ? 0.08 + 0.85 * (v / this.maxV) : 0;
      return { background: `rgba(37, 99, 235, ${a.toFixed(2)})` };
    },
    fmt(v) {
      if (this.metric === "revenue") return this.fmtMln(v);
      if (this.metric === "avg") return this.fmtMoney(v);
      return this.fmtNum(v);
    },
  },
  template: `
  <div>
    <h1 class="page-title">Годы × Месяцы</h1>
    <p class="page-sub">Тепловая карта: чем темнее, тем больше. 2019→2026</p>
    <div class="controls" style="margin-bottom:14px">
      <div class="seg">
        <button :class="{active: metric==='orders'}" @click="metric='orders'">Заказов</button>
        <button :class="{active: metric==='revenue'}" @click="metric='revenue'">Выручка</button>
        <button :class="{active: metric==='avg'}" @click="metric='avg'">Средний чек</button>
      </div>
    </div>
    <div class="card" style="overflow-x:auto">
      <table class="data" style="min-width:840px">
        <thead><tr><th>Год</th><th v-for="m in 12" :key="m" class="num">{{ monthNames[m-1] }}</th><th class="num">Σ</th></tr></thead>
        <tbody>
          <tr v-for="y in years" :key="y">
            <td><b>{{ y }}</b></td>
            <td v-for="m in 12" :key="m" class="num" :style="cell(y, m-1)" style="color:#fff; min-width:54px; padding:10px 6px; text-align:center">
              {{ fmt((matrix[y] || [])[m-1] || 0) }}
            </td>
            <td class="num"><b>{{ fmt((matrix[y] || []).reduce((a, b) => a + b, 0)) }}</b></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>`
};
