<script setup lang="ts">
import { computed } from 'vue'
import { useApi, fmtInt } from '../api/client'
import type { ForecastRow2, PairRow2 } from '../api/types2'

const fc = useApi<any>(() => '/api/forecast/remnants?days=90&top=200')
const pairs = useApi<any>(() => '/api/basket/pairs?days=90&top=10')

const FLAG: Record<string, { icon: string; cls: string; text: string }> = {
  crit: { icon: '🔥', cls: 'down', text: 'закончился' },
  warn: { icon: '⚠', cls: '', text: 'мало' },
  ok: { icon: '✓', cls: 'up', text: 'хватает' },
}
const cnt = computed(() => {
  const rows = (fc.data.value?.rows ?? []) as ForecastRow2[]
  return {
    crit: rows.filter(r => r.flag === 'crit').length,
    warn: rows.filter(r => r.flag === 'warn').length,
    ok: rows.filter(r => r.flag === 'ok').length,
    total: rows.length,
  }
})
const rows = computed(() => (fc.data.value?.rows ?? []) as ForecastRow2[])
const prs = computed(() => (pairs.data.value?.pairs ?? []) as PairRow2[])
</script>

<template>
  <h1>Прогноз</h1>
  <div class="panel">
    <h3>На сколько хватит остатков (темп расхода за 90 дней)</h3>
    <div v-if="fc.loading.value"><div v-for="r in 12" :key="r" class="skel skel-row" /></div>
    <div v-else-if="fc.error.value" class="err-text">{{ fc.error.value }}</div>
    <template v-else>
      <p class="flags">
        <span class="badge down">🔥 {{ cnt.crit }}</span>
        <span class="badge">⚠ {{ cnt.warn }}</span>
        <span class="badge up">✓ {{ cnt.ok }}</span>
        <span class="muted">из {{ cnt.total }} позиций с расходом</span>
      </p>
      <table>
        <thead><tr><th></th><th>Товар</th><th class="num">Остаток</th><th class="num">Расход, 90д</th><th class="num">В день</th><th class="num">Хватит, дн</th></tr></thead>
        <tbody>
          <tr v-for="r in rows" :key="r.id_1c">
            <td>{{ FLAG[r.flag]?.icon ?? '' }}</td>
            <td class="ellipsis" :title="r.name">{{ r.name }}</td>
            <td class="num">{{ fmtInt(r.stock) }}</td>
            <td class="num">{{ fmtInt(r.spent) }}</td>
            <td class="num">{{ r.rate_day.toFixed(1) }}</td>
            <td class="num">{{ r.days_left > 999 ? '∞' : fmtInt(r.days_left) }}</td>
          </tr>
        </tbody>
      </table>
    </template>
  </div>
  <div class="panel">
    <h3>Топ-пары (покупают вместе, 90 дней)</h3>
    <div v-if="pairs.loading.value" class="muted">Считаю…</div>
    <table v-else>
      <thead><tr><th>Товар A</th><th>Товар B</th><th class="num">Заказов</th></tr></thead>
      <tbody>
        <tr v-for="(p, ix) in prs" :key="ix">
          <td class="ellipsis" :title="p.a_name">{{ p.a_name }}</td>
          <td class="ellipsis" :title="p.b_name">{{ p.b_name }}</td>
          <td class="num">{{ p.cnt }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
