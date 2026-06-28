<template>
  <!-- 登录等公开页面：独立全屏布局，不显示侧边栏 -->
  <router-view v-if="isPublic" />
  <div v-else class="app">
    <Sidebar />
    <main class="main-content">
      <router-view />
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import Sidebar from './components/layout/Sidebar.vue'

const route = useRoute()
const isPublic = computed(() => route.meta.public === true)
</script>

<style>
.app {
  display: flex;
  height: 100vh;
  width: 100vw;
  background: #0b0f19;
}

.main-content {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  height: 100vh;
}
</style>
