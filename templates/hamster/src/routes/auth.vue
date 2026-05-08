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
@import url('https://fonts.googleapis.com/css2?family=Rubik:wght@400;600;700&display=swap');

:global(*) {
  box-sizing: border-box;
}

:global(body) {
  background-color: #0d1220;
  color: #e8edf8;
  margin: 0;
  min-height: 100vh;
  font-family: 'Rubik', 'Segoe UI', sans-serif;
  background:
    radial-gradient(circle at 20% 15%, rgba(33, 126, 255, 0.22), transparent 35%),
    radial-gradient(circle at 82% 80%, rgba(248, 176, 21, 0.18), transparent 30%),
    #0d1220;
}

.auth-page {
  min-height: 100vh;
  display: grid;
  place-items: center;
  padding: 24px;
}

.auth-card {
  width: min(520px, 100%);
  border-radius: 0;
  border: 1px solid rgba(123, 150, 205, 0.35);
  background: rgba(16, 22, 40, 0.9);
  box-shadow: 0 18px 55px rgba(0, 0, 0, 0.48);
  padding: 24px;
  animation: up 0.4s ease-out;
}

.auth-brand {
  text-align: center;
}

.brand-gif {
  width: 92px;
  height: 92px;
  border-radius: 0;
  border: 1px solid rgba(123, 150, 205, 0.45);
  object-fit: cover;
}

.auth-brand h1 {
  margin: 12px 0 4px;
  font-size: 34px;
  letter-spacing: 0.04em;
}

.auth-brand p {
  margin: 0;
  color: #b8c4dd;
}

.mode-tabs {
  margin-top: 18px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.mode-tabs button {
  border: 0;
  border-radius: 0;
  padding: 10px;
  cursor: pointer;
  color: #dbe6ff;
  background: #202b4b;
}

.mode-tabs button.active {
  background: linear-gradient(130deg, #1f74ff, #3da9ff);
  color: #fff;
}

.auth-form {
  margin-top: 16px;
  display: grid;
  gap: 12px;
}

label {
  display: grid;
  gap: 6px;
  color: #b6c3dc;
  font-size: 14px;
}

input {
  width: 100%;
  border-radius: 0;
  border: 1px solid #30406b;
  background: #101933;
  color: #f1f6ff;
  padding: 11px 12px;
  font-size: 15px;
}

input:focus {
  outline: 2px solid #2b8dff;
  outline-offset: 1px;
}

.error {
  margin: 0;
  color: #ff9fa8;
  font-size: 14px;
}

.submit {
  margin-top: 4px;
  border: 0;
  border-radius: 0;
  padding: 12px;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  cursor: pointer;
  background: linear-gradient(130deg, #3f8cff, #0065ff);
}

.submit:disabled {
  opacity: 0.55;
  cursor: default;
}

@keyframes up {
  from {
    transform: translateY(14px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}
</style>
