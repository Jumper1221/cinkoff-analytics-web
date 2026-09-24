<script setup lang="ts">
import { useApi, fmtMoney } from '../api/client'

const { data, loading, error } = useApi<any>(() => '/api/years')
</script>

<template>
  <h1>Годы</h1>
  <div class="panel">
    <div v-if="loading" class="muted">Загрузка…</div>
    <div v-else-if="error" class="err-text">{{ error }}</div>
    <pre v-else>{{ JSON.stringify(data, null, 2) }}</pre>
  </div>
</template>
