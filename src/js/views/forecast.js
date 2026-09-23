// Вкладка «Прогноз»: темп расхода vs остаток → «хватит на N дней».
import { api, fmtNum, fmtDate, chartColors } from "../common.js";

export default {
  data: () => ({ loading: true, error: "", rows: [], days: 90, flagFilter: "all", pairs: [] }),
  watch: { days() { this.load(); } },
  mounted() { this.load(); },
  computed: {
    flagCounts() {
      const c = { crit: 0, warn: 0, ok: 0 };
      this.rows.forEach(r => c[r.flag]++);
      return c;
    },
  },
  methods: { api, fmtNum,
    async load() {
      this.loading = true;
      try {
        this.rows = (await this.api("/api/forecast/remnants", { days: this.days, top: 120 })).rows;
        this.pairs = (await this.api("/api/basket/pairs", { days: this.days, top: 10 })).pairs;
      }
      catch (e) { this.error = String(e); }
      this.loading = false;
    },
    flagLabel(f) { return { crit: "🔥 меньше 2 нед", warn: "⚠ меньше 1.5 мес", ok: "✓ ок" }[f] || f; },
    flagColor(f) { return { crit: "var(--red, #dc2626)", warn: "var(--orange, #f59e0b)", ok: "var(--green, #16a34a)" }[f]; },
  },
  template: `
  <div>
    <h1 class="page-title">Прогноз остатков</h1>
    <p class="page-sub">Темп расхода по заказам за период → сколько дней хватит</p>
    <div class="controls" style="margin-bottom:14px">
      <div class="seg">
        <button :class="{active: days===30}" @click="days=30">30 дн</button>
        <button :class="{active: days===90}" @click="days=90">90 дн</button>
        <button :class="{active: days===180}" @click="days=180">180 дн</button>
      </div>
      <div class="seg">
        <button :class="{active: flagFilter==='all'}" @click="flagFilter='all'">Все ({{ rows.length }})</button>
        <button :class="{active: flagFilter==='crit'}" @click="flagFilter='crit'">🔥 {{ flagCounts.crit }}</button>
        <button :class="{active: flagFilter==='warn'}" @click="flagFilter='warn'">⚠ {{ flagCounts.warn }}</button>
        <button :class="{active: flagFilter==='ok'}" @click="flagFilter='ok'">✓ {{ flagCounts.ok }}</button>
      </div>
    </div>
    <div v-if="loading" class="loading">Считаем…</div>
    <div class="card" v-else>
      <table class="data">
        <thead><tr><th>Товар</th><th class="num">Расход</th><th class="num">шт/день</th><th class="num">Остаток</th><th class="num">Хватит, дн</th><th>Статус</th></tr></thead>
        <tbody>
          <tr v-for="r in (flagFilter==='all' ? rows : rows.filter(x => x.flag===flagFilter))" :key="r.id_1c">
            <td>{{ (r.name || "—").slice(0, 55) }}</td>
            <td class="num">{{ fmtNum(r.spent) }}</td>
            <td class="num">{{ r.rate_day }}</td>
            <td class="num">{{ fmtNum(r.stock) }}</td>
            <td class="num"><b>{{ r.days_left === null ? "—" : r.days_left }}</b></td>
            <td><span class="badge" :style="{color: flagColor(r.flag)}">{{ flagLabel(r.flag) }}</span></td>
          </tr>
        </tbody>
      </table>
    </div>
    <div class="card" v-if="pairs.length" style="margin-top:14px">
      <h3>Топ-пары заказов <span class="muted" style="font-weight:400; font-size:12px">за {{ days }} дн</span></h3>
      <table class="data"><tbody>
        <tr v-for="(p, i) in pairs" :key="i">
          <td style="width:45%">{{ (p.a_name || "—").slice(0, 40) }}</td>
          <td class="muted" style="width:8px; white-space:nowrap">+</td>
          <td>{{ (p.b_name || "—").slice(0, 40) }}</td>
          <td class="num"><b>{{ p.cnt }}</b> раз</td>
        </tr>
      </tbody></table>
    </div>
  </div>`
};
