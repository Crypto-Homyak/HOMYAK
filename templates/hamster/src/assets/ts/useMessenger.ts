import { computed, nextTick, onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import chatsGif from '@/assets/icons/chats.gif'
import halrGif from '@/assets/icons/halr.gif'
import type { ChatItem, UserLite, WsMessage, ViewMode } from './mestypes'
import {
  viewMode, isMobile, mobilePane, me, connected, socketErr, toast,
  chats, activeChatId, messagesByChat, draft, search, searchUsersRes,
  searchingUsers, loadingMessages, messageScroller,
  createMenuOpen, createModal, settingsForm, settingsBusy,
  infoOpen, infoMode, infoUser, infoChat,
  callHistory, loadingCallHistory, call, incomingCall,
  hiddenLocalVideo, hiddenRemoteVideo, hiddenRemoteAudio,
  wsState, token,
} from './messtate'
import { useWs } from './useWs'
import { useCall } from './useCall'

const CLOUD_UPLOAD = 'https://cloud.onlysq.ru/upload'
const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined)?.trim() || 'https://cryptohomyak.team/api').replace(/\/$/, '')

function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export function useMessenger() {
  const router = useRouter()

  const {
    sendAndWait, sendNoWait, rejectAllPending,
    connectWs, fetchMe, patchChat, patchUser, addMessage,
  } = useWs()

  const {
    playRing, stopRing,
    ensurePopup, updatePopupUi, closePopup,
    hydrateMedia, toggleMic, toggleCamera,
    stopWebrtc, startWebrtc,
    loadCallHistory, startCall, acceptCall, rejectCall, endCall,
    callStatusText,
  } = useCall({ sendAndWait, sendNoWait, setToast, clearAuthAndBack })

  let toastTimer = 0

  function setToast(text: string): void {
    toast.value = text
    if (toastTimer) window.clearTimeout(toastTimer)
    toastTimer = window.setTimeout(() => { toast.value = '' }, 2600)
  }

  function clearAuthAndBack(): void {
    localStorage.removeItem('hamster_token')
    localStorage.removeItem('hamster_user')
    wsState.manualWsClose = true
    if (wsState.ws) wsState.ws.close()
    void router.push('/')
  }

  const activeChat = computed(() => chats.value.find((x) => x.id === activeChatId.value) || null)
  const canWrite = computed(() => Boolean(activeChat.value?.can_w))
  const activeMessages = computed(() => {
    if (activeChatId.value <= 0) return []
    return messagesByChat[activeChatId.value] || []
  })
  const activePeer = computed(() => {
    if (!activeChat.value || !me.value || activeChat.value.kind !== 'dm') return null
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
    if (!q) return sorted
    return sorted.filter((x) => {
      const t = chatTitle(x).toLowerCase()
      const p = (x.last?.txt || '').toLowerCase()
      return t.includes(q) || p.includes(q)
    })
  })

  function fmtTime(ts: string | null): string {
    if (!ts) return ''
    return new Date(ts).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })
  }

  function fmtDateTime(ts: string | null): string {
    if (!ts) return ''
    return new Date(ts).toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' })
  }

  function avatarText(name: string): string {
    return (name.trim().slice(0, 1) || '?').toUpperCase()
  }

  function chatTitle(chat: ChatItem): string {
    if (chat.kind !== 'dm' || !me.value) return chat.title
    const peer = chat.members.find((x) => x.id !== me.value!.id)
    return peer?.name || peer?.username || chat.title
  }

  function chatAvatar(chat: ChatItem): string {
    if (chat.kind !== 'dm' || !me.value) return ''
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
      return (u.pathname.split('/').pop() || '').trim() || 'file'
    } catch {
      return (raw.split('/').pop() || '').split('?')[0] || 'file'
    }
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

  function openListOnMobile(): void {
    if (!isMobile.value) return
    infoOpen.value = false
    mobilePane.value = 'list'
  }

  function syncMobileLayout(): void {
    if (typeof window === 'undefined') return
    const mobile = window.matchMedia('(max-width: 860px)').matches
    isMobile.value = mobile
    if (!mobile) { mobilePane.value = 'list'; return }
    if (viewMode.value !== 'chats') { mobilePane.value = 'list'; return }
    if (!activeChatId.value) mobilePane.value = 'list'
  }

  async function scrollToBottom(): Promise<void> {
    await nextTick()
    if (messageScroller.value) messageScroller.value.scrollTop = messageScroller.value.scrollHeight
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

  async function loadChats(): Promise<void> {
    const res = await sendAndWait({ act: 'get_chats', lim: 150 }, 'get_chats')
    if (!res.ok) throw new Error((res.err || 'get_chats failed').toString())
    chats.value = (res.items as ChatItem[] | undefined) || []
    const first = chats.value[0]
    if (!activeChatId.value && first) await selectChat(first.id)
  }

  async function sendText(): Promise<void> {
    const txt = draft.value.trim()
    if (!txt || !activeChatId.value) return
    if (!canWrite.value) { setToast('В этот чат нельзя писать'); return }
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
    if (!canWrite.value) { setToast('В этот чат нельзя писать'); return }
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
    if (!res.ok) setToast((res.err || 'Не удалось удалить чат').toString())
  }

  function onChatContextMenu(e: MouseEvent, chat: ChatItem): void {
    e.preventDefault()
    void deleteChatSelf(chat.id)
  }

  function intEq(a: number, b: number): boolean {
    return Number(a) === Number(b)
  }

  function canKick(memberId: number): boolean {
    if (!me.value || !infoChat.value) return false
    return intEq(infoChat.value.own, me.value.id) && !intEq(memberId, me.value.id)
  }

  async function kickMember(memberId: number): Promise<void> {
    if (!infoChat.value || !canKick(memberId)) return
    if (!confirm('Кикнуть участника из чата?')) return
    const res = await sendAndWait({ act: 'chat_kick', cid: infoChat.value.id, uid: memberId }, 'chat_kick')
    if (!res.ok) { setToast((res.err || 'Не удалось кикнуть').toString()); return }
    setToast('Участник удален')
  }

  function onMemberContextMenu(e: MouseEvent, member: { id: number }): void {
    e.preventDefault()
    void kickMember(member.id)
  }

  async function openDm(user: UserLite): Promise<void> {
    const res = await sendAndWait({ act: 'open_dm', to: user.username }, 'open_dm')
    if (!res.ok || !res.chat) { setToast((res.err || 'Не удалось открыть чат').toString()); return }
    patchChat(res.chat as ChatItem)
    await selectChat((res.chat as ChatItem).id)
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
    if (!ttl) { setToast('Нужно название'); return }
    createModal.busy = true
    try {
      const members = createModal.members.split(',').map((x) => x.trim()).filter(Boolean)
      const res = await sendAndWait({ act: 'create_chat', title: ttl, kind: createModal.kind, members }, 'create_chat')
      if (!res.ok || !res.chat) { setToast((res.err || 'Не удалось создать чат').toString()); return }
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
      if (!res.ok || !dat.ok || !dat.user) { setToast(dat.err || 'Не удалось обновить аватар'); return }
      patchUser(dat.user)
    } catch {
      setToast('Ошибка загрузки аватара')
    }
  }

  async function saveSettings(): Promise<void> {
    settingsBusy.value = true
    try {
      const res = await fetch(apiUrl('/profile'), {
        method: 'POST',
        headers: { Authorization: `Bearer ${token.value}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: settingsForm.name.trim(),
          username: settingsForm.username.trim().toLowerCase(),
          phone: settingsForm.phone.trim(),
          bio: settingsForm.bio.trim(),
        }),
      })
      const dat = (await res.json()) as { ok?: boolean; user?: UserLite; err?: string }
      if (!res.ok || !dat.ok || !dat.user) { setToast(dat.err || 'Не удалось сохранить профиль'); return }
      patchUser(dat.user)
      setToast('Профиль обновлен')
    } finally {
      settingsBusy.value = false
    }
  }

  async function searchUsersByText(q: string): Promise<void> {
    const val = q.trim()
    if (val.length < 2 || !wsState.ws || wsState.ws.readyState !== WebSocket.OPEN) {
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

  let mobileMql: MediaQueryList | null = null

  onMounted(async () => {
    syncMobileLayout()
    mobileMql = window.matchMedia('(max-width: 860px)')
    mobileMql.addEventListener('change', syncMobileLayout)

    token.value = localStorage.getItem('hamster_token') || ''
    if (!token.value) { void router.push('/'); return }

    const ok = await fetchMe()
    if (!ok) { clearAuthAndBack(); return }

    window.addEventListener('message', onWindowMessage)

    connectWs({
      onAuth: async () => {
        const auth = await sendAndWait({ act: 'auth', token: token.value }, 'auth')
        if (!auth.ok) throw new Error((auth.err || 'auth failed').toString())
        await loadChats()
      },
      playRing,
      stopRing,
      ensurePopup,
      updatePopupUi,
      startWebrtc,
      stopWebrtc,
      loadCallHistory,
    })
  })

  onBeforeUnmount(() => {
    window.removeEventListener('message', onWindowMessage)
    if (mobileMql) { mobileMql.removeEventListener('change', syncMobileLayout); mobileMql = null }
    wsState.manualWsClose = true
    if (wsState.reconnectTimer) window.clearTimeout(wsState.reconnectTimer)
    rejectAllPending('unmount')
    if (wsState.ws) wsState.ws.close()
    stopRing()
    stopWebrtc(true)
    closePopup()
  })

  watch(search, (v) => void searchUsersByText(v))
  watch(activeMessages, () => void scrollToBottom())
  watch(viewMode, async (v) => {
    syncMobileLayout()
    if (v === 'calls') await loadCallHistory().catch(() => null)
  })
  watch(activeChatId, () => {
    if (!isMobile.value || viewMode.value !== 'chats') return
    if (activeChatId.value <= 0) mobilePane.value = 'list'
  })
  watch(
    () => `${call.status}:${call.note}:${call.micMuted}:${call.camOff}`,
    () => updatePopupUi(),
  )
  watch(hiddenLocalVideo, hydrateMedia)
  watch(hiddenRemoteVideo, hydrateMedia)
  watch(hiddenRemoteAudio, hydrateMedia)

  return {
    // state
    viewMode, isMobile, mobilePane, me, connected, socketErr, toast,
    chats, activeChatId, messagesByChat, draft, search, searchUsersRes,
    searchingUsers, loadingMessages, messageScroller,
    createMenuOpen, createModal, settingsForm, settingsBusy,
    infoOpen, infoMode, infoUser, infoChat,
    callHistory, loadingCallHistory, call, incomingCall,
    hiddenLocalVideo, hiddenRemoteVideo, hiddenRemoteAudio,
    // computed
    activeChat, canWrite, activeMessages, activePeer,
    showLeftPane, showContentPane, mobileViewMode, filteredChats,
    // ui helpers
    fmtTime, fmtDateTime, avatarText,
    chatTitle, chatAvatar, chatStatus, previewText, isImage, fileLabel,
    // navigation
    setViewMode, openListOnMobile,
    // messages
    selectChat, sendText, pickFile,
    // chats
    deleteChatSelf, onChatContextMenu,
    canKick, kickMember, onMemberContextMenu,
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
  }
}