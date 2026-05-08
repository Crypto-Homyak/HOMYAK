<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
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
} from 'lucide-vue-next'
import MobileBottomNav from '@/components/MobileBottomNav.vue'
import chatsGif from '@/assets/icons/chats.gif'
import halrGif from '@/assets/icons/halr.gif'

type ViewMode = 'chats' | 'calls' | 'settings'
type ProfileMode = 'user' | 'chat'

interface UserLite {
  id: number
  username: string
  name: string
  email: string
  avatar: string
  bio: string
  phone: string
  online: boolean
}

interface ChatMember {
  id: number
  username: string
  name: string
  avatar: string
  role: string
  online: boolean
}

interface WsMessage {
  id: number
  cid: number
  uid: number
  txt: string
  kind: 'text' | 'file' | 'voice'
  url: string
  fname: string
  ts: string | null
  username: string
  name: string
  avatar: string
}

interface ChatItem {
  id: number
  title: string
  raw: string
  kind: 'dm' | 'group' | 'channel'
  is_grp: boolean
  own: number
  my_role: string
  can_w: boolean
  cdt: string | null
  members: ChatMember[]
  last: WsMessage | null
}

interface CallHistory {
  id: number
  cid: string
  chat: number
  status: string
  duration: number
  ts: string | null
  dir: 'in' | 'out'
  peer: {
    id: number
    username: string
    name: string
    avatar: string
    online: boolean
  }
}

interface WsPacket {
  act?: string
  ok?: boolean
  err?: string
  [key: string]: unknown
}

const router = useRouter()
const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined)?.trim() || 'https://cryptohomyak.team/api').replace(/\/$/, '')
const CLOUD_UPLOAD = 'https://cloud.onlysq.ru/upload'

function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

function wsUrl(): string {
  const u = new URL(API_BASE)
  const proto = u.protocol === 'https:' ? 'wss:' : 'ws:'
  const pth = u.pathname.replace(/\/$/, '')
  return `${proto}//${u.host}${pth}/ws`
}

const viewMode = ref<ViewMode>('chats')
const isMobile = ref(false)
const mobilePane = ref<'list' | 'chat'>('list')
const token = ref('')
const me = ref<UserLite | null>(null)
const connected = ref(false)
const socketErr = ref('')
const toast = ref('')
let toastTimer = 0

const chats = ref<ChatItem[]>([])
const activeChatId = ref(0)
const messagesByChat = reactive<Record<number, WsMessage[]>>({})
const draft = ref('')
const search = ref('')
const searchUsersRes = ref<UserLite[]>([])
const searchingUsers = ref(false)
const loadingMessages = ref(false)
const messageScroller = ref<HTMLElement | null>(null)

const createMenuOpen = ref(false)
const createModal = reactive({
  open: false,
  kind: 'group' as 'group' | 'channel',
  title: '',
  members: '',
  busy: false,
})

const settingsForm = reactive({
  name: '',
  username: '',
  phone: '',
  bio: '',
})
const settingsBusy = ref(false)

const infoOpen = ref(false)
const infoMode = ref<ProfileMode>('user')
const infoUser = ref<UserLite | null>(null)
const infoChat = ref<ChatItem | null>(null)

const callHistory = ref<CallHistory[]>([])
const loadingCallHistory = ref(false)

const call = reactive({
  cid: '',
  chat: 0,
  status: 'idle' as 'idle' | 'ringing' | 'talk' | 'error',
  note: '',
  micMuted: false,
  camOff: false,
})
const incomingCall = ref<{ cid: string; chat: number; from: { id: number; username: string; name: string } } | null>(null)

const hiddenLocalVideo = ref<HTMLVideoElement | null>(null)
const hiddenRemoteVideo = ref<HTMLVideoElement | null>(null)
const hiddenRemoteAudio = ref<HTMLAudioElement | null>(null)

let ws: WebSocket | null = null
let manualWsClose = false
let reconnectTimer = 0
let mobileMql: MediaQueryList | null = null
const pending = new Map<string, Array<{ resolve: (value: WsPacket) => void; reject: (reason: Error) => void; timer: number }>>()

let pc: RTCPeerConnection | null = null
let localStream: MediaStream | null = null
let remoteStream: MediaStream | null = null
let callPopup: Window | null = null
let popupLocalVideo: HTMLVideoElement | null = null
let popupRemoteVideo: HTMLVideoElement | null = null
let popupStatus: HTMLElement | null = null
let popupMicBtn: HTMLButtonElement | null = null
let popupCamBtn: HTMLButtonElement | null = null

const activeChat = computed(() => chats.value.find((x) => x.id === activeChatId.value) || null)
const canWrite = computed(() => Boolean(activeChat.value?.can_w))
const activeMessages = computed(() => {
  if (activeChatId.value <= 0) {
    return []
  }
  return messagesByChat[activeChatId.value] || []
})
const activePeer = computed(() => {
  if (!activeChat.value || !me.value || activeChat.value.kind !== 'dm') {
    return null
  }
  return activeChat.value.members.find((x) => x.id !== me.value!.id) || null
})

const showLeftPane = computed(() => {
  if (!isMobile.value) return true
  if (viewMode.value !== 'chats') return false
  return mobilePane.value === 'list'
})

const showContentPane = computed(() => {
  if (!isMobile.value) return true
  if (viewMode.value !== 'chats') return true
  return mobilePane.value === 'chat'
})

const mobileViewMode = computed<ViewMode>({
  get: () => viewMode.value,
  set: (v) => setViewMode(v),
})

const filteredChats = computed(() => {
  const q = search.value.trim().toLowerCase()
  const sorted = [...chats.value].sort((a, b) => (b.last?.id || 0) - (a.last?.id || 0))
  if (!q) {
    return sorted
  }
  return sorted.filter((x) => {
    const t = chatTitle(x).toLowerCase()
    const p = (x.last?.txt || '').toLowerCase()
    return t.includes(q) || p.includes(q)
  })
})

function setToast(text: string): void {
  toast.value = text
  if (toastTimer) {
    window.clearTimeout(toastTimer)
  }
  toastTimer = window.setTimeout(() => {
    toast.value = ''
  }, 2600)
}

function clearAuthAndBack(): void {
  localStorage.removeItem('hamster_token')
  localStorage.removeItem('hamster_user')
  manualWsClose = true
  if (ws) {
    ws.close()
  }
  void router.push('/')
}

function fmtTime(ts: string | null): string {
  if (!ts) return ''
  const d = new Date(ts)
  return d.toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
}

function fmtDateTime(ts: string | null): string {
  if (!ts) return ''
  return new Date(ts).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function avatarText(name: string): string {
  return (name.trim().slice(0, 1) || '?').toUpperCase()
}

function chatTitle(chat: ChatItem): string {
  if (chat.kind !== 'dm' || !me.value) {
    return chat.title
  }
  const peer = chat.members.find((x) => x.id !== me.value!.id)
  return peer?.name || peer?.username || chat.title
}

function chatAvatar(chat: ChatItem): string {
  if (chat.kind !== 'dm' || !me.value) {
    return ''
  }
  return chat.members.find((x) => x.id !== me.value!.id)?.avatar || ''
}

function chatStatus(chat: ChatItem): string {
  if (chat.kind === 'group') return `Группа · ${chat.members.length}`
  if (chat.kind === 'channel') return `Канал · ${chat.members.length}`
  if (chat.kind === 'dm' && me.value) {
    const peer = chat.members.find((x) => x.id !== me.value!.id)
    return peer?.online ? 'online' : 'offline'
  }
  return ''
}

function previewText(msg: WsMessage | null): string {
  if (!msg) return 'Пустой чат'
  if (msg.kind === 'file') return 'Файл'
  if (msg.kind === 'voice') return 'Голосовое'
  return msg.txt
}

function isImage(msg: WsMessage): boolean {
  if (msg.kind !== 'file') return false
  return /\.(gif|png|jpe?g|webp)(\?.*)?$/i.test(msg.url || '')
}

function fileLabel(msg: WsMessage): string {
  const nm = (msg.fname || '').trim()
  if (nm) return nm
  const raw = (msg.url || '').trim()
  if (!raw) return 'file'
  try {
    const u = new URL(raw)
    const part = (u.pathname.split('/').pop() || '').trim()
    return part || 'file'
  } catch {
    const part = (raw.split('/').pop() || '').split('?')[0]
    return part || 'file'
  }
}

function setOnline(uid: number, online: boolean): void {
  for (const chat of chats.value) {
    for (const m of chat.members) {
      if (m.id === uid) m.online = online
    }
  }
  if (me.value && me.value.id === uid) me.value.online = online
}

function patchChat(chat: ChatItem): void {
  const idx = chats.value.findIndex((x) => x.id === chat.id)
  if (idx >= 0) {
    chats.value[idx] = chat
  } else {
    chats.value.push(chat)
  }
}

function patchUser(user: UserLite): void {
  if (me.value && me.value.id === user.id) {
    me.value = user
    settingsForm.name = user.name || ''
    settingsForm.username = user.username || ''
    settingsForm.phone = user.phone || ''
    settingsForm.bio = user.bio || ''
    localStorage.setItem('hamster_user', JSON.stringify(user))
  }
  for (const chat of chats.value) {
    for (const m of chat.members) {
      if (m.id === user.id) {
        m.avatar = user.avatar
        m.name = user.name
        m.username = user.username
        m.online = user.online
      }
    }
    if (chat.last && chat.last.uid === user.id) {
      chat.last.avatar = user.avatar
      chat.last.name = user.name
      chat.last.username = user.username
    }
  }
  if (infoUser.value && infoUser.value.id === user.id) {
    infoUser.value = user
  }
}

function addMessage(msg: WsMessage): void {
  const arr = messagesByChat[msg.cid] || []
  if (arr.some((x) => x.id === msg.id)) {
    return
  }
  arr.push(msg)
  arr.sort((a, b) => a.id - b.id)
  messagesByChat[msg.cid] = arr
  const chat = chats.value.find((x) => x.id === msg.cid)
  if (chat) chat.last = msg
  if (activeChatId.value === msg.cid) {
    void scrollToBottom()
  }
}

function resolvePending(pack: WsPacket): boolean {
  const act = (pack.act || '').toString()
  if (!act) return false
  const q = pending.get(act)
  if (!q || !q.length) return false
  const one = q.shift()
  if (!one) return false
  window.clearTimeout(one.timer)
  one.resolve(pack)
  if (!q.length) pending.delete(act)
  return true
}

function rejectAllPending(reason: string): void {
  for (const arr of pending.values()) {
    for (const w of arr) {
      window.clearTimeout(w.timer)
      w.reject(new Error(reason))
    }
  }
  pending.clear()
}

function sendAndWait(payload: Record<string, unknown>, expectAct?: string, timeoutMs = 15000): Promise<WsPacket> {
  if (!ws || ws.readyState !== WebSocket.OPEN) {
    return Promise.reject(new Error('WS closed'))
  }
  const act = (expectAct || payload.act || '').toString()
  if (!act) return Promise.reject(new Error('bad act'))
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => {
      const arr = pending.get(act)
      if (arr) {
        const idx = arr.findIndex((x) => x.resolve === resolve)
        if (idx >= 0) arr.splice(idx, 1)
        if (!arr.length) pending.delete(act)
      }
      reject(new Error(`timeout: ${act}`))
    }, timeoutMs)

    const arr = pending.get(act) || []
    arr.push({ resolve, reject, timer })
    pending.set(act, arr)
    ws!.send(JSON.stringify(payload))
  })
}

function sendNoWait(payload: Record<string, unknown>): void {
  if (!ws || ws.readyState !== WebSocket.OPEN) return
  ws.send(JSON.stringify(payload))
}

async function fetchMe(): Promise<boolean> {
  try {
    const res = await fetch(apiUrl('/me'), {
      headers: { Authorization: `Bearer ${token.value}` },
    })
    const dat = (await res.json()) as { ok?: boolean; user?: UserLite; err?: string }
    if (!res.ok || !dat.ok || !dat.user) {
      socketErr.value = dat.err || 'auth failed'
      return false
    }
    me.value = dat.user
    settingsForm.name = dat.user.name || ''
    settingsForm.username = dat.user.username || ''
    settingsForm.phone = dat.user.phone || ''
    settingsForm.bio = dat.user.bio || ''
    return true
  } catch {
    socketErr.value = 'API недоступен'
    return false
  }
}

async function scrollToBottom(): Promise<void> {
  await nextTick()
  if (messageScroller.value) {
    messageScroller.value.scrollTop = messageScroller.value.scrollHeight
  }
}

async function loadChats(): Promise<void> {
  const res = await sendAndWait({ act: 'get_chats', lim: 150 }, 'get_chats')
  if (!res.ok) throw new Error((res.err || 'get_chats failed').toString())
  chats.value = (res.items as ChatItem[] | undefined) || []
  const first = chats.value[0]
  if (!activeChatId.value && first) {
    await selectChat(first.id)
  }
}

async function loadMessages(cid: number): Promise<void> {
  loadingMessages.value = true
  try {
    const res = await sendAndWait({ act: 'get_msgs', cid, lim: 200 }, 'get_msgs')
    if (!res.ok) throw new Error((res.err || 'get_msgs failed').toString())
    messagesByChat[cid] = ((res.items as WsMessage[] | undefined) || []).sort((a, b) => a.id - b.id)
    await scrollToBottom()
  } finally {
    loadingMessages.value = false
  }
}

async function selectChat(cid: number): Promise<void> {
  infoOpen.value = false
  viewMode.value = 'chats'
  activeChatId.value = cid
  mobilePane.value = 'chat'
  await loadMessages(cid)
}

function openListOnMobile(): void {
  if (!isMobile.value) return
  infoOpen.value = false
  mobilePane.value = 'list'
}

function setViewMode(next: ViewMode): void {
  viewMode.value = next
  if (!isMobile.value) return
  if (next === 'chats') {
    mobilePane.value = activeChatId.value > 0 ? 'chat' : 'list'
    return
  }
  mobilePane.value = 'list'
}

async function sendText(): Promise<void> {
  const txt = draft.value.trim()
  if (!txt || !activeChatId.value) return
  if (!canWrite.value) {
    setToast('В этот чат нельзя писать')
    return
  }
  draft.value = ''
  const res = await sendAndWait({ act: 'send_msg', cid: activeChatId.value, txt }, 'send_msg')
  if (!res.ok) setToast((res.err || 'Ошибка отправки').toString())
}

async function uploadOnlySq(file: File): Promise<string> {
  const fd = new FormData()
  fd.append('file', file)
  const res = await fetch(CLOUD_UPLOAD, { method: 'POST', body: fd })
  const dat = (await res.json()) as { ok?: boolean; url?: string }
  if (!res.ok || !dat.ok || !dat.url) throw new Error('cloud upload fail')
  return dat.url
}

async function pickFile(ev: Event): Promise<void> {
  const inp = ev.target as HTMLInputElement
  const one = inp.files?.[0]
  inp.value = ''
  if (!one || !activeChatId.value) return
  if (!canWrite.value) {
    setToast('В этот чат нельзя писать')
    return
  }
  try {
    const url = await uploadOnlySq(one)
    const res = await sendAndWait({ act: 'send_msg', cid: activeChatId.value, kind: 'file', url, fname: one.name }, 'send_msg')
    if (!res.ok) setToast((res.err || 'Файл не отправлен').toString())
  } catch {
    setToast('Ошибка загрузки в OnlySq Cloud')
  }
}

async function deleteChatSelf(cid: number): Promise<void> {
  if (!confirm('Удалить чат?')) return
  const res = await sendAndWait({ act: 'chat_delself', cid }, 'chat_delself')
  if (!res.ok) {
    setToast((res.err || 'Не удалось удалить чат').toString())
  }
}

function onChatContextMenu(e: MouseEvent, chat: ChatItem): void {
  e.preventDefault()
  void deleteChatSelf(chat.id)
}

function canKick(memberId: number): boolean {
  if (!me.value || !infoChat.value) return false
  return intEq(infoChat.value.own, me.value.id) && !intEq(memberId, me.value.id)
}

function intEq(a: number, b: number): boolean {
  return Number(a) === Number(b)
}

async function kickMember(memberId: number): Promise<void> {
  if (!infoChat.value || !canKick(memberId)) return
  if (!confirm('Кикнуть участника из чата?')) return
  const res = await sendAndWait({ act: 'chat_kick', cid: infoChat.value.id, uid: memberId }, 'chat_kick')
  if (!res.ok) {
    setToast((res.err || 'Не удалось кикнуть').toString())
    return
  }
  setToast('Участник удален')
}

function onMemberContextMenu(e: MouseEvent, member: ChatMember): void {
  e.preventDefault()
  void kickMember(member.id)
}

async function pickAvatar(ev: Event): Promise<void> {
  const inp = ev.target as HTMLInputElement
  const one = inp.files?.[0]
  inp.value = ''
  if (!one) return
  const fd = new FormData()
  fd.append('avatar', one)
  try {
    const res = await fetch(apiUrl('/avatar/upload'), {
      method: 'POST',
      headers: { Authorization: `Bearer ${token.value}` },
      body: fd,
    })
    const dat = (await res.json()) as { ok?: boolean; user?: UserLite; err?: string }
    if (!res.ok || !dat.ok || !dat.user) {
      setToast(dat.err || 'Не удалось обновить аватар')
      return
    }
    patchUser(dat.user)
  } catch {
    setToast('Ошибка загрузки аватара')
  }
}

async function searchUsersByText(q: string): Promise<void> {
  const val = q.trim()
  if (val.length < 2 || !ws || ws.readyState !== WebSocket.OPEN) {
    searchUsersRes.value = []
    return
  }
  searchingUsers.value = true
  try {
    const res = await sendAndWait({ act: 'search_users', q: val, lim: 20 }, 'search_users')
    searchUsersRes.value = (res.items as UserLite[] | undefined) || []
  } finally {
    searchingUsers.value = false
  }
}

async function openDm(user: UserLite): Promise<void> {
  const res = await sendAndWait({ act: 'open_dm', to: user.username }, 'open_dm')
  if (!res.ok || !res.chat) {
    setToast((res.err || 'Не удалось открыть чат').toString())
    return
  }
  const chat = res.chat as ChatItem
  patchChat(chat)
  await selectChat(chat.id)
}

function openCreate(kind: 'group' | 'channel'): void {
  createMenuOpen.value = false
  createModal.open = true
  createModal.kind = kind
  createModal.title = ''
  createModal.members = ''
}

async function createChatSubmit(): Promise<void> {
  const ttl = createModal.title.trim()
  if (!ttl) {
    setToast('Нужно название')
    return
  }
  createModal.busy = true
  try {
    const members = createModal.members
      .split(',')
      .map((x) => x.trim())
      .filter(Boolean)
    const res = await sendAndWait({ act: 'create_chat', title: ttl, kind: createModal.kind, members }, 'create_chat')
    if (!res.ok || !res.chat) {
      setToast((res.err || 'Не удалось создать чат').toString())
      return
    }
    const chat = res.chat as ChatItem
    patchChat(chat)
    createModal.open = false
    await selectChat(chat.id)
  } finally {
    createModal.busy = false
  }
}

function openInfo(): void {
  const chat = activeChat.value
  if (!chat) return
  mobilePane.value = 'chat'
  infoOpen.value = true
  if (chat.kind === 'dm' && activePeer.value) {
    infoMode.value = 'user'
    infoUser.value = {
      id: activePeer.value.id,
      username: activePeer.value.username,
      name: activePeer.value.name,
      email: '',
      avatar: activePeer.value.avatar,
      phone: '',
      bio: '',
      online: activePeer.value.online,
    }
    infoChat.value = null
  } else {
    infoMode.value = 'chat'
    infoChat.value = chat
    infoUser.value = null
  }
}

async function saveSettings(): Promise<void> {
  settingsBusy.value = true
  try {
    const res = await fetch(apiUrl('/profile'), {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token.value}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        name: settingsForm.name.trim(),
        username: settingsForm.username.trim().toLowerCase(),
        phone: settingsForm.phone.trim(),
        bio: settingsForm.bio.trim(),
      }),
    })
    const dat = (await res.json()) as { ok?: boolean; user?: UserLite; err?: string }
    if (!res.ok || !dat.ok || !dat.user) {
      setToast(dat.err || 'Не удалось сохранить профиль')
      return
    }
    patchUser(dat.user)
    setToast('Профиль обновлен')
  } finally {
    settingsBusy.value = false
  }
}

async function loadCallHistory(): Promise<void> {
  loadingCallHistory.value = true
  try {
    const res = await sendAndWait({ act: 'call_hist', lim: 100 }, 'call_hist')
    callHistory.value = (res.items as CallHistory[] | undefined) || []
  } finally {
    loadingCallHistory.value = false
  }
}

function callStatusText(st: string): string {
  if (st === 'ended') return 'Завершен'
  if (st === 'rejected') return 'Отклонен'
  if (st === 'missed') return 'Пропущен'
  if (st === 'talk') return 'Разговор'
  return 'Ожидание'
}

function ensurePopup(): void {
  if (callPopup && !callPopup.closed) return
  callPopup = window.open('', 'hamster_call_window', 'width=980,height=700,resizable=yes')
  if (!callPopup) {
    setToast('Браузер блокирует окно звонка')
    return
  }
  callPopup.document.write(`
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8"/>
<title>Homyak Call</title>
<style>
body{margin:0;background:#0a1020;color:#f4f7ff;font:16px Segoe UI,sans-serif}
.top{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-bottom:1px solid #304777}
.videos{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:12px}
video{width:100%;aspect-ratio:16/10;background:#02050c;border-radius:10px;border:1px solid #314977;object-fit:cover}
.controls{display:flex;gap:8px;padding:0 12px 12px}
button{border:0;border-radius:8px;padding:10px 14px;background:#18468f;color:#fff;cursor:pointer}
button.end{background:#b5385d}
</style>
</head>
<body>
  <div class="top"><strong>Звонок Homyak</strong><span id="status">Подключение...</span></div>
  <div class="videos">
    <video id="local-video" autoplay muted playsinline></video>
    <video id="remote-video" autoplay playsinline></video>
  </div>
  <div class="controls">
    <button id="mic-btn">🎙 Микрофон</button>
    <button id="cam-btn">📷 Камера</button>
    <button id="end-btn" class="end">⛔ Завершить</button>
  </div>
</body>
</html>`)
  callPopup.document.close()
  popupLocalVideo = callPopup.document.getElementById('local-video') as HTMLVideoElement | null
  popupRemoteVideo = callPopup.document.getElementById('remote-video') as HTMLVideoElement | null
  popupStatus = callPopup.document.getElementById('status')
  popupMicBtn = callPopup.document.getElementById('mic-btn') as HTMLButtonElement | null
  popupCamBtn = callPopup.document.getElementById('cam-btn') as HTMLButtonElement | null
  const endBtn = callPopup.document.getElementById('end-btn') as HTMLButtonElement | null
  if (popupMicBtn) popupMicBtn.onclick = () => window.postMessage({ act: 'call_toggle_mic' }, '*')
  if (popupCamBtn) popupCamBtn.onclick = () => window.postMessage({ act: 'call_toggle_cam' }, '*')
  if (endBtn) endBtn.onclick = () => window.postMessage({ act: 'call_end_req' }, '*')
}

function updatePopupUi(): void {
  if (popupStatus) popupStatus.textContent = call.note || call.status
  if (popupMicBtn) popupMicBtn.textContent = call.micMuted ? '🔇 Микро выкл' : '🎙 Микро вкл'
  if (popupCamBtn) popupCamBtn.textContent = call.camOff ? '📷 Камера выкл' : '📹 Камера вкл'
}

function hydrateMedia(): void {
  if (hiddenLocalVideo.value) hiddenLocalVideo.value.srcObject = localStream
  if (hiddenRemoteVideo.value) hiddenRemoteVideo.value.srcObject = remoteStream
  if (hiddenRemoteAudio.value) hiddenRemoteAudio.value.srcObject = remoteStream
  if (popupLocalVideo) popupLocalVideo.srcObject = localStream
  if (popupRemoteVideo) popupRemoteVideo.srcObject = remoteStream
  updatePopupUi()
}

function toggleMic(): void {
  if (!localStream) return
  const tracks = localStream.getAudioTracks()
  if (!tracks.length) return
  const next = !call.micMuted
  for (const t of tracks) t.enabled = !next
  call.micMuted = next
  updatePopupUi()
}

function toggleCamera(): void {
  if (!localStream) return
  const tracks = localStream.getVideoTracks()
  if (!tracks.length) {
    setToast('Камера не подключена, звонок идет по аудио')
    return
  }
  const next = !call.camOff
  for (const t of tracks) t.enabled = !next
  call.camOff = next
  updatePopupUi()
}

async function ensureMedia(): Promise<void> {
  if (localStream) {
    for (const t of localStream.getTracks()) t.stop()
  }
  try {
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true })
    call.camOff = false
  } catch {
    localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
    call.camOff = true
  }
  call.micMuted = false
  hydrateMedia()
}

function ensurePeer(): void {
  if (pc) return
  remoteStream = new MediaStream()
  pc = new RTCPeerConnection({
    iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
  })
  pc.ontrack = (ev) => {
    if (!remoteStream) remoteStream = new MediaStream()
    for (const t of ev.streams[0]?.getTracks() || [ev.track]) {
      if (!remoteStream.getTracks().some((x) => x.id === t.id)) remoteStream.addTrack(t)
    }
    hydrateMedia()
  }
  pc.onicecandidate = (ev) => {
    if (!ev.candidate || !call.cid) return
    sendNoWait({
      act: 'call_ice',
      cid: call.cid,
      ice: {
        candidate: ev.candidate.candidate,
        sdpMid: ev.candidate.sdpMid,
        sdpMLineIndex: ev.candidate.sdpMLineIndex,
      },
    })
  }
}

function stopWebrtc(stopTracks = true): void {
  if (pc) {
    pc.ontrack = null
    pc.onicecandidate = null
    pc.onconnectionstatechange = null
    void pc.close()
    pc = null
  }
  if (stopTracks && localStream) {
    for (const t of localStream.getTracks()) t.stop()
    localStream = null
  }
  if (remoteStream) {
    for (const t of remoteStream.getTracks()) t.stop()
    remoteStream = null
  }
  call.micMuted = false
  call.camOff = false
  hydrateMedia()
}

async function startWebrtc(): Promise<void> {
  if (!call.cid) return
  try {
    ensurePopup()
    ensurePeer()
    await ensureMedia()
    if (!pc || !localStream) return
    for (const t of localStream.getTracks()) {
      pc.addTrack(t, localStream)
    }
    const offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    const ans = await sendAndWait({ act: 'call_offer', cid: call.cid, sdp: offer.sdp, type: offer.type }, 'call_ans', 25000)
    if (!ans.ok || !ans.sdp || !ans.type) throw new Error((ans.err || 'Ошибка SDP').toString())
    await pc.setRemoteDescription(new RTCSessionDescription({ sdp: String(ans.sdp), type: String(ans.type) as RTCSdpType }))
    call.status = 'talk'
    call.note = 'Соединение установлено'
    hydrateMedia()
  } catch (e) {
    call.status = 'error'
    call.note = e instanceof Error ? e.message : 'Ошибка звонка'
    updatePopupUi()
  }
}

async function startCall(): Promise<void> {
  const chat = activeChat.value
  if (!chat || chat.kind !== 'dm') {
    setToast('Звонки только в личных чатах')
    return
  }
  const res = await sendAndWait({ act: 'call_start', cid: chat.id }, 'call_start')
  if (!res.ok) {
    setToast((res.err || 'Не удалось начать звонок').toString())
    return
  }
  call.cid = String(res.cid || '')
  call.chat = Number(res.chat || chat.id)
  call.status = 'ringing'
  call.note = 'Ждем ответ...'
  ensurePopup()
  updatePopupUi()
}

async function acceptCall(): Promise<void> {
  if (!incomingCall.value) return
  call.cid = incomingCall.value.cid
  call.chat = incomingCall.value.chat
  incomingCall.value = null
  const res = await sendAndWait({ act: 'call_acc', cid: call.cid }, 'call_acc')
  if (!res.ok) {
    call.status = 'error'
    call.note = (res.err || 'Ошибка принятия').toString()
    return
  }
  call.status = 'ringing'
  call.note = 'Подключаемся...'
  ensurePopup()
  updatePopupUi()
}

async function rejectCall(): Promise<void> {
  if (!incomingCall.value) return
  const cid = incomingCall.value.cid
  incomingCall.value = null
  await sendAndWait({ act: 'call_rej', cid }, 'call_rej').catch(() => null)
}

async function endCall(): Promise<void> {
  if (call.cid) {
    await sendAndWait({ act: 'call_end', cid: call.cid }, 'call_end').catch(() => null)
  }
  stopWebrtc(true)
  call.cid = ''
  call.chat = 0
  call.status = 'idle'
  call.note = ''
  if (callPopup && !callPopup.closed) callPopup.close()
  callPopup = null
  popupLocalVideo = null
  popupRemoteVideo = null
  popupStatus = null
  popupMicBtn = null
  popupCamBtn = null
  if (viewMode.value === 'calls') await loadCallHistory().catch(() => null)
}

async function connectWs(): Promise<void> {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  ws = new WebSocket(wsUrl())
  ws.onopen = async () => {
    connected.value = true
    socketErr.value = ''
    try {
      const auth = await sendAndWait({ act: 'auth', token: token.value }, 'auth')
      if (!auth.ok) throw new Error((auth.err || 'auth failed').toString())
      await loadChats()
    } catch {
      clearAuthAndBack()
    }
  }
  ws.onmessage = async (ev: MessageEvent) => {
    let pack: WsPacket = {}
    try {
      pack = JSON.parse(ev.data as string) as WsPacket
    } catch {
      return
    }
    if (resolvePending(pack)) return
    const act = (pack.act || '').toString()

    if (act === 'msg' && pack.ok && pack.msg) {
      addMessage(pack.msg as WsMessage)
      return
    }
    if ((act === 'chat_new' || act === 'chat_upd' || act === 'chat_recent') && pack.ok && pack.chat) {
      patchChat(pack.chat as ChatItem)
      return
    }
    if (act === 'chat_del' && pack.ok && typeof pack.cid === 'number') {
      chats.value = chats.value.filter((x) => x.id !== pack.cid)
      delete messagesByChat[pack.cid]
      if (activeChatId.value === pack.cid) activeChatId.value = 0
      return
    }
    if (act === 'user_upd' && pack.ok && pack.user) {
      patchUser(pack.user as UserLite)
      return
    }
    if (act === 'presence' && pack.ok) {
      setOnline(Number(pack.uid || 0), Boolean(pack.online))
      return
    }
    if (act === 'presence_bulk' && pack.ok) {
      const ids = new Set(((pack.uids as number[] | undefined) || []).map((x) => Number(x)))
      for (const chat of chats.value) {
        for (const m of chat.members) m.online = ids.has(m.id)
      }
      if (me.value) me.value.online = ids.has(me.value.id)
      return
    }
    if (act === 'call_in' && pack.ok) {
      incomingCall.value = {
        cid: String(pack.cid || ''),
        chat: Number(pack.chat || 0),
        from: (pack.from || { id: 0, username: '', name: '' }) as { id: number; username: string; name: string },
      }
      return
    }
    if (act === 'call_ring' && pack.ok) {
      call.cid = String(pack.cid || '')
      call.chat = Number(pack.chat || 0)
      call.status = 'ringing'
      call.note = 'Ожидание ответа'
      ensurePopup()
      updatePopupUi()
      return
    }
    if (act === 'call_go' && pack.ok) {
      if (!call.cid) call.cid = String(pack.cid || '')
      call.status = 'talk'
      call.note = 'Звонок активен'
      await startWebrtc()
      return
    }
    if (act === 'call_stop' && pack.ok) {
      stopWebrtc(true)
      call.cid = ''
      call.chat = 0
      call.status = 'idle'
      call.note = ''
      if (callPopup && !callPopup.closed) callPopup.close()
      callPopup = null
      popupLocalVideo = null
      popupRemoteVideo = null
      popupStatus = null
      popupMicBtn = null
      popupCamBtn = null
      if (viewMode.value === 'calls') await loadCallHistory().catch(() => null)
      return
    }
  }
  ws.onclose = () => {
    connected.value = false
    rejectAllPending('ws closed')
    if (!manualWsClose) {
      reconnectTimer = window.setTimeout(() => void connectWs(), 1800)
    }
  }
  ws.onerror = () => {
    socketErr.value = 'Ошибка WS'
  }
}

async function logout(): Promise<void> {
  await endCall().catch(() => null)
  clearAuthAndBack()
}

function onWindowMessage(ev: MessageEvent): void {
  if (!ev.data || typeof ev.data !== 'object') return
  if (ev.data.act === 'call_end_req') void endCall()
  if (ev.data.act === 'call_toggle_mic') toggleMic()
  if (ev.data.act === 'call_toggle_cam') toggleCamera()
}

function syncMobileLayout(): void {
  if (typeof window === 'undefined') return
  const mobile = window.matchMedia('(max-width: 860px)').matches
  isMobile.value = mobile
  if (!mobile) {
    mobilePane.value = 'list'
    return
  }
  if (viewMode.value !== 'chats') {
    mobilePane.value = 'list'
    return
  }
  if (!activeChatId.value) {
    mobilePane.value = 'list'
  }
}

watch(search, (v) => void searchUsersByText(v))
watch(activeMessages, () => void scrollToBottom())
watch(viewMode, async (v) => {
  syncMobileLayout()
  if (v === 'calls') await loadCallHistory().catch(() => null)
})
watch(activeChatId, () => {
  if (!isMobile.value || viewMode.value !== 'chats') return
  if (activeChatId.value <= 0) {
    mobilePane.value = 'list'
  }
})
watch(
  () => `${call.status}:${call.note}:${call.micMuted}:${call.camOff}`,
  () => updatePopupUi(),
)
watch(hiddenLocalVideo, hydrateMedia)
watch(hiddenRemoteVideo, hydrateMedia)
watch(hiddenRemoteAudio, hydrateMedia)

onMounted(async () => {
  syncMobileLayout()
  mobileMql = window.matchMedia('(max-width: 860px)')
  mobileMql.addEventListener('change', syncMobileLayout)
  token.value = localStorage.getItem('hamster_token') || ''
  if (!token.value) {
    void router.push('/')
    return
  }
  const ok = await fetchMe()
  if (!ok) {
    clearAuthAndBack()
    return
  }
  window.addEventListener('message', onWindowMessage)
  await connectWs()
})

onBeforeUnmount(() => {
  window.removeEventListener('message', onWindowMessage)
  if (mobileMql) {
    mobileMql.removeEventListener('change', syncMobileLayout)
    mobileMql = null
  }
  manualWsClose = true
  if (reconnectTimer) window.clearTimeout(reconnectTimer)
  rejectAllPending('unmount')
  if (ws) ws.close()
  stopWebrtc(true)
  if (callPopup && !callPopup.closed) callPopup.close()
})
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
        <Settings class="ico" /> <span>Настройки</span>
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

            <label>Имя
              <input v-model="settingsForm.name" type="text" />
            </label>
            <label>Username
              <input v-model="settingsForm.username" type="text" />
            </label>
            <label>Телефон
              <input v-model="settingsForm.phone" type="text" />
            </label>
            <label>О себе
              <textarea v-model="settingsForm.bio" rows="4"></textarea>
            </label>
            <button type="button" class="save" :disabled="settingsBusy" @click="saveSettings">
              <Shield class="ico" /> {{ settingsBusy ? 'Сохраняем...' : 'Сохранить' }}
            </button>
            <button type="button" class="logout settings-logout" @click="logout">
              <LogOut class="ico" /> Выйти
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
                <button type="button" @click="startCall"><Phone class="ico" /> Звонок</button>
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
              <button type="button" class="act-btn" @click="startCall"><Phone class="ico" /> Звонок</button>
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
        <label>Название
          <input v-model="createModal.title" type="text" />
        </label>
        <label>Участники (username через запятую)
          <input v-model="createModal.members" type="text" placeholder="ivan,olga,max" />
        </label>
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
@import url('https://fonts.googleapis.com/css2?family=Exo+2:wght@400;600;700&display=swap');

:global(*) {
  box-sizing: border-box;
}

:global(html),
:global(body),
:global(#app) {
  margin: 0;
  height: 100%;
  min-height: 100%;
}

:global(body) {
  overflow: hidden;
  color: #ecf4ff;
  font-family: 'Exo 2', 'Segoe UI', sans-serif;
  background:
    radial-gradient(circle at 16% 14%, rgba(36, 93, 205, 0.2), transparent 30%),
    #080d1a;
}

.layout {
  position: fixed;
  inset: 0;
  height: auto;
  min-height: 0;
  display: grid;
  grid-template-columns: 112px 440px 1fr;
  background:
    radial-gradient(circle, rgba(95, 130, 214, 0.12) 1px, transparent 1px),
    linear-gradient(140deg, rgba(8, 12, 25, 0.95), rgba(8, 12, 25, 0.9));
  background-size: 24px 24px, 100% 100%;
}

.ico {
  width: 18px;
  height: 18px;
  flex: 0 0 18px;
}

.rail {
  border-right: 1px solid rgba(72, 96, 145, 0.5);
  background: #0e1428;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 8px;
}

.logo {
  width: 56px;
  height: 56px;
  margin: 0 auto 10px;
  border: 1px solid rgba(103, 136, 213, 0.65);
  overflow: hidden;
}

.logo img {
  width: 100%;
  height: 100%;
  object-fit: contain;
}

.rail button {
  border: 0;
  background: #1a2f5d;
  color: #e7f0ff;
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  padding: 0 12px;
  cursor: pointer;
}

.rail button.active {
  background: #2b56ae;
}

.rail .logout {
  margin-top: auto;
  background: #57254a;
}

.left {
  border-right: 1px solid rgba(72, 96, 145, 0.5);
  background: rgba(9, 15, 29, 0.9);
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  min-height: 0;
}

.left-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.left-head h1 {
  margin: 0;
  font-size: 50px;
  line-height: 1;
}

.plus {
  border: 0;
  background: #1778ff;
  color: #fff;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.create-menu {
  border: 1px solid #35528c;
  background: #121e39;
}

.create-menu button {
  width: 100%;
  border: 0;
  background: transparent;
  color: #eff5ff;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px;
  cursor: pointer;
}

.search-wrap {
  border: 1px solid #36518a;
  background: #111c36;
  display: grid;
  grid-template-columns: 20px 1fr;
  gap: 8px;
  align-items: center;
  padding: 9px 10px;
}

.search-wrap input {
  width: 100%;
  border: 0;
  background: transparent;
  color: #edf4ff;
}

.user-result-list {
  border: 1px solid #2b426f;
  background: #111c36;
  max-height: 230px;
  overflow: auto;
}

.user-result {
  width: 100%;
  border: 0;
  border-bottom: 1px solid #253b64;
  background: transparent;
  color: #e9f2ff;
  display: grid;
  grid-template-columns: 36px 1fr;
  gap: 8px;
  padding: 8px;
  text-align: left;
  cursor: pointer;
}

.mini-avatar {
  width: 36px;
  height: 36px;
  background: #355795;
  display: grid;
  place-items: center;
}

.mini-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.u-meta small {
  color: #abc0e8;
}

.chat-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding-bottom: 0;
}

.chat-row {
  width: 100%;
  border: 1px solid transparent;
  background: rgba(27, 42, 78, 0.62);
  color: #edf3ff;
  display: grid;
  grid-template-columns: 50px 1fr auto;
  gap: 10px;
  padding: 10px;
  text-align: left;
  cursor: pointer;
}

.chat-row.active {
  border-color: #7198ef;
}

.avatar {
  width: 50px;
  height: 50px;
  background: #3a5d9e;
  display: grid;
  place-items: center;
}

.avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.meta {
  min-width: 0;
}

.meta strong,
.meta small {
  display: block;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta small {
  color: #b3c6ed;
}

.r-meta {
  text-align: right;
  color: #9ab2e1;
  font-size: 12px;
}

.content {
  min-height: 0;
  display: flex;
  flex-direction: column;
  background: rgba(8, 12, 24, 0.74);
}

.title-line {
  height: 64px;
  border-bottom: 1px solid rgba(72, 96, 145, 0.5);
  display: flex;
  align-items: center;
  padding: 0 16px;
  font-size: 24px;
  font-weight: 700;
}

.chat-head {
  height: 70px;
  border-bottom: 1px solid rgba(72, 96, 145, 0.5);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px;
}

.back-chat-list {
  border: 0;
  background: #223f74;
  color: #fff;
  width: 34px;
  height: 34px;
  cursor: pointer;
}

.peer {
  border: 0;
  background: transparent;
  color: #ecf4ff;
  text-align: left;
  cursor: pointer;
}

.peer strong {
  display: block;
  font-size: 36px;
  line-height: 1;
}

.peer small {
  color: #8fd0ff;
}

.head-actions {
  display: flex;
  gap: 8px;
}

.act-btn {
  border: 0;
  background: #1f7cff;
  color: #fff;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  cursor: pointer;
}

.act-btn input {
  display: none;
}

.messages-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 12px;
  align-items: flex-start;
  padding: 14px;
}

.msg {
  max-width: min(68%, 700px);
  background: #2d457c;
  border: 1px solid #6288d9;
  padding: 10px 12px;
  width: auto;
}

.msg.mine {
  align-self: flex-end;
  background: #2a5bb8;
}

.msg header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 6px;
}

.msg p {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.msg-image {
  max-width: 320px;
  width: auto;
  height: auto;
  object-fit: contain;
}

.file-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}

.file-name {
  color: #d8e6ff;
  text-decoration: underline;
  word-break: break-word;
}

.dl-btn {
  border: 1px solid #5f84d5;
  background: #1f5ec8;
  color: #fff;
  text-decoration: none;
  padding: 6px 12px;
}

.composer {
  height: 62px;
  border-top: 1px solid rgba(72, 96, 145, 0.5);
  padding: 8px;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
}

.composer input {
  border: 1px solid #37528e;
  background: #111c36;
  color: #eff5ff;
  padding: 10px;
}

.composer button {
  border: 0;
  background: #177cff;
  color: #fff;
  padding: 0 14px;
  cursor: pointer;
}

.calls-scroll,
.settings-scroll,
.info-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: 14px;
}

.call-card {
  border: 1px solid #335083;
  background: #14203d;
  padding: 10px;
  margin-bottom: 8px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.settings-box,
.info-card {
  max-width: 860px;
  margin: 0 auto;
  border: 1px solid #35518a;
  background: #121d38;
  padding: 18px;
}

.settings-box {
  display: grid;
  gap: 10px;
}

.big-avatar,
.info-avatar {
  width: 120px;
  height: 120px;
  margin: 0 auto 14px;
  position: relative;
  background: #3a5e9f;
  display: grid;
  place-items: center;
}

.big-avatar img,
.info-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.fallback {
  font-size: 44px;
}

.pick-avatar {
  position: absolute;
  right: -8px;
  bottom: -8px;
  width: 34px;
  height: 34px;
  background: #1984ff;
  display: grid;
  place-items: center;
  cursor: pointer;
}

.pick-avatar input {
  display: none;
}

.settings-box label {
  display: grid;
  gap: 6px;
  margin-bottom: 10px;
}

.settings-box input,
.settings-box textarea {
  border: 1px solid #36528e;
  background: #101a31;
  color: #eff5ff;
  padding: 10px;
}

.save {
  border: 0;
  background: #2367d1;
  color: #fff;
  padding: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  cursor: pointer;
}

.settings-logout {
  margin-top: 2px;
  justify-content: center;
}

.desktop-only {
  display: flex;
}

.info-line {
  justify-content: flex-start;
  gap: 12px;
}

.back-btn {
  border: 0;
  background: #243f74;
  color: #fff;
  padding: 8px 12px;
  cursor: pointer;
}

.info-card h2,
.info-card p {
  text-align: center;
}

.info-actions {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-top: 16px;
}

.info-actions button {
  border: 0;
  background: #26334f;
  color: #d8e7ff;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  align-items: center;
  cursor: pointer;
}

.members {
  margin-top: 12px;
  border-top: 1px solid #2d426f;
  padding-top: 12px;
}

.member-row {
  display: flex;
  justify-content: space-between;
  padding: 6px 0;
}

.member-row.kickable {
  cursor: context-menu;
}

.member-row.kickable:hover {
  color: #ffccd8;
}

.empty {
  flex: 1;
  display: grid;
  place-items: center;
}

.empty img {
  width: 88px;
  height: 88px;
  object-fit: contain;
}

.overlay {
  position: fixed;
  inset: 0;
  background: rgba(3, 8, 18, 0.7);
  display: grid;
  place-items: center;
  z-index: 100;
}

.modal {
  width: min(560px, calc(100% - 24px));
  border: 1px solid #4968aa;
  background: #121e39;
  padding: 16px;
  display: grid;
  gap: 10px;
}

.modal input {
  width: 100%;
  border: 1px solid #3a548c;
  background: #111b33;
  color: #eff5ff;
  padding: 10px;
}

.modal button {
  border: 0;
  background: #1f7eff;
  color: #fff;
  padding: 10px;
  cursor: pointer;
}

.call-row {
  display: flex;
  gap: 8px;
}

.call-row .good {
  background: #0f9563;
}

.call-row .bad {
  background: #be3a61;
}

.hint {
  color: #9eb8ea;
}

.toast {
  position: fixed;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  border: 1px solid #6e93de;
  background: #1b3368;
  color: #ecf4ff;
  padding: 8px 12px;
  z-index: 120;
}

.toast.warn {
  background: #5c2030;
  border-color: #cb6a89;
}

.hidden-media {
  width: 0;
  height: 0;
  overflow: hidden;
}

@media (max-width: 1024px) {
  .layout {
    grid-template-columns: 96px 380px 1fr;
  }

  .left-head h1 {
    font-size: 44px;
  }

  .peer strong {
    font-size: 30px;
  }
}

@media (max-width: 860px) {
  .layout {
    position: fixed;
    inset: 0;
    grid-template-columns: 1fr;
    grid-template-rows: 1fr;
    padding-bottom: calc(66px + env(safe-area-inset-bottom));
  }

  .rail {
    display: none;
  }

  .left,
  .content {
    border-right: 0;
    min-height: 0;
    height: 100%;
  }

  .left {
    padding: 12px;
    gap: 8px;
  }

  .left-head h1 {
    font-size: 44px;
  }

  .chat-row {
    grid-template-columns: 46px 1fr auto;
    padding: 8px;
  }

  .avatar {
    width: 46px;
    height: 46px;
  }

  .chat-head {
    height: 64px;
    gap: 8px;
  }

  .peer strong {
    font-size: 28px;
  }

  .head-actions {
    gap: 6px;
  }

  .act-btn {
    padding: 8px 10px;
    font-size: 13px;
  }

  .messages-scroll,
  .calls-scroll,
  .settings-scroll,
  .info-scroll {
    padding: 12px;
  }

  .settings-box,
  .info-card {
    max-width: none;
    width: 100%;
  }

  .msg {
    max-width: min(90%, 560px);
  }

  .composer {
    height: 58px;
  }

  .desktop-only {
    display: none !important;
  }

  .toast {
    bottom: calc(76px + env(safe-area-inset-bottom));
  }
}
</style>

