<script setup lang="ts">
import { computed } from 'vue'
import { useApi, fmtInt, fmtMoney } from '../api/client'

const { data, loading, error } = useApi<any>(() => '/api/kpi')
const kpis = computed(() => [
  { l: 'Заказов сегодня', v: fmtInt(data.value?.orders_today) },
  { l: 'Заказов, 30 дней', v: fmtInt(data.value?.orders_30d) },
  { l: 'Выручка, 30 дней', v: fmtMoney(data.value?.sum_30d) },
  { l: 'Ср. чек, 30 дней', v: fmtMoney(data.value?.avg_30) },
])
</script>

<template>
  <h1>Дашборд</h1>
  <div v-if="loading" class="muted">Загрузка…</div>
  <div v-else-if="error" class="panel err-text">{{ error }}</div>
  <div v-else class="kpis">
    <div v-for="k in kpis" :key="k.l" class="panel kpi">
      <div class="v">{{ k.v }}</div>
      <div class="l">{{ k.l }}</div>
    </div>
  </div>
</template>
