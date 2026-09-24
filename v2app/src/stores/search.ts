import { defineStore } from 'pinia'

export interface SearchHit { kind: 'order' | 'item'; id: number | string; title: string; sub: string }

export const useSearchStore = defineStore('search', {
  state: () => ({ open: false, q: '', loading: false, hits: [] as SearchHit[], err: '' }),
  actions: {
    toggle() { this.open = !this.open; if (this.open) this.q = ''; this.hits = []; this.err = '' },
    close() { this.open = false },
    async run() {
      if (this.q.trim().length < 2) { this.hits = []; return }
      this.loading = true; this.err = ''
      try {
        const r = await fetch(`/api/search_all?s=${encodeURIComponent(this.q.trim())}`)
        if (!r.ok) throw new Error(`${r.status}`)
        const j = await r.json()
        this.hits = [
          ...(j.orders ?? []).map((o: any) => ({ kind: 'order' as const, id: o.order_id, title: o.number, sub: `${o.order_date?.slice(0, 10) ?? ''} · ${o.contractor_name ?? ''} · ${(+o.sum || 0).toFixed(0)} ₽` })),
          ...(j.items ?? []).map((i: any) => ({ kind: 'item' as const, id: i.id_1c, title: i.full_name, sub: i.group_name ?? '' })),
        ]
      } catch (e: any) { this.err = e?.message ?? String(e) }
      finally { this.loading = false }
    },
  },
})
