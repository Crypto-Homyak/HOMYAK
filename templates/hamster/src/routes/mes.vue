<script setup lang="ts">
import { ref } from 'vue'

const isOpen = ref(false)

const togglePanel = () => {
  isOpen.value = !isOpen.value
}
</script>

<template>
  <div class="chats-div">
    <button @click="togglePanel" class="chatop">
      <img src="@/assets/icons/chats.gif" alt="icon" class="chats_icon">
      
    </button>
    <div class="vertical-line"></div>
  </div>

  <div class="main-content">
    <p>CHAT</p>
  </div>

  <Transition name="slide">
    <div v-if="isOpen" class="top-panel">
      <div class="panel-inner-content">
        <h2>HOMYAK CHATS</h2>
        <ul>
          <li>
            <button class="list-btn">HOMYAK CHATS</button>
          </li>
        </ul>
        <button @click="isOpen = false" class="close-btn">CHATTING</button>
      </div>
    </div>
  </Transition>
</template>

<style scoped>
@import '@/assets/messenger/main.css';
</style>
