// Вкладка «Товары»: поиск по каталогу 231k + детали цен по филиалам.
import { api, fmtMoney, fmtMln, fmtNum } from "../common.js";

export default {
  data: () => ({ loading: false, error: "", q: "", results: [], sel: null, prices: [],
  abcRows: [], abcFilter: "all" }),
  methods: { api, fmtMoney, fmtMln, fmtNum,
  async loadAbc() {
    this.abcRows = await this.api("/api/abc", { days: 365 });
  },
  abcFiltered() {
    return this.abcFilter === "all" ? this.abcRows : this.abcRows.filter(r => r.abc === this.abcFilter);
  },
   async search() {
      if (this.q.length < 2) { this.results = []; return; }
      this.loading = true; this.error = "";
      try { this.results = await api("/api/catalog/search", { s: this.q, limit: 30 }); }
      catch (e) { this.error = String(e); }
      this.loading = false;
    },
    async open(n) {
      this.sel = n;
      this.prices = await api(`/api/catalog/prices/${n.id_1c}`);
    },
  },
  created() {
    this.debSearch = (() => { let t; return () => { clearTimeout(t); t = setTimeout(this.search, 350); }; })();
  },
  mounted() { this.loadAbc && this.loadAbc(); },
  template: `
  <div>
    <div class="card" style="margin-bottom:14px">
      <h3>ABC-анализ (365 дн, по выручке)</h3>
      <div class="controls">
        <div class="seg">
          <button :class="{active: abcFilter==='all'}" @click="abcFilter='all'">Все</button>
          <button :class="{active: abcFilter==='A'}" @click="abcFilter='A'">A</button>
          <button :class="{active: abcFilter==='B'}" @click="abcFilter='B'">B</button>
          <button :class="{active: abcFilter==='C'}" @click="abcFilter='C'">C</button>
        </div>
        <span class="muted">A = 80% кумулятивной выручки, B = до 95%, C = хвост</span>
      </div>
      <table class="data">
        <thead><tr><th>Кл.</th><th>Товар</th><th class="num">Выручка</th><th class="num">Ед.</th><th class="num">Доля</th><th class="num">Кум.</th></tr></thead>
        <tbody>
          <tr v-for="r in (abcFilter==='all' ? abcRows : abcRows.filter(x => x.abc===abcFilter)).slice(0,50)" :key="r.name">
            <td><span class="badge" :style="{color: r.abc==='A' ? 'var(--green)' : (r.abc==='B' ? 'var(--orange)' : 'var(--muted)')}">{{ r.abc }}</span></td>
            <td>{{ (r.name || "—").slice(0, 60) }}</td>
            <td class="num">{{ fmtMln(r.revenue) }}</td>
            <td class="num">{{ fmtNum(r.units) }}</td>
            <td class="num">{{ r.share_pct }}%</td>
            <td class="num">{{ r.cum_share_pct }}%</td>
          </tr>
        </tbody>
      </table>
    </div>
    <h1 class="page-title">Товары</h1>
    <p class="page-sub">Каталог 231 090 позиций · цены по 33 филиалам</p>
    <div class="controls">
      <input type="search" v-model="q" @input="debSearch && debSearch()" placeholder="Название, цвет, толщина…" style="min-width:320px">
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <div class="grid2">
      <div class="card">
        <h3>Результаты</h3>
        <table class="data">
          <thead><tr><th>Название</th><th>Цвет</th><th>Толщ.</th></tr></thead>
          <tbody>
            <tr v-for="r in results" :key="r.id_1c" @click="sel=r" :style="{cursor:'pointer'}">
              <td>{{ r.full_name && r.full_name.slice(0, 70) }}</td><td>{{ r.color }}</td><td>{{ r.thickness }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="card" v-if="sel && !card"><div class="loading">Загрузка карточки…</div></div>
      <div v-if="card">
        <div class="kpis" style="margin-bottom:14px">
          <div class="kpi"><div class="l">Куплено всего</div><div class="v">{{ fmtNum(card.sold_all.units) }}</div><div class="d">ед · {{ fmtMln(card.sold_all.revenue) }} · {{ card.sold_all.orders_cnt }} заказов</div></div>
          <div class="kpi"><div class="l">За 12 мес</div><div class="v">{{ fmtNum(card.sold12.units) }}</div><div class="d">ед · {{ fmtMln(card.sold12.revenue) }}</div></div>
          <div class="kpi"><div class="l">Последний заказ</div><div class="v" style="font-size:17px">{{ card.sold_all.last_order ? fmtDate(card.sold_all.last_order) : "—" }}</div></div>
          <div class="kpi"><div class="l">Характеристики</div><div class="d">{{ card.info.color || "—" }} · {{ card.info.thickness || "—" }} · {{ card.info.surface || "—" }} · {{ card.info.weight || "—" }} кг</div></div>
        </div>
        <div class="grid2">
          <div class="card">
            <h3>Динамика цены</h3>
            <div class="chart-box" v-if="card.price_history.length"><canvas ref="cardPrice"></canvas></div>
            <div v-else class="loading">Нет данных о цене</div>
          </div>
          <div>
            <div class="card" style="margin-bottom:14px">
              <h3>Цены по филиалам</h3>
              <table class="data"><tbody>
                <tr v-for="p in prices.slice(0, 12)" :key="p.branch_id_1c">
                  <td>{{ p.branch }}</td><td class="num">{{ fmtMoney(p.price, 2) }}</td>
                  <td class="num"><b>{{ fmtMoney(p.discount_price, 2) }}</b></td>
                </tr>
              </tbody></table>
            </div>
            <div class="card" v-if="card.remnants.length" style="margin-bottom:14px">
              <h3>Остатки / приход</h3>
              <table class="data"><tbody>
                <tr v-for="(r, i) in card.remnants.slice(0, 8)" :key="i">
                  <td>{{ r.branch }}</td><td class="num">{{ r.qty }} шт</td>
                  <td class="muted" v-if="r.delivery_date">приход {{ r.delivery_date }}</td>
                </tr>
              </tbody></table>
            </div>
            <div class="card" v-if="card.together.length">
              <h3>Покупают вместе</h3>
              <table class="data"><tbody>
                <tr v-for="(t, i) in card.together" :key="i">
                  <td>{{ (t.name || "—").slice(0, 45) }}</td><td class="num">{{ t.cnt }} раз</td>
                </tr>
              </tbody></table>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>`
};
