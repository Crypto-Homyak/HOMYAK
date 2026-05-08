import { createApp } from 'vue'
import App from './App.vue'
import { createRouter, createWebHistory } from 'vue-router'

import Auth from './routes/auth.vue'
import Messenger from './routes/mes.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: Auth },
    { path: '/messenger', component: Messenger },
    { path: '/max', redirect: '/messenger' },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

const app = createApp(App)

app.use(router)
app.mount('#app')
