<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="onSubmit">
      <div class="brand">Stocks</div>
      <div class="subtitle">股票复盘 · 登录</div>

      <label class="field">
        <span class="field-label">账号</span>
        <input
          v-model="username"
          type="text"
          autocomplete="username"
          placeholder="请输入账号"
          :disabled="loading"
        />
      </label>

      <label class="field">
        <span class="field-label">密码</span>
        <input
          v-model="password"
          type="password"
          autocomplete="current-password"
          placeholder="请输入密码"
          :disabled="loading"
        />
      </label>

      <div v-if="error" class="error">{{ error }}</div>

      <button class="submit" type="submit" :disabled="loading">
        {{ loading ? '登录中...' : '登 录' }}
      </button>
    </form>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const route = useRoute()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function onSubmit() {
  if (loading.value) return
  error.value = ''
  if (!username.value || !password.value) {
    error.value = '请输入账号和密码'
    return
  }
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    const redirect = (route.query.redirect as string) || '/'
    router.replace(redirect)
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '登录失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100vh;
  width: 100vw;
  background: #0b0f19;
}

.login-card {
  width: 340px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  background: #1f2937;
  border: 1px solid #374151;
  border-radius: 10px;
  padding: 32px 28px;
}

.brand {
  font-size: 26px;
  font-weight: 700;
  color: #60a5fa;
  text-align: center;
}

.subtitle {
  font-size: 13px;
  color: #9ca3af;
  text-align: center;
  margin-bottom: 6px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.field-label {
  font-size: 13px;
  color: #9ca3af;
}

.field input {
  width: 100%;
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #374151;
  background: #111827;
  color: #e5e7eb;
  font-size: 14px;
}

.field input:focus {
  outline: none;
  border-color: #2563eb;
}

.error {
  font-size: 13px;
  color: #ef4444;
  text-align: center;
}

.submit {
  margin-top: 6px;
  padding: 11px;
  border-radius: 6px;
  border: none;
  background: #2563eb;
  color: #fff;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.submit:hover:not(:disabled) {
  background: #1d4ed8;
}

.submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
</style>
