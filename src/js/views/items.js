// Вкладка «Товары»: поиск по каталогу 231k + детали цен по филиалам.
import { api, fmtMoney } from "../common.js";

export default {
  data: () => ({ loading: false, error: "", q: "", results: [], sel: null, prices: [] }),
  methods: { api, fmtMoney,
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
  template: `
  <div>
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
      <div class="card" v-if="sel">
        <h3>{{ sel.full_name && sel.full_name.slice(0, 80) }}</h3>
        <table class="data">
          <thead><tr><th>Филиал</th><th>Цена</th><th>Со скидкой</th><th>Версия</th></tr></thead>
          <tbody>
            <tr v-for="p in prices" :key="p.branch_id_1c">
              <td>{{ p.branch }}</td><td class="num">{{ fmtMoney(p.price, 2) }}</td><td class="num">{{ fmtMoney(p.discount_price, 2) }}</td><td>{{ (p.version_date||"").slice(0,10) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>`
};
