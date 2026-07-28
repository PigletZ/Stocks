<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-overlay" @click.self="$emit('close')">
      <div class="modal-card" :style="{ width }">
        <div class="modal-header">
          <span>{{ title }}</span>
          <button class="modal-close" @click="$emit('close')">✕</button>
        </div>
        <div class="modal-body">
          <slot />
        </div>
        <div v-if="$slots.footer" class="modal-footer">
          <slot name="footer" />
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
defineProps<{
  visible: boolean
  title: string
  width?: string
}>()

defineEmits<{
  (e: 'close'): void
}>()
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-card {
  width: 420px;
  max-width: 92vw;
  background: #1f2937;
  border-radius: 10px;
  border: 1px solid #374151;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid #374151;
  font-size: 15px;
  font-weight: 600;
  color: #e5e7eb;
}

.modal-close {
  background: none;
  border: none;
  color: #9ca3af;
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
}

.modal-close:hover {
  color: #e5e7eb;
}

.modal-body {
  padding: 18px;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 0 18px 18px;
}
</style>
