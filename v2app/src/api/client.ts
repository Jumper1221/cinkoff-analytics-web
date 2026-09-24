import { onMounted, onUnmounted, ref, type Ref } from 'vue'

const BASE = '' // тот же origin: в деве проксирует Vite, в проде тот же FastAPI

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function request<T>(path: string, signal?: AbortSignal, retries = 2): Promise<T> {
  let lastErr: unknown
  for (let attempt = 0; attempt <= retries; attempt++) {
    try {
      const res = await fetch(BASE + path, { signal, headers: { accept: 'application/json' } })
      if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText}`)
      return (await res.json()) as T
    } catch (e) {
      lastErr = e
      if (signal?.aborted) throw e
      if (attempt < retries) await new Promise(r => setTimeout(r, 400 * (attempt + 1)))
    }
  }
  throw lastErr
}

/** Загрузка с生命周期: abort при unmount, loading/error/data — готовые рефы */
export function useApi<T>(path: () => string, immediate = true) {
  const data: Ref<T | null> = ref(null)
  const loading = ref(false)
  const error = ref('')
  let ctrl: AbortController | null = null

  async function load() {
    ctrl?.abort()
    ctrl = new AbortController()
    loading.value = true
    error.value = ''
    try { data.value = await request<T>(path(), ctrl.signal) }
    catch (e: any) {
      if (e?.name !== 'AbortError') error.value = e?.message ?? String(e)
    }
    finally { if (!ctrl?.signal.aborted) loading.value = false }
  }

  if (immediate) onMounted(load)
  onUnmounted(() => ctrl?.abort())
  return { data, loading, error, load }
}

export const fmtMoney = (v: number | null | undefined) =>
  v == null ? '—' : new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 }).format(v) + ' ₽'
export const fmtMln = (v: number | null | undefined) =>
  v == null ? '—' : (v / 1e6).toFixed(1).replace('.', ',') + ' млн'
export const fmtDate = (v: string | null | undefined) => (v ? v.slice(0, 10) : '—')
export const fmtInt = (v: number | null | undefined) =>
  v == null ? '—' : new Intl.NumberFormat('ru-RU').format(v)
