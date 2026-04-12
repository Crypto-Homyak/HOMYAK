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
:global(body) {
  background-color: #1a1a1a;
  color: #ffffff;
  margin: 0;
  display: flex;
  height: 100vh;
}

.chats-div {
  height: 100vh;
  width: 100px;
  background-color: #252525;
  display: flex;
  justify-content: center;
  padding-top: 20px;
  flex-shrink: 0;
  z-index: 1001;
}

.chatop {
  width: 70px;
  height: 70px;
  border-radius: 50%;
  background: transparent; 
  border: none;       
  cursor: pointer;
  padding: 0;
  overflow: hidden;   
  display: flex;
  align-items: center;
  justify-content: center;
}

.chats_icon {
  width: 100%;    
  height: 100%;
  object-fit: cover;   
}

.main-content {
  flex-grow: 1;
  padding: 20px;
}

.top-panel {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 200px;
  background-color: #272727;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.5);
  z-index: 1000;
  border-bottom: 1px solid #444;
}

.panel-inner-content {
  padding: 20px 20px 20px 120px;
}

.slide-enter-active,
.slide-leave-active {
  transition: transform 0.3s ease-out;
}

.slide-enter-from,
.slide-leave-to {
  transform: translateY(-100%);
}

.list-btn, .close-btn {
  background: #333;
  color: white;
  border: 1px solid #555;
  padding: 8px 16px;
  margin-top: 10px;
  cursor: pointer;
}
</style>
