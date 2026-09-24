import { ref, watch, onMounted, nextTick, onUnmounted, type Ref } from 'vue'
import {
  Chart, registerables, type ChartConfiguration,
} from 'chart.js'

Chart.register(...registerables)

export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
export function chartColors() {
  return {
    text: cssVar('--text'), muted: cssVar('--muted'), border: cssVar('--line'),
    accent: cssVar('--accent'), ok: cssVar('--ok'), err: cssVar('--err'),
  }
}

export function useChart(draw: () => ChartConfiguration | null, dep: Ref<unknown> | (() => unknown)) {
  const canvas = ref<HTMLCanvasElement | null>(null)
  let inst: Chart | null = null

  function depVal(): unknown {
    const v: unknown = typeof dep === 'function' ? (dep as () => unknown).call(null) : (dep as Ref<unknown>).value
    // Vue-Ref-помеч-ен-«__v_isRef: true»-—-разв-орач-ива-ем (computed-над-Ref-даёт-Ref-—-класс-ический-двой-ной-слой)
    if (v && typeof v === 'object' && (v as any).__v_isRef) {
      return (v as { value: unknown }).value
    }
    return v
  }

  function render() {
    if (!canvas.value) return
    const cfg = draw()
    if (!cfg) { inst?.destroy(); inst = null; return }
    if (inst) inst.destroy()
    // responsive-режим-в-некоторых-условиях-не-делает-первый-кадр (ResizeObserver-в-момент-вирт-времени-хрома / спят-лей-аут):
    // рисуем-в-ЯВНЫЙ-размер-конт-ейнера-—-атрибуты-width/height-канваса, а-CSS-показ-ывает-1:1
    const box = canvas.value.parentElement
    const cw = Math.max(240, box?.clientWidth ?? 640)
    const ch = Math.max(180, box?.clientHeight ?? 300)
    canvas.value.width = cw
    canvas.value.height = ch
    canvas.value.setAttribute('data-chart', 'rendered')
    const opts = { ...(cfg.options ?? {}), responsive: false, animation: false, devicePixelRatio: 1 } as ChartConfiguration['options']
    inst = new Chart(canvas.value, { ...cfg, options: opts })
  }

  onMounted(async () => {
    await nextTick()
    if (depVal() != null) render()
  })
  watch(depVal as () => unknown, async (v) => {
    if (v != null) { await nextTick(); render() }
  })
  onUnmounted(() => inst?.destroy())
  return { canvas, render }
}
