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

/** канвас-реф + отрисовка-конфига-после-пинcede; сам-убивает-инстанс-при-перерисовке/unmount */
export function useChart(draw: () => ChartConfiguration | null, dep: Ref<unknown>) {
  const canvas = ref<HTMLCanvasElement | null>(null)
  let inst: Chart | null = null

  function render() {
    if (!canvas.value) return
    const cfg = draw()
    if (!cfg) { inst?.destroy(); inst = null; return }
    if (inst) inst.destroy()
    inst = new Chart(canvas.value, cfg)
  }

  onMounted(async () => { await nextTick(); if (dep.value != null) render() })
  watch(dep, async (v) => { if (v != null) { await nextTick(); render() } })
  onUnmounted(() => inst?.destroy())
  return { canvas, render }
}
