import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { api } from '../api/client'

const TOKEN_KEY = 'stocks_auth_token'
const EXP_KEY = 'stocks_auth_exp'
const USER_KEY = 'stocks_auth_user'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
  const expiresAt = ref<number>(Number(localStorage.getItem(EXP_KEY) || 0))
  const username = ref<string>(localStorage.getItem(USER_KEY) || '')

  // token 存在且未过期（expiresAt 为 Unix 秒）
  const isAuthenticated = computed(
    () => !!token.value && expiresAt.value * 1000 > Date.now()
  )

  async function login(user: string, password: string) {
    const res = await api.post('/auth/login', { username: user, password })
    token.value = res.data.token
    expiresAt.value = res.data.expires_at
    username.value = res.data.username
    localStorage.setItem(TOKEN_KEY, token.value)
    localStorage.setItem(EXP_KEY, String(expiresAt.value))
    localStorage.setItem(USER_KEY, username.value)
  }

  function logout() {
    token.value = ''
    expiresAt.value = 0
    username.value = ''
    localStorage.removeItem(TOKEN_KEY)
    localStorage.removeItem(EXP_KEY)
    localStorage.removeItem(USER_KEY)
  }

  return { token, expiresAt, username, isAuthenticated, login, logout }
})
