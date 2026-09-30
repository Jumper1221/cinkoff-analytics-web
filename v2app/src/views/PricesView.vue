<script setup lang="ts">
import { computed, ref, watch, type Ref } from 'vue'
import { useApi, fmtMoney, fmtDate, fmtInt } from '../api/client'
import { useChart, chartColors } from '../api/useChart'
import type { PricePoint } from '../api/types'

// --- Каталог: точка отгрузки → дерево (вид → группа) → товары с текущими ценами ---

interface Branch { id_1c: string; name: string; n_items: number }
interface TreeGroup { kind: string; group_name: string; n_items: number; n_priced: number }
interface Family { family: string; n_items: number; n_priced: number; groups: TreeGroup[] }
interface TreeKind { kind: string; n_items: number; n_families: number; families: Family[] }
interface SurfItem { surface: string; n: number }
interface CatalogItem {
  id_1c: string; code_1c: string; full_name: string; group_name: string
  color?: string; thickness?: string; surface?: string
  price: number; discount_pct: number; discount_price: number; version_date: string
}

const TREE_KEY = 'catalog.branch'

// Точка отгрузки (запоминаем выбор)
const savedBranch = (() => { try { return localStorage.getItem(TREE_KEY) || '' } catch { return '' } })()
const branches = useApi<Branch[]>(() => '/api/catalog/branches')
const branchId = ref(savedBranch)
watch(branches.data, (b) => {
  if (!branchId.value && b?.length) {
    const obn = b.find(x => /обнинск/i.test(x.name))
    branchId.value = (obn ?? b[0]).id_1c
  }
})
watch(branchId, (v) => { if (v) { try { localStorage.setItem(TREE_KEY, v) } catch {} } })

// Дерево каталога
const tree = useApi<{ kinds: TreeKind[] }>(() => '/api/catalog/tree')

// Выбор в дереве: вид (открыт/закрыт) → семейство (открыто/закрыто) → группа ИЛИ всё семейство
const kindOpen = ref('')
const famOpen = ref('')
const selGroup = ref<{ kind: string; family: string; group: string } | null>(null)
const selFamilyOnly = ref(false)
const selSurf = ref('')   // покрытие внутри выбранной группы (4-й уровень)
const search = ref('')
const offset = ref(0)
let searchTm: number | undefined

const hasSearch = computed(() => search.value.trim().length >= 2)
const listQ = computed(() => {
  if (!branchId.value) return ''
  if ((!selGroup.value && !selFamilyOnly.value) && !hasSearch.value) return ''
  const p = new URLSearchParams({ branch: branchId.value, limit: '50', offset: String(offset.value) })
  if (selGroup.value && !selFamilyOnly.value) {
    p.set('group', selGroup.value.group); p.set('kind', selGroup.value.kind)
  } else if (selGroup.value) {
    // всё семейство: фильтр по префиксу имён групп (kind = семейство, group пуст)
    p.set('kind', selGroup.value.family)
  }
  if (selSurf.value && selGroup.value?.group) p.set('surface', selSurf.value)
  if (hasSearch.value) p.set('search', search.value.trim())
  return `/api/catalog/items?${p.toString()}`
})

const items = useApi<{ total: number; items: CatalogItem[] }>(() => listQ.value, false)
watch(listQ, () => items.load())
watch(search, () => {
  window.clearTimeout(searchTm)
  searchTm = window.setTimeout(() => { offset.value = 0; if (listQ.value) items.load() }, 400)
})
watch(selGroup, (nv, ov) => { offset.value = 0; if (nv?.group !== ov?.group) selSurf.value = '' })

// --- 4-й уровень: покрытия группы (лениво, при первом раскрытии) ---
const surfOpen = ref('')            // имя раскрытой группы
const surfCache = ref<Record<string, SurfItem[]>>({})
const surfLoading = ref(false)
async function toggleSurf(g: string) {
  if (surfOpen.value === g) { surfOpen.value = ''; return }
  surfOpen.value = g
  if (!surfCache.value[g]) {
    surfLoading.value = true
    try {
      const p = new URLSearchParams({ branch: branchId.value || '', group: g })
      const r = await fetch(`/api/catalog/surfaces?${p.toString()}`)
      const d = await r.json() as { surfaces: SurfItem[] }
      surfCache.value = { ...surfCache.value, [g]: d.surfaces ?? [] }
    } finally { surfLoading.value = false }
  }
}
function pickSurf(k: string, f: string, g: string, s: string) {
  if (selSurf.value === s && selGroup.value?.group === g && selGroup.value?.kind === k) {
    selSurf.value = ''
  } else {
    selGroup.value = { kind: k, family: f, group: g }
    selFamilyOnly.value = false
    selSurf.value = s
  }
}

function toggleKind(k: string) {
  kindOpen.value = kindOpen.value === k ? '' : k
  famOpen.value = ''
  if (kindOpen.value) { selGroup.value = null; selFamilyOnly.value = false }
}
function toggleFamily(k: string, f: string) {
  if (famOpen.value === f && kindOpen.value === k) { famOpen.value = '' }
  else { kindOpen.value = k; famOpen.value = f }
  selGroup.value = null; selFamilyOnly.value = false
}
function pickFamily(k: string, f: string) {
  if (selGroup.value?.family === f && selGroup.value?.kind === k && selFamilyOnly.value) {
    selGroup.value = null; selFamilyOnly.value = false
  } else {
    selGroup.value = { kind: k, family: f, group: '' }
    selFamilyOnly.value = true
  }
}
function pickGroup(k: string, f: string, g: string) {
  if (selGroup.value?.group === g && selGroup.value?.kind === k) { selGroup.value = null; selFamilyOnly.value = false }
  else { selGroup.value = { kind: k, family: f, group: g }; selFamilyOnly.value = false }
}

const branchName = computed(() => branches.data.value?.find(b => b.id_1c === branchId.value)?.name ?? '')

// Карточка товара
const sel = ref<CatalogItem | null>(null)
const prices = useApi<PricePoint[]>(() => (sel.value ? `/api/catalog/prices/${sel.value.id_1c}` : ''), false)
const hist = useApi<PricePoint[]>(() => (sel.value ? `/api/catalog/price_history/${sel.value.id_1c}?branch=${encodeURIComponent(branchId.value)}` : ''), false)
watch(sel, () => { if (sel.value) { prices.load(); hist.load() } })

const priceDep = computed(() => prices.data.value)
const { canvas: cAll } = useChart(() => {
  const d = prices.data.value
  if (!d?.length) return null
  const C = chartColors()
  const rows = [...d].sort((a, b) => a.discount_price - b.discount_price)
  return {
    type: 'bar',
    data: {
      labels: rows.map(r => r.branch),
      datasets: [
        { label: 'Цена прайса', data: rows.map(r => r.price), backgroundColor: C.muted + '66', borderRadius: 3, yAxisID: 'y' },
        { type: 'line', label: 'Со скидкой', data: rows.map(r => r.discount_price), borderColor: C.accent, tension: 0.25, pointRadius: 3, yAxisID: 'y' },
      ],
    },
    options: {
      indexAxis: 'y', maintainAspectRatio: false,
      scales: { x: { ticks: { color: C.muted }, grid: { color: C.border } }, y: { ticks: { color: C.text, font: { size: 10 } }, grid: { display: false } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 10 } } },
    },
  } as any
}, priceDep as Ref<unknown>)

const histDep = computed(() => hist.data.value)
const { canvas: cHist } = useChart(() => {
  const d = hist.data.value
  if (!d?.length) return null
  const C = chartColors()
  const rows = [...d].sort((a, b) => (a.version_date ?? '').localeCompare(b.version_date ?? ''))
  return {
    type: 'line',
    data: {
      labels: rows.map(r => (r.version_date ?? '').slice(0, 10)),
      datasets: [
        { label: 'Со скидкой', data: rows.map(r => r.discount_price), borderColor: C.accent, tension: 0.25, pointRadius: 2 },
        { label: 'Прайс', data: rows.map(r => r.price), borderColor: C.muted, tension: 0.25, pointRadius: 0, borderDash: [4, 3] },
      ],
    },
    options: {
      maintainAspectRatio: false,
      scales: { x: { ticks: { color: C.muted, font: { size: 9 }, maxRotation: 0, autoSkip: true }, grid: { color: C.border } }, y: { ticks: { color: C.muted }, grid: { color: C.border } } },
      plugins: { legend: { labels: { color: C.text, boxWidth: 10 } } },
    },
  } as any
}, histDep as Ref<unknown>)
</script>

<template>
  <h1>Каталог товаров</h1>

  <div class="panel">
    <div class="cat-bar">
      <label class="cat-branch">
        <span class="muted">Точка отгрузки:</span>
        <select v-model="branchId" class="cat-select">
          <option v-for="b in (branches.data.value ?? [])" :key="b.id_1c" :value="b.id_1c">
            {{ b.name }} ({{ fmtInt(b.n_items) }})
          </option>
        </select>
      </label>
      <input v-model="search" class="f-search cat-search" :style="{ flexGrow: 1 }" placeholder="поиск по каталогу (от 2 букв)…" />
    </div>
    <div v-if="branches.error.value" class="err-text">{{ branches.error.value }}</div>
  </div>

  <div v-if="branchId" class="cat-grid2">
    <div class="panel cat-tree">
      <h3>Каталог</h3>
      <div v-if="tree.loading.value" class="muted">Дерево…</div>
      <div v-else-if="tree.error.value" class="err-text">{{ tree.error.value }}</div>
      <template v-else>
        <div v-for="k in (tree.data.value?.kinds ?? [])" :key="k.kind" class="cat-kind-block">
          <div class="tree-kind click" @click="toggleKind(k.kind)">
            <span class="tri">{{ kindOpen === k.kind ? '▾' : '▸' }}</span>{{ k.kind }}
            <span class="muted small">— {{ fmtInt(k.n_items) }}</span>
          </div>
          <div v-if="kindOpen === k.kind" class="kind-groups">
            <div v-for="f in k.families" :key="f.family" class="fam-block">
              <div class="tree-fam-row">
                <span class="tree-family click" :class="{ on: selFamilyOnly && selGroup?.family === f.family && selGroup?.kind === k.kind }"
                      @click="pickFamily(k.kind, f.family)">
                  {{ f.family }}
                </span>
                <span class="tree-fam-tri click" @click="toggleFamily(k.kind, f.family)">{{ (famOpen === f.family && kindOpen === k.kind) ? '▾' : '▸' }}</span>
                <span class="muted small">{{ fmtInt(f.n_priced) }}</span>
              </div>
              <div v-if="famOpen === f.family && kindOpen === k.kind" class="kind-groups">
                <div v-for="g in f.groups" :key="g.group_name" class="tree-group-wrap">
                  <div class="tree-group click"
                     :class="{ on: selGroup?.group === g.group_name && selGroup?.kind === k.kind && !selFamilyOnly }"
                     @click="pickGroup(k.kind, f.family, g.group_name)">
                    <span class="tri2 click" @click.stop="toggleSurf(g.group_name)">{{ surfOpen === g.group_name ? '▾' : '▸' }}</span>
                    <span class="tg-name">{{ g.group_name }}</span>
                    <span class="muted small">{{ fmtInt(g.n_priced) }}</span>
                  </div>
                  <div v-if="surfOpen === g.group_name" class="surf-list">
                    <div v-if="surfLoading && !surfCache[g.group_name]" class="muted small" style="padding: 2px 0 2px 40px">Покрытия…</div>
                    <div v-else-if="!(surfCache[g.group_name]?.length)" class="muted small" style="padding: 2px 0 2px 46px">—</div>
                    <div v-else v-for="s in (surfCache[g.group_name] ?? [])" :key="s.surface"
                         class="tree-surf click"
                         :class="{ on: selSurf === s.surface && selGroup?.group === g.group_name }"
                         @click="pickSurf(k.kind, f.family, g.group_name, s.surface)">
                      <span class="tg-name">{{ s.surface }}</span>
                      <span class="muted small">{{ fmtInt(s.n) }}</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <div class="panel cat-list">
      <h3>
        Товары <span class="muted">@ {{ branchName }}</span>
        <span v-if="selGroup && selGroup.group" class="muted"> — {{ selGroup.group }}<template v-if="selSurf"> · {{ selSurf }}</template></span>
        <span v-else-if="selGroup && !selGroup.group" class="muted"> — семейство «{{ selGroup.family }}»</span>
        <span v-else-if="hasSearch" class="muted">— поиск «{{ search.trim() }}»</span>
        <span v-if="items.data.value" class="muted small"> — {{ fmtInt(items.data.value.total) }}</span>
      </h3>
      <div v-if="items.loading.value" class="muted">Товары…</div>
      <div v-else-if="items.error.value" class="err-text">{{ items.error.value }}</div>
      <template v-else-if="items.data.value && items.data.value.items.length">
        <table>
          <thead><tr><th>Товар</th><th>Покрытие</th><th>Прайс</th><th>Скидка %</th><th>Со скидкой</th><th>Версия</th></tr></thead>
          <tbody>
            <tr v-for="it in items.data.value.items" :key="it.id_1c" class="click" @click="sel = it">
              <td class="cell-name">
                {{ it.full_name }}
                <div v-if="it.color || it.thickness" class="muted small">{{ [it.color, it.thickness].filter(Boolean).join(', ') }}</div>
              </td>
              <td class="muted">{{ it.surface || '—' }}</td>
              <td class="num">{{ fmtMoney(it.price) }}</td>
              <td class="num">{{ it.discount_pct ? it.discount_pct.toFixed(1) + '%' : '—' }}</td>
              <td class="num"><b>{{ fmtMoney(it.discount_price) }}</b></td>
              <td class="muted">{{ fmtDate(it.version_date) }}</td>
            </tr>
          </tbody>
        </table>
        <div class="pager">
          <button class="anchor" :disabled="offset === 0" @click="offset = Math.max(0, offset - 50)">← пред</button>
          <span class="muted">{{ offset + 1 }}–{{ Math.min(offset + 50, (items.data.value?.total ?? 0)) }} из {{ fmtInt(items.data.value?.total ?? 0) }}</span>
          <button class="anchor" :disabled="offset + 50 >= (items.data.value?.total ?? 0)" @click="offset += 50">след →</button>
        </div>
      </template>
      <div v-else-if="!items.loading.value" class="muted">
        {{ (selGroup || hasSearch) ? 'Ничего не найдено' : 'Выберите группу слева или ищите поиском' }}
      </div>
    </div>
  </div>
  <div v-else class="panel muted">Выберите точку отгрузки…</div>

  <div v-if="sel" class="panel">
    <h3>{{ sel.full_name }}</h3>
    <div class="muted small" style="margin-bottom:10px">
      Группа: {{ sel.group_name }} · версия-цены {{ fmtDate(sel.version_date) }}
    </div>
    <div v-if="prices.loading.value || hist.loading.value" class="muted">Цены по точкам…</div>
    <div v-else-if="prices.error.value || hist.error.value" class="err-text">{{ prices.error.value || hist.error.value }}</div>
    <template v-else>
      <div class="cat-grid2">
        <div class="chart-box tall"><canvas ref="cAll" /></div>
        <div class="chart-box tall"><canvas ref="cHist" /></div>
      </div>
      <table v-if="prices.data.value?.length" style="margin-top:10px">
        <thead><tr><th>Точка</th><th>Прайс</th><th>Скидка %</th><th>Со скидкой</th><th>Версия</th></tr></thead>
        <tbody>
          <tr v-for="p in prices.data.value" :key="p.branch + (p.version_date ?? '')">
            <td>{{ p.branch }}</td>
            <td class="num">{{ fmtMoney(p.price) }}</td>
            <td class="num">{{ p.discount_pct ? p.discount_pct.toFixed(1) + '%' : '—' }}</td>
            <td class="num"><b>{{ fmtMoney(p.discount_price) }}</b></td>
            <td class="muted">{{ fmtDate(p.version_date) }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
</template>

<style scoped>
.cat-bar { display: flex; gap: 14px; align-items: center; flex-wrap: wrap; }
.cat-branch { display: inline-flex; align-items: center; gap: 8px; }
.cat-branch select, .cat-search {
  background: var(--panel); color: var(--text); border: 1px solid var(--line);
  border-radius: 8px; padding: 6px 10px; font-size: 14px;
}
.cat-search { flex-grow: 1; min-width: 220px; }
.cat-tree { max-height: 62vh; overflow: auto; }
.tree-kind { padding: 6px 8px; font-weight: 600; border-radius: 6px; }
.tree-kind:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.tri { display: inline-block; width: 14px; color: var(--muted); }
.fam-block { margin: 2px 0; }
.tree-fam-row { display: flex; align-items: baseline; gap: 6px; padding: 3px 8px 3px 16px; border-radius: 6px; }
.tree-family { flex-grow: 1; }
.tree-family:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.tree-family.on { color: var(--accent); font-weight: 700; }
.tree-fam-tri { width: 14px; color: var(--muted); cursor: pointer; }
.kind-groups { margin: 2px 0 8px 16px; }
.tree-group-wrap { margin: 0; }
.tri2 { display: inline-block; width: 12px; color: var(--muted); font-size: 11px; }
.surf-list { margin: 1px 0 4px 30px; }
.tree-surf { display: flex; justify-content: space-between; gap: 8px; padding: 3px 8px 3px 14px; border-radius: 6px; font-size: 13px; }
.tree-surf:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.tree-surf.on { background: color-mix(in srgb, var(--accent) 20%, transparent); font-weight: 600; }
.tree-group { display: flex; justify-content: space-between; gap: 8px; padding: 4px 8px 4px 34px; border-radius: 6px; }
.tree-group:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.tree-group.on { background: color-mix(in srgb, var(--accent) 16%, transparent); font-weight: 600; }
.cat-list { min-width: 0; }
.cell-name { max-width: 460px; }
.num { text-align: right; white-space: nowrap; }
.pager { display: flex; align-items: center; gap: 14px; margin-top: 10px; }
.pager .muted { margin: 0 auto; }
.cat-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
@media (max-width: 900px) { .cat-grid2 { grid-template-columns: 1fr; } .cat-list { order: 2; } }
</style>
