import { createApp } from 'vue'
import { createPinia } from 'pinia'
import App from './App.vue'
import router from './router'
import './styles/main.css'

const saved = localStorage.getItem('ca-theme') ?? 'light'
document.documentElement.dataset.theme = saved

createApp(App).use(createPinia()).use(router).mount('#app')
