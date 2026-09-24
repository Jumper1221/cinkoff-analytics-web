import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { fmtMoney, fmtMln, fmtInt, fmtDate } from '../src/api/client'
import App from '../src/App.vue'
import { createRouter, createWebHistory } from 'vue-router'

describe('форматтеры', () => {
  it('деньги/миллионы/инт/дата', () => {
    expect(fmtMoney(1219.9)!.replace('\u00A0', ' ')).toBe('1 220 ₽')
    expect(fmtMoney(null)).toBe('—')
    expect(fmtMln(77_300_000)).toBe('77,3 млн')
    expect(fmtInt(1234567)!.replace(/\u00A0/g, ' ')).toContain('1 234 567')
    expect(fmtDate('2019-07-02T00:00:00')).toBe('2019-07-02')
    expect(fmtDate(null)).toBe('—')
  })
})

describe('App-маунт', () => {
  it('сайдбар 9 пунктов + рендер без ошибок', async () => {
    const router = createRouter({ history: createWebHistory('/v2/'), routes: [
      { path: '/', component: { template: '<div/>' } },
    ]})
    await router.push('/')
    const w = mount(App, { global: { plugins: [createPinia(), router] } })
    expect(w.findAll('.nav-item').length).toBe(9)
    expect(w.text()).toContain('Cinkoff Analytics')
  })
})
