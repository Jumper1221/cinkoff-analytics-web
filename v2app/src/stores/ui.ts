import { defineStore } from 'pinia'

type Toast = { id: number; kind: 'ok' | 'err'; text: string }

export const useUiStore = defineStore('ui', {
  state: () => ({ theme: (localStorage.getItem('ca-theme') ?? 'light') as 'light' | 'dark', toasts: [] as Toast[] }),
  actions: {
    toggleTheme() {
      this.theme = this.theme === 'light' ? 'dark' : 'light'
      localStorage.setItem('ca-theme', this.theme)
      document.documentElement.dataset.theme = this.theme
    },
    toast(kind: Toast['kind'], text: string) {
      const id = Date.now() + Math.random()
      this.toasts.push({ id, kind, text })
      setTimeout(() => (this.toasts = this.toasts.filter(t => t.id !== id)), 4000)
    },
  },
})
