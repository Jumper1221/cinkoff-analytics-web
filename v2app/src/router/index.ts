import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory('/v2/'),
  routes: [
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/orders', name: 'orders', component: () => import('../views/OrdersView.vue') },
    { path: '/items', name: 'items', component: () => import('../views/ItemsView.vue') },
    { path: '/remnants', name: 'remnants', component: () => import('../views/RemnantsView.vue') },
    { path: '/prices', name: 'prices', component: () => import('../views/PricesView.vue') },
    { path: '/years', name: 'years', component: () => import('../views/YearsView.vue') },
    { path: '/forecast', name: 'forecast', component: () => import('../views/ForecastView.vue') },
    { path: '/branches', name: 'branches', component: () => import('../views/BranchesView.vue') },
    { path: '/heatmap', name: 'heatmap', component: () => import('../views/HeatmapView.vue') },
    { path: '/people', name: 'people', component: () => import('../views/PeopleView.vue') },
  ],
})

export default router
