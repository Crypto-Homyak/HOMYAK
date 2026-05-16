import type { WsPacket, WsMessage, ChatItem, UserLite } from './mestypes'
import {
  wsState, popupState,
  connected, socketErr, token,
  chats, activeChatId, messagesByChat,
  me, settingsForm, infoUser,
  incomingCall, call,
  viewMode,
} from './messtate'
import { wsUrl, apiUrl } from './mesconfig'

const pending = new Map<string, Array<{
  resolve: (value: WsPacket) => void
  reject: (reason: Error) => void
  timer: number
}>>()

export function useWs() {

  function sendAndWait(payload: Record<string, unknown>, expectAct?: string, timeoutMs = 15000): Promise<WsPacket> {
    if (!wsState.ws || wsState.ws.readyState !== WebSocket.OPEN) return Promise.reject(new Error('WS closed'))
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
      wsState.ws!.send(JSON.stringify(payload))
    })
  }

  function sendNoWait(payload: Record<string, unknown>): void {
    if (!wsState.ws || wsState.ws.readyState !== WebSocket.OPEN) return
    wsState.ws.send(JSON.stringify(payload))
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

  function patchChat(chat: ChatItem): void {
    const idx = chats.value.findIndex((x) => x.id === chat.id)
    if (idx >= 0) chats.value[idx] = chat
    else chats.value.push(chat)
  }

  function addMessage(msg: WsMessage): void {
    const arr = messagesByChat[msg.cid] || []
    if (arr.some((x) => x.id === msg.id)) return
    arr.push(msg)
    arr.sort((a, b) => a.id - b.id)
    messagesByChat[msg.cid] = arr
    const chat = chats.value.find((x) => x.id === msg.cid)
    if (chat) chat.last = msg
  }

  function setOnline(uid: number, online: boolean): void {
    for (const chat of chats.value)
      for (const m of chat.members)
        if (m.id === uid) m.online = online
    if (me.value && me.value.id === uid) me.value.online = online
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
    if (infoUser.value && infoUser.value.id === user.id) infoUser.value = user
  }

  async function fetchMe(): Promise<boolean> {
    try {
      const res = await fetch(apiUrl('/me'), { headers: { Authorization: `Bearer ${token.value}` } })
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

  async function onWsMessage(ev: MessageEvent, callbacks: {
    playRing: () => void
    stopRing: () => void
    ensurePopup: () => void
    updatePopupUi: () => void
    startWebrtc: () => Promise<void>
    stopWebrtc: (stopTracks: boolean) => void
    loadCallHistory: () => Promise<void>
  }): Promise<void> {
    let pack: WsPacket = {}
    try { pack = JSON.parse(ev.data as string) as WsPacket } catch { return }
    if (resolvePending(pack)) return
    const act = (pack.act || '').toString()

    if (act === 'msg' && pack.ok && pack.msg) { addMessage(pack.msg as WsMessage); return }
    if ((act === 'chat_new' || act === 'chat_upd' || act === 'chat_recent') && pack.ok && pack.chat) { patchChat(pack.chat as ChatItem); return }
    if (act === 'chat_del' && pack.ok && typeof pack.cid === 'number') {
      chats.value = chats.value.filter((x) => x.id !== pack.cid)
      delete messagesByChat[pack.cid as number]
      if (activeChatId.value === pack.cid) activeChatId.value = 0
      return
    }
    if (act === 'user_upd' && pack.ok && pack.user) { patchUser(pack.user as UserLite); return }
    if (act === 'presence' && pack.ok) { setOnline(Number(pack.uid || 0), Boolean(pack.online)); return }
    if (act === 'presence_bulk' && pack.ok) {
      const ids = new Set(((pack.uids as number[] | undefined) || []).map((x) => Number(x)))
      for (const chat of chats.value) for (const m of chat.members) m.online = ids.has(m.id)
      if (me.value) me.value.online = ids.has(me.value.id)
      return
    }
    if (act === 'call_in' && pack.ok) {
      incomingCall.value = {
        cid: String(pack.cid || ''),
        chat: Number(pack.chat || 0),
        from: (pack.from || { id: 0, username: '', name: '' }) as { id: number; username: string; name: string },
      }
      callbacks.playRing()
      return
    }
    if (act === 'call_ring' && pack.ok) {
      call.cid = String(pack.cid || '')
      call.chat = Number(pack.chat || 0)
      call.status = 'ringing'
      call.note = 'Ожидание ответа'
      callbacks.playRing()
      callbacks.ensurePopup()
      callbacks.updatePopupUi()
      return
    }
    if (act === 'call_go' && pack.ok) {
      if (!call.cid) call.cid = String(pack.cid || '')
      call.status = 'talk'
      call.note = 'Звонок активен'
      callbacks.stopRing()
      await callbacks.startWebrtc()
      return
    }
    if (act === 'call_stop' && pack.ok) {
      callbacks.stopRing()
      callbacks.stopWebrtc(true)
      call.cid = ''
      call.chat = 0
      call.status = 'idle'
      call.note = ''
      popupState.callPopup?.close()
      popupState.callPopup = null
      popupState.popupLocalVideo = null
      popupState.popupRemoteVideo = null
      popupState.popupStatus = null
      popupState.popupMicBtn = null
      popupState.popupCamBtn = null
      if (viewMode.value === 'calls') await callbacks.loadCallHistory().catch(() => null)
      return
    }
  }

  function connectWs(callbacks: {
    onAuth: () => Promise<void>
    playRing: () => void
    stopRing: () => void
    ensurePopup: () => void
    updatePopupUi: () => void
    startWebrtc: () => Promise<void>
    stopWebrtc: (stopTracks: boolean) => void
    loadCallHistory: () => Promise<void>
  }): void {
    if (wsState.ws && (wsState.ws.readyState === WebSocket.OPEN || wsState.ws.readyState === WebSocket.CONNECTING)) return
    wsState.ws = new WebSocket(wsUrl())

    wsState.ws.onopen = async () => {
      connected.value = true
      socketErr.value = ''
      await callbacks.onAuth()
    }

    wsState.ws.onmessage = async (ev: MessageEvent) => {
      await onWsMessage(ev, callbacks)
    }

    wsState.ws.onclose = () => {
      connected.value = false
      rejectAllPending('ws closed')
      if (!wsState.manualWsClose) {
        wsState.reconnectTimer = window.setTimeout(() => connectWs(callbacks), 1800)
      }
    }

    wsState.ws.onerror = () => {
      socketErr.value = 'Ошибка WS'
    }
  }

  return {
    sendAndWait,
    sendNoWait,
    rejectAllPending,
    resolvePending,
    connectWs,
    fetchMe,
    patchChat,
    patchUser,
    addMessage,
  }
}