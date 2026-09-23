// Cinkoff Analytics — SPA-каркас: сайдбар, вкладки, тема, роутинг по хэшу.
// ФИКС: все вьюхи импортируются ДО mount (иначе заглушка прилипает навсегда).

const VIEWS = {
  dashboard: { title: "Дашборд", ico: "📊" },
  orders:    { title: "Заказы",   ico: "📋" },
  items:     { title: "Товары",   ico: "📦" },
  remnants:  { title: "Остатки",  ico: "🏭" },
  prices:    { title: "Цены",     ico: "₽"  },
  heatmap:   { title: "Годы",     ico: "📅" },
};

const { createApp, ref, computed } = Vue;

async function boot() {
  const app = createApp({
    setup() {
      const route = ref(new URLSearchParams(location.hash.slice(1)).get("v") || "dashboard");
      const theme = ref(localStorage.getItem("theme") || "light");

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

      return { route, theme, nav, toggleTheme, VIEWS };
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
      <div class="side-foot">v0.2 · данные: Postgres</div>
    </aside>
    <main class="main">
      <component :is="route + '-view'"></component>
    </main>
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
