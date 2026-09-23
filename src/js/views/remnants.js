// Вкладка «Остатки»: снапшоты (товар x склад) — топ-наличие.
import { api, fmtNum, fmtDate } from "../common.js";

export default {
  data: () => ({ loading: true, error: "", rows: [], kind: "metall", snaps: [], snap: "" }),
  watch: { kind() { this.load(); }, snap() { this.load(); } },
  mounted() { this.load(); this.loadSnaps(); },
  methods: { api, fmtNum,
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
