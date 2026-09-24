<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { useSearchStore } from '../stores/search'

const s = useSearchStore()
const router = useRouter()
const inputEl = ref<HTMLInputElement | null>(null)

watch(() => s.open, async (o) => { if (o) { await nextTick(); inputEl.value?.focus() } })
watch(() => s.q, () => { clearTimeout((window as any).__ssT); (window as any).__ssT = setTimeout(() => s.run(), 300) })

function go(h: { kind: string; id: number | string }) {
  s.close()
  if (h.kind === 'order') router.push('/orders')
  else router.push('/items')
}
</script>

<template>
  <Teleport to="body">
    <div v-if="s.open" class="mask" @click.self="s.close()">
      <div class="modal search-modal">
        <input
          ref="inputEl"
          v-model="s.q"
          class="f-search big"
          placeholder="Заказы и товары… (Ctrl+K)"
          @keydown.esc="s.close()"
        />
        <div v-if="s.loading" class="muted">Ищу…</div>
        <div v-else-if="s.err" class="err-text">{{ s.err }}</div>
        <div v-else-if="s.q.length >= 2 && !s.hits.length" class="muted">Ничего не найдено</div>
        <div v-for="hh in s.hits" :key="String(hh.id)" class="hit click" @click="go(hh)">
          <span class="badge">{{ hh.kind === 'order' ? 'заказ' : 'товар' }}</span>
          <b>{{ hh.title }}</b> <span class="muted">— {{ hh.sub }}</span>
        </div>
        <div class="muted small">Esc — закрыть</div>
      </div>
    </div>
  </Teleport>
</template>
