// Cinkoff Analytics — SPA-каркас: сайдбар, вкладки, тема, роутинг по хэшу.
// ФИКС: все вьюхи импортируются ДО mount (иначе заглушка прилипает навсегда).

const VIEWS = {
  dashboard: { title: "Дашборд", ico: "📊" },
  orders:    { title: "Заказы",   ico: "📋" },
  items:     { title: "Товары",   ico: "📦" },
  remnants:  { title: "Остатки",  ico: "🏭" },
  prices:    { title: "Цены",     ico: "₽"  },
  heatmap:   { title: "Годы",     ico: "📅" },
  forecast:  { title: "Прогноз",   ico: "⏳" },
  cohorts:   { title: "Точки",     ico: "🏬" },
};

const { createApp, ref, computed } = Vue;

async function boot() {
  const app = createApp({
    setup() {
      const route = ref(new URLSearchParams(location.hash.slice(1)).get("v") || "dashboard");
      const theme = ref(localStorage.getItem("theme") || "light");
      const showSearch = ref(false);
      const searchQ = ref("");
      const searchRes = ref({ orders: [], items: [] });
      const searchBusy = ref(false);
      let searchTimer = null;

      function doSearch() {
        clearTimeout(searchTimer);
        if (searchQ.value.length < 2) { searchRes.value = { orders: [], items: [] }; return; }
        searchTimer = setTimeout(async () => {
          searchBusy.value = true;
          try {
            searchRes.value = await fetch(`/api/search_all?q=${encodeURIComponent(searchQ.value)}`).then(r => r.json());
          } finally { searchBusy.value = false; }
        }, 250);
      }
      function openSearch() { showSearch.value = true; searchQ.value = ""; searchRes.value = { orders: [], items: [] }; }
      function closeSearch() { showSearch.value = false; }
      function goOrder(oid) { closeSearch(); location.hash = "v=orders"; setTimeout(() => window.dispatchEvent(new CustomEvent("open-order", { detail: oid })), 300); }

      window.addEventListener("keydown", (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); showSearch.value ? closeSearch() : openSearch(); }
        if (e.key === "Escape") closeSearch();
      });

      function nav(v) {
        if (!VIEWS[v]) return;
        location.hash = "v=" + v;
        route.value = v;
      }
      function toggleTheme() {
        theme.value = theme.value === "dark" ? "light" : "dark";
        if (theme.value === "dark") document.documentElement.dataset.theme = "dark";
        else document.documentElement.dataset.theme = "";
        localStorage.setItem("theme", theme.value);
      }
      window.addEventListener("hashchange", () => {
        const v = new URLSearchParams(location.hash.slice(1)).get("v") || "dashboard";
        if (VIEWS[v]) route.value = v;
      });

      return { route, theme, nav, toggleTheme, VIEWS,
              showSearch, searchQ, searchRes, searchBusy, doSearch, openSearch, closeSearch, goOrder };
    },
    template: `
  <div class="shell">
    <aside class="sidebar">
      <div class="brand">Cinkoff<span>аналитика заказов</span></div>
      <button v-for="(v, key) in VIEWS" :key="key" class="nav-item"
              :class="{active: route===key}" @click="nav(key)">
        <span class="ico">{{ v.ico }}</span><span class="lbl">{{ v.title }}</span>
      </button>
      <div class="spacer"></div>
      <button class="toggle-theme" @click="toggleTheme" :title="theme">
        {{ theme === "dark" ? "☀" : "☾" }}
      </button>
      <button class="ghost" style="width:100%; margin-bottom:8px; font-size:12.5px" @click="openSearch" title="Ctrl+K">
        🔍 Поиск <span class="d" style="opacity:.6">Ctrl+K</span>
      </button>
      <div class="side-foot">v0.3 · данные: Postgres</div>
    </aside>
    <main class="main">
      <component :is="route + '-view'"></component>
    </main>

    <div v-if="showSearch" class="modal-mask" @click.self="closeSearch" style="align-items:flex-start; background:rgba(0,0,0,.35)">
      <div class="modal" style="max-width:640px; margin-top:8vh; padding:14px">
        <input type="search" v-model="searchQ" @input="doSearch" placeholder="Заказы, контрагенты, товары…"
               style="width:100%; font-size:16px; padding:10px 14px" autofocus>
        <div v-if="searchBusy" class="loading" style="padding:14px">…</div>
        <div v-else-if="searchQ.length >= 2">
          <div v-if="searchRes.orders && searchRes.orders.length">
            <h3 style="margin:12px 0 4px; font-size:13px; color:var(--muted)">ЗАКАЗЫ</h3>
            <table class="data"><tbody>
              <tr v-for="o in searchRes.orders" :key="o.order_id" @click="goOrder(o.order_id)" style="cursor:pointer">
                <td>{{ o.number }}</td><td>{{ (o.contractor_name||"").slice(0,26) }}</td>
                <td><span class="badge">{{ o.order_status }}</span></td><td class="num">{{ Number(o.sum).toLocaleString("ru") }} ₽</td>
              </tr>
            </tbody></table>
          </div>
          <div v-if="searchRes.items && searchRes.items.length">
            <h3 style="margin:12px 0 4px; font-size:13px; color:var(--muted)">ТОВАРЫ</h3>
            <table class="data"><tbody>
              <tr v-for="it in searchRes.items" :key="it.id_1c" @click="closeSearch(); $nextTick(()=>location.hash='v=items')" style="cursor:pointer">
                <td>{{ (it.full_name||"").slice(0,70) }}</td>
                <td class="muted">{{ it.color || "" }} {{ it.thickness || "" }}</td>
              </tr>
            </tbody></table>
          </div>
          <div v-if="!(searchRes.orders||[]).length && !(searchRes.items||[]).length" class="loading" style="padding:20px">Ничего не найдено</div>
        </div>
      </div>
    </div>
  </div>`
  });

  // 1) импортируем и регистрируем ВСЕ вьюхи заранее
  for (const [name] of Object.entries(VIEWS)) {
    try {
      const mod = await import(`/static/js/views/${name}.js`);
      app.component(name + "-view", mod.default);
    } catch (e) {
      console.error("view import failed:", name, e);
      app.component(name + "-view", {
        template: `<div class="error">Не загрузилась вкладка ${name}: {{ $e || "" }}<pre>{{ JSON.stringify(window.__err_$ { name } || e, null, 2) }}</pre></div>`,
      });
    }
  }

  // 2) только теперь mount — все компоненты уже известны
  if ((localStorage.getItem("theme") || "light") === "dark") {
    document.documentElement.dataset.theme = "dark";
  }
  app.mount("#app");
}

boot().catch(e => {
  document.getElementById("app").innerHTML =
    '<div class="error" style="padding:30px">Фронт-ошибка: <pre>' + (e && e.stack || e) + '</pre></div>';
  console.error(e);
});
