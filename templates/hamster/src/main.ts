import { createApp } from 'vue'
import App from './App.vue'
import { createRouter, createWebHistory } from 'vue-router'

import Auth from './routes/auth.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/',  component: Auth},
    { path: '/max', component: () => import('@/routes/mes.vue') }
  ]
})

const app = createApp(App)

app.use(router)
app.mount('#app')