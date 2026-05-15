<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import halrGif from '@/assets/icons/halr.gif'

interface AuthUser {
  id: number
  username: string
  name: string
  email: string
  avatar: string
}

const router = useRouter()
const mode = ref<'login' | 'register'>('login')
const busy = ref(false)
const err = ref('')

const loginValue = ref('')
const password = ref('')
const username = ref('')
const displayName = ref('')
const email = ref('')

const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined)?.trim() || 'https://cryptohomyak.team/api').replace(/\/$/, '')

const titleText = computed(() => (mode.value === 'login' ? 'Вход в Homyak Messenger' : 'Регистрация в Homyak Messenger'))
const endpoint = computed(() => (mode.value === 'login' ? '/login' : '/register'))

function saveAuth(token: string, user: AuthUser): void {
  localStorage.setItem('hamster_token', token)
  localStorage.setItem('hamster_user', JSON.stringify(user))
}

function switchMode(next: 'login' | 'register'): void {
  err.value = ''
  mode.value = next
}

async function submit(): Promise<void> {
  if (busy.value) {
    return
  }

  err.value = ''

  if (mode.value === 'login') {
    if (!loginValue.value.trim() || !password.value.trim()) {
      err.value = 'Введите логин и пароль.'
      return
    }
  } else if (!username.value.trim() || !password.value.trim()) {
    err.value = 'Username и пароль обязательны.'
    return
  }

  busy.value = true
  try {
    const payload =
      mode.value === 'login'
        ? {
            login: loginValue.value.trim().toLowerCase(),
            password: password.value,
          }
        : {
            username: username.value.trim().toLowerCase(),
            password: password.value,
            name: displayName.value.trim() || username.value.trim(),
            email: email.value.trim().toLowerCase() || `${username.value.trim().toLowerCase()}@local`,
          }

    const res = await fetch(`${API_BASE}${endpoint.value}`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    })

    const dat = (await res.json()) as {
      ok?: boolean
      err?: string
      token?: string
      user?: AuthUser
    }

    if (!res.ok || !dat.ok || !dat.token || !dat.user) {
      err.value = dat.err || 'Не удалось выполнить запрос.'
      return
    }

    saveAuth(dat.token, dat.user)
    void router.push('/messenger')
  } catch {
    err.value = 'Сеть недоступна. Проверьте интернет или base URL.'
  } finally {
    busy.value = false
  }
}

onMounted(() => {
  const token = localStorage.getItem('hamster_token')
  if (token) {
    void router.push('/messenger')
  }
})
</script>

<template>
  <main class="auth-page">
    <section class="auth-card">
      <div class="auth-brand">
        <img :src="halrGif" alt="Hamster" class="brand-gif" />
        <h1>Homyak</h1>
        <p>{{ titleText }}</p>
      </div>

      <div class="mode-tabs">
        <button :class="{ active: mode === 'login' }" type="button" @click="switchMode('login')">Вход</button>
        <button :class="{ active: mode === 'register' }" type="button" @click="switchMode('register')">Регистрация</button>
      </div>

      <form class="auth-form" @submit.prevent="submit">
        <label v-if="mode === 'login'">
          Логин или email
          <input v-model="loginValue" type="text" autocomplete="username" placeholder="например, max_homyak" />
        </label>

        <template v-else>
          <label>
            Username
            <input v-model="username" type="text" autocomplete="username" placeholder="без пробелов" />
          </label>
          <label>
            Имя
            <input v-model="displayName" type="text" autocomplete="name" placeholder="как показывать в чатах" />
          </label>
          <label>
            Email
            <input v-model="email" type="email" autocomplete="email" placeholder="необязательно" />
          </label>
        </template>

        <label>
          Пароль
          <input v-model="password" type="password" autocomplete="current-password" placeholder="минимум 1 символ" />
        </label>

        <p v-if="err" class="error">{{ err }}</p>

        <button class="submit" type="submit" :disabled="busy">
          {{ busy ? 'Подождите...' : mode === 'login' ? 'Войти' : 'Создать аккаунт' }}
        </button>
      </form>
    </section>
  </main>
</template>

<style scoped>
@import "@/assets/css/auth.css";
</style>
