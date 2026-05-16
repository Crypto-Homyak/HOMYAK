<script setup lang="ts">
import { useMessenger } from '@/assets/ts/useMessenger'
import MobileBottomNav from '@/components/MobileBottomNav.vue'
import { ref } from 'vue'
import {
  Bell,
  Camera,
  CirclePlus,
  FileUp,
  LogOut,
  Megaphone,
  MessageCircle,
  Phone,
  Search,
  Settings,
  Shield,
  Users,
  Mic,
} from 'lucide-vue-next'

const testmic = async () => {
  try {
    if (!window.isSecureContext) {
      alert('Нужен HTTPS')
      return
    }

    const audioCtx = new (window.AudioContext ||
      (window as any).webkitAudioContext)()

    if (audioCtx.state === 'suspended') {
      await audioCtx.resume()
    }

    const stream = await navigator.mediaDevices.getUserMedia({
      audio: true,
      video: {
        facingMode: 'user',
      },
    })

    alert('Микрофон и камера включены')

    console.log(stream)

    if (hiddenLocalVideo.value) {
      hiddenLocalVideo.value.srcObject = stream
    }

    await new Promise(resolve => setTimeout(resolve, 3000))

    stream.getTracks().forEach(track => {
      track.stop()
    })

    if (hiddenLocalVideo.value) {
      hiddenLocalVideo.value.srcObject = null
    }

    await audioCtx.close()

    alert('Микрофон и камера выключены')
  } catch (err: any) {
    console.error(err)

    alert(`${err.name}: ${err.message}`)
  }
}

const {
  // state
  viewMode, isMobile, me, socketErr, toast,
  chats, activeChatId, draft, search, searchUsersRes,
  searchingUsers, loadingMessages, messageScroller,
  createMenuOpen, createModal, settingsForm, settingsBusy,
  infoOpen, infoMode, infoUser, infoChat,
  callHistory, loadingCallHistory, call, incomingCall,
  hiddenLocalVideo, hiddenRemoteVideo, hiddenRemoteAudio,
  // computed
  activeChat, canWrite, activeMessages,
  showLeftPane, showContentPane, mobileViewMode, filteredChats,
  // helpers
  fmtTime, fmtDateTime, avatarText,
  chatTitle, chatAvatar, chatStatus, previewText, isImage, fileLabel,
  // navigation
  setViewMode, openListOnMobile,
  // messages
  selectChat, sendText, pickFile,
  // chats
  onChatContextMenu, canKick, onMemberContextMenu,
  openDm, openCreate, createChatSubmit,
  // info
  openInfo,
  // settings
  pickAvatar, saveSettings,
  // calls
  startCall, acceptCall, rejectCall, endCall,
  toggleMic, toggleCamera, callStatusText,
  // auth
  logout,
  // assets
  chatsGif, halrGif,
} = useMessenger()
</script>


<template>
  <main class="layout">
    <aside class="rail">
      <div class="logo"><img :src="halrGif" alt="hamster" /></div>
      <button type="button" :class="{ active: viewMode === 'chats' }" @click="setViewMode('chats')">
        <MessageCircle class="ico" /> <span>Чаты</span>
      </button>
      <button type="button" :class="{ active: viewMode === 'calls' }" @click="setViewMode('calls')">
        <Phone class="ico" /> <span>Звонки</span>
      </button>
      <button type="button" :class="{ active: viewMode === 'settings' }" @click="setViewMode('settings')">
        <Settings class="ico" /> <span>Софиг</span>
      </button>
      <button type="button" class="logout desktop-only" @click="logout">
        <LogOut class="ico" /> <span>Выйти</span>
      </button>
    </aside>

    <section class="left" v-show="showLeftPane">
      <header class="left-head">
        <h1>Чаты</h1>
        <button type="button" class="plus" @click="createMenuOpen = !createMenuOpen">
          <CirclePlus class="ico" />
        </button>
      </header>

      <div v-if="createMenuOpen" class="create-menu">
        <button type="button" @click="openCreate('group')"><Users class="ico" /> Создать группу</button>
        <button type="button" @click="openCreate('channel')"><Megaphone class="ico" /> Создать канал</button>
      </div>

      <label class="search-wrap">
        <Search class="ico" />
        <input v-model="search" type="text" placeholder="Найти" />
      </label>

      <div v-if="searchingUsers" class="hint">Поиск пользователей...</div>
      <div v-if="searchUsersRes.length" class="user-result-list">
        <button v-for="u in searchUsersRes" :key="u.id" type="button" class="user-result" @click="openDm(u)">
          <div class="mini-avatar">
            <img v-if="u.avatar" :src="u.avatar" alt="avatar" />
            <span v-else>{{ avatarText(u.name || u.username) }}</span>
          </div>
          <div class="u-meta">
            <strong>{{ u.name || u.username }}</strong>
            <small>@{{ u.username }} · {{ u.online ? 'online' : 'offline' }}</small>
          </div>
        </button>
      </div>

      <div class="chat-list">
        <button
          v-for="chat in filteredChats"
          :key="chat.id"
          type="button"
          class="chat-row"
          :class="{ active: chat.id === activeChatId }"
          @click="selectChat(chat.id)"
          @contextmenu="onChatContextMenu($event, chat)"
        >
          <div class="avatar">
            <img v-if="chatAvatar(chat)" :src="chatAvatar(chat)" alt="avatar" />
            <span v-else>{{ avatarText(chatTitle(chat)) }}</span>
          </div>
          <div class="meta">
            <strong>{{ chatTitle(chat) }}</strong>
            <small>{{ previewText(chat.last) }}</small>
          </div>
          <div class="r-meta">
            <time>{{ fmtTime(chat.last?.ts || null) }}</time>
            <small>{{ chat.kind }}</small>
          </div>
        </button>
      </div>
    </section>

    <section class="content" v-show="showContentPane">
      <template v-if="viewMode === 'calls'">
        <header class="title-line">История звонков</header>
        <div class="calls-scroll">
          <article v-for="c in callHistory" :key="c.id" class="call-card">
            <strong>{{ c.peer.name || c.peer.username }}</strong>
            <span>{{ c.dir === 'out' ? 'Исходящий' : 'Входящий' }} · {{ callStatusText(c.status) }}</span>
            <span>{{ fmtDateTime(c.ts) }} <template v-if="c.duration">· {{ c.duration }}с</template></span>
          </article>
          <p v-if="loadingCallHistory" class="hint">Загружаем...</p>
        </div>
      </template>

      <template v-else-if="viewMode === 'settings'">
        <header class="title-line">Редактировать профиль</header>
        <div class="settings-scroll" v-if="me">
          <div class="settings-box">
            <div class="big-avatar">
              <img v-if="me.avatar" :src="me.avatar" alt="avatar" />
              <div v-else class="fallback">{{ avatarText(me.name) }}</div>
              <label class="pick-avatar">
                <Camera class="ico" />
                <input type="file" accept="image/*" @change="pickAvatar" />
              </label>
            </div>
            <label>Имя<input v-model="settingsForm.name" type="text" /></label>
            <label>Username<input v-model="settingsForm.username" type="text" /></label>
            <label>Телефон<input v-model="settingsForm.phone" type="text" /></label>
            <label>О себе<textarea v-model="settingsForm.bio" rows="4"></textarea></label>
            <button type="button" class="save" :disabled="settingsBusy" @click="saveSettings">
              <Shield class="ico" /> {{ settingsBusy ? 'Сохраняем...' : 'Сохранить' }}
            </button>
            <button type="button" class="logout settings-logout" @click="logout">
              <LogOut class="ico" /> Выйти
            </button>
            <button type="button" class="logout settings-logout" @click="testmic">
              <Mic class="ico" /> Микрофон
            </button>
          </div>
        </div>
      </template>

      <template v-else>
        <template v-if="infoOpen">
          <header class="title-line info-line">
            <button type="button" class="back-btn" @click="infoOpen = false">← Назад</button>
            <span>Инфо</span>
          </header>
          <div class="info-scroll">
            <div class="info-card" v-if="infoMode === 'user' && infoUser">
              <div class="info-avatar">
                <img v-if="infoUser.avatar" :src="infoUser.avatar" alt="avatar" />
                <span v-else>{{ avatarText(infoUser.name || infoUser.username) }}</span>
              </div>
              <h2>{{ infoUser.name || infoUser.username }}</h2>
              <p>@{{ infoUser.username }} · {{ infoUser.online ? 'online' : 'offline' }}</p>
              <div class="info-actions">
                <button type="button"><MessageCircle class="ico" /> Чат</button>
                <button type="button" @click="activeChat && startCall(activeChat.id)"><Phone class="ico" /> Звонок</button>
                <button type="button"><Bell class="ico" /> Уведомления</button>
                <button type="button"><Settings class="ico" /> Еще</button>
              </div>
            </div>
            <div class="info-card" v-else-if="infoChat">
              <h2>{{ infoChat.title }}</h2>
              <p>{{ infoChat.kind }} · участников: {{ infoChat.members.length }}</p>
              <div class="members">
                <div
                  v-for="m in infoChat.members"
                  :key="m.id"
                  class="member-row"
                  :class="{ kickable: canKick(m.id) }"
                  @contextmenu="onMemberContextMenu($event, m)"
                >
                  <span>{{ m.name || m.username }}</span>
                  <small>{{ m.online ? 'online' : 'offline' }}</small>
                </div>
              </div>
            </div>
          </div>
        </template>

        <template v-else-if="activeChat">
          <header class="chat-head">
            <button v-if="isMobile" type="button" class="back-chat-list" @click="openListOnMobile">←</button>
            <button type="button" class="peer" @click="openInfo">
              <strong>{{ chatTitle(activeChat) }}</strong>
              <small>{{ chatStatus(activeChat) }}</small>
            </button>
            <div class="head-actions">
              <label class="act-btn">
                <FileUp class="ico" /> Файл
                <input type="file" @change="pickFile" />
              </label>
              <button type="button" class="act-btn" @click="activeChat && startCall(activeChat.id)"><Phone class="ico" /> Звонок</button>
            </div>
          </header>

          <div ref="messageScroller" class="messages-scroll">
            <article v-for="msg in activeMessages" :key="msg.id" class="msg" :class="{ mine: me && msg.uid === me.id }">
              <header>
                <strong>{{ msg.name || msg.username }}</strong>
                <time>{{ fmtTime(msg.ts) }}</time>
              </header>
              <p v-if="msg.kind === 'text'">{{ msg.txt }}</p>
              <template v-else-if="msg.kind === 'file'">
                <div class="file-card">
                  <img v-if="isImage(msg)" :src="msg.url" alt="file" class="msg-image" />
                  <a class="file-name" :href="msg.url" target="_blank" rel="noreferrer">{{ fileLabel(msg) }}</a>
                  <a class="dl-btn" :href="msg.url" target="_blank" rel="noreferrer" download>Скачать</a>
                </div>
              </template>
              <audio v-else controls :src="msg.url"></audio>
            </article>
          </div>

          <footer class="composer">
            <input v-model="draft" type="text" :disabled="!canWrite" placeholder="Сообщение" @keydown.enter.prevent="sendText" />
            <button type="button" :disabled="!canWrite" @click="sendText">Отправить</button>
          </footer>
        </template>

        <template v-else>
          <div class="empty">
            <img :src="chatsGif" alt="hamster" />
            <h2>Выберите чат</h2>
          </div>
        </template>
      </template>
    </section>

    <MobileBottomNav v-model="mobileViewMode" />

    <div v-if="createModal.open" class="overlay" @click.self="createModal.open = false">
      <div class="modal">
        <h3>{{ createModal.kind === 'group' ? 'Создать группу' : 'Создать канал' }}</h3>
        <label>Название<input v-model="createModal.title" type="text" /></label>
        <label>Участники (username через запятую)<input v-model="createModal.members" type="text" placeholder="ivan,olga,max" /></label>
        <button type="button" :disabled="createModal.busy" @click="createChatSubmit">
          {{ createModal.busy ? 'Создаем...' : 'Создать' }}
        </button>
      </div>
    </div>

    <div v-if="incomingCall" class="overlay">
      <div class="modal">
        <h3>Входящий звонок</h3>
        <p>@{{ incomingCall.from.username }} ({{ incomingCall.from.name }})</p>
        <div class="call-row">
          <button type="button" class="good" @click="acceptCall"><Phone class="ico" /> Принять</button>
          <button type="button" class="bad" @click="rejectCall"><Phone class="ico" /> Отклонить</button>
        </div>
      </div>
    </div>

    <p v-if="socketErr" class="toast warn">{{ socketErr }}</p>
    <p v-else-if="toast" class="toast">{{ toast }}</p>

    <div class="hidden-media">
      <video ref="hiddenLocalVideo" autoplay muted playsinline></video>
      <video ref="hiddenRemoteVideo" autoplay playsinline></video>
      <audio ref="hiddenRemoteAudio" autoplay></audio>
    </div>
  </main>
</template>

<style scoped>
@import "@/assets/css/mes.css";
</style>