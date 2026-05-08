<script setup lang="ts">
import { MessageCircle, Phone, Settings } from 'lucide-vue-next'

type ViewMode = 'chats' | 'calls' | 'settings'

const props = defineProps<{
  modelValue: ViewMode
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: ViewMode): void
}>()

function setMode(mode: ViewMode): void {
  emit('update:modelValue', mode)
}
</script>

<template>
  <nav class="mobile-nav" aria-label="Разделы">
    <button type="button" :class="{ active: props.modelValue === 'chats' }" @click="setMode('chats')">
      <MessageCircle class="ico" />
      <span>Чаты</span>
    </button>
    <button type="button" :class="{ active: props.modelValue === 'calls' }" @click="setMode('calls')">
      <Phone class="ico" />
      <span>Звонки</span>
    </button>
    <button type="button" :class="{ active: props.modelValue === 'settings' }" @click="setMode('settings')">
      <Settings class="ico" />
      <span>Настройки</span>
    </button>
  </nav>
</template>

<style scoped>
.mobile-nav {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 40;
  height: calc(66px + env(safe-area-inset-bottom));
  padding: 8px 10px calc(8px + env(safe-area-inset-bottom));
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  border-top: 1px solid rgba(92, 128, 195, 0.55);
  background: linear-gradient(180deg, rgba(12, 20, 40, 0.98), rgba(11, 18, 36, 0.98));
  backdrop-filter: blur(10px);
}

.mobile-nav button {
  border: 1px solid rgba(67, 102, 164, 0.45);
  background: #17284f;
  color: #dce8ff;
  border-radius: 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12px;
  cursor: pointer;
}

.mobile-nav button.active {
  background: #2f5fbe;
  border-color: #7ea9ff;
  color: #ffffff;
}

.ico {
  width: 17px;
  height: 17px;
}

@media (min-width: 861px) {
  .mobile-nav {
    display: none;
  }
}
</style>
