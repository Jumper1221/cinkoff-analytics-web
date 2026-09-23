// Утилиты: fetch с ин-дvisa, форматирование денег/дат, канвас-хелпер.
export const fmtMoney = (v, digits = 0) =>
  (v == null ? "—" : Number(v).toLocaleString("ru-RU", { maximumFractionDigits: digits, minimumFractionDigits: 0 })) + " ₽";
export const fmtNum = (v, digits = 0) =>
  (v == null ? "—" : Number(v).toLocaleString("ru-RU", { maximumFractionDigits: digits }));
export const fmtMln = (v) => (v == null ? "—" : (Number(v) / 1e6).toFixed(1) + " млн");
export const fmtDate = (d) => (d ? new Date(d).toLocaleDateString("ru-RU") : "—");
export const monthName = (m) => ["янв","фев","мар","апр","май","июн","июл","авг","сен","окт","ноя","дек"][m - 1] || "";

export async function api(path, params = {}) {
  const u = new URL(path, location.origin);
  for (const [k, v] of Object.entries(params)) if (v !== "" && v != null) u.searchParams.set(k, v);
  const r = await fetch(u, { headers: { "Accept": "application/json" } });
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export function chartColors() {
  const css = getComputedStyle(document.documentElement);
  const c = (n) => css.getPropertyValue(n).trim() || "#888";
  return { accent: c("--accent"), text: c("--text"), border: c("--border"), muted: c("--muted"),
           green: c("--green"), orange: c("--orange"), red: c("--red") };
}

export function makeChart(canvasId, cfg) {
  const el = document.getElementById(canvasId);
  if (!el) return null;
  return new Chart(el, cfg);  // Chart — глобал из chart.umd.js
}

export function destroyChart(chart) { if (chart) chart.destroy(); }
