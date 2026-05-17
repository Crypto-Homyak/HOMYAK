import type { WsPacket } from './mestypes'
import {
  rtcState, popupState,
  call, incomingCall, callHistory,
  loadingCallHistory, viewMode,
  hiddenLocalVideo, hiddenRemoteVideo, hiddenRemoteAudio,
} from './messtate'
import callMp3 from '@/assets/sounds/call.mp3'

export function useCall(deps: {
  sendAndWait: (payload: Record<string, unknown>, expectAct?: string, timeoutMs?: number) => Promise<WsPacket>
  sendNoWait: (payload: Record<string, unknown>) => void
  setToast: (text: string) => void
  clearAuthAndBack: () => void
}) {
  const { sendAndWait, sendNoWait, setToast } = deps

  function playRing(): void {
    if (popupState.ringAudio) {
      popupState.ringAudio.pause()
      popupState.ringAudio.currentTime = 0
    }
    popupState.ringAudio = new Audio(callMp3)
    popupState.ringAudio.loop = true
    popupState.ringAudio.play().catch(() => null)
  }

  function stopRing(): void {
    if (popupState.ringAudio) {
      popupState.ringAudio.pause()
      popupState.ringAudio.currentTime = 0
      popupState.ringAudio = null
    }
  }

  function ensurePopup(): void {
    if (popupState.callPopup && !popupState.callPopup.closed) return
    popupState.callPopup = window.open('', 'hamster_call_window', 'width=980,height=700,resizable=yes')
    if (!popupState.callPopup) { setToast('Браузер блокирует окно звонка'); return }
    popupState.callPopup.document.write(`
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
    popupState.callPopup.document.close()
    popupState.popupLocalVideo = popupState.callPopup.document.getElementById('local-video') as HTMLVideoElement | null
    popupState.popupRemoteVideo = popupState.callPopup.document.getElementById('remote-video') as HTMLVideoElement | null
    popupState.popupStatus = popupState.callPopup.document.getElementById('status')
    popupState.popupMicBtn = popupState.callPopup.document.getElementById('mic-btn') as HTMLButtonElement | null
    popupState.popupCamBtn = popupState.callPopup.document.getElementById('cam-btn') as HTMLButtonElement | null
    const endBtn = popupState.callPopup.document.getElementById('end-btn') as HTMLButtonElement | null
    if (popupState.popupMicBtn) popupState.popupMicBtn.onclick = () => window.postMessage({ act: 'call_toggle_mic' }, '*')
    if (popupState.popupCamBtn) popupState.popupCamBtn.onclick = () => window.postMessage({ act: 'call_toggle_cam' }, '*')
    if (endBtn) endBtn.onclick = () => window.postMessage({ act: 'call_end_req' }, '*')
  }

  function updatePopupUi(): void {
    if (popupState.popupStatus) popupState.popupStatus.textContent = call.note || call.status
    if (popupState.popupMicBtn) popupState.popupMicBtn.textContent = call.micMuted ? '🔇 Микро выкл' : '🎙 Микро вкл'
    if (popupState.popupCamBtn) popupState.popupCamBtn.textContent = call.camOff ? '📷 Камера выкл' : '📹 Камера вкл'
  }

  function closePopup(): void {
    if (popupState.callPopup && !popupState.callPopup.closed) popupState.callPopup.close()
    popupState.callPopup = null
    popupState.popupLocalVideo = null
    popupState.popupRemoteVideo = null
    popupState.popupStatus = null
    popupState.popupMicBtn = null
    popupState.popupCamBtn = null
  }

  function hydrateMedia(): void {
    if (hiddenLocalVideo.value) hiddenLocalVideo.value.srcObject = rtcState.localStream
    if (hiddenRemoteVideo.value) hiddenRemoteVideo.value.srcObject = rtcState.remoteStream
    if (hiddenRemoteAudio.value) hiddenRemoteAudio.value.srcObject = rtcState.remoteStream
    if (popupState.popupLocalVideo) popupState.popupLocalVideo.srcObject = rtcState.localStream
    if (popupState.popupRemoteVideo) popupState.popupRemoteVideo.srcObject = rtcState.remoteStream
    updatePopupUi()
  }

  async function ensureMedia(): Promise<void> {
    if (rtcState.localStream) for (const t of rtcState.localStream.getTracks()) t.stop()
    try {
      rtcState.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: true })
      call.camOff = false
    } catch {
      rtcState.localStream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false })
      call.camOff = true
    }
    call.micMuted = false
    hydrateMedia()
  }

  function toggleMic(): void {
    if (!rtcState.localStream) return
    const tracks = rtcState.localStream.getAudioTracks()
    if (!tracks.length) return
    const next = !call.micMuted
    for (const t of tracks) t.enabled = !next
    call.micMuted = next
    updatePopupUi()
  }

  function toggleCamera(): void {
    if (!rtcState.localStream) return
    const tracks = rtcState.localStream.getVideoTracks()
    if (!tracks.length) { setToast('Камера не подключена, звонок идет по аудио'); return }
    const next = !call.camOff
    for (const t of tracks) t.enabled = !next
    call.camOff = next
    updatePopupUi()
  }

  function ensurePeer(): void {
    if (rtcState.pc) return
    rtcState.remoteStream = new MediaStream()
    rtcState.pc = new RTCPeerConnection({ iceServers: [{ urls: 'stun:stun.l.google.com:19302' }] })

    rtcState.pc.ontrack = (ev) => {
      if (!rtcState.remoteStream) rtcState.remoteStream = new MediaStream()
      for (const t of ev.streams[0]?.getTracks() || [ev.track]) {
        if (!rtcState.remoteStream.getTracks().some((x) => x.id === t.id))
          rtcState.remoteStream.addTrack(t)
      }
      hydrateMedia()
    }

    rtcState.pc.onicecandidate = (ev) => {
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
    if (rtcState.pc) {
      rtcState.pc.ontrack = null
      rtcState.pc.onicecandidate = null
      rtcState.pc.onconnectionstatechange = null
      void rtcState.pc.close()
      rtcState.pc = null
    }
    if (stopTracks && rtcState.localStream) {
      for (const t of rtcState.localStream.getTracks()) t.stop()
      rtcState.localStream = null
    }
    if (rtcState.remoteStream) {
      for (const t of rtcState.remoteStream.getTracks()) t.stop()
      rtcState.remoteStream = null
    }
    call.micMuted = false
    call.camOff = false
    hydrateMedia()
  }

  async function startWebrtc(): Promise<void> {
    if (!call.cid) return
    try {
      ensurePeer()
      if (!rtcState.pc || !rtcState.localStream) return
      for (const t of rtcState.localStream.getTracks()) rtcState.pc.addTrack(t, rtcState.localStream)
      const offer = await rtcState.pc.createOffer()
      await rtcState.pc.setLocalDescription(offer)
      const ans = await sendAndWait(
        { act: 'call_offer', cid: call.cid, sdp: offer.sdp, type: offer.type },
        'call_ans',
        25000,
      )
      if (!ans.ok || !ans.sdp || !ans.type) throw new Error((ans.err || 'Ошибка SDP').toString())
      await rtcState.pc.setRemoteDescription(
        new RTCSessionDescription({ sdp: String(ans.sdp), type: String(ans.type) as RTCSdpType }),
      )
      call.status = 'talk'
      call.note = 'Соединение установлено'
      hydrateMedia()
    } catch (e) {
      call.status = 'error'
      call.note = e instanceof Error ? e.message : 'Ошибка звонка'
      updatePopupUi()
    }
  }

  async function loadCallHistory(): Promise<void> {
    loadingCallHistory.value = true
    try {
      const res = await sendAndWait({ act: 'call_hist', lim: 100 }, 'call_hist')
      callHistory.value = (res.items as typeof callHistory.value | undefined) || []
    } finally {
      loadingCallHistory.value = false
    }
  }

  async function startCall(chatId: number): Promise<void> {
    await ensureMedia()
    const res = await sendAndWait({ act: 'call_start', cid: chatId }, 'call_start')
    if (!res.ok) { setToast((res.err || 'Не удалось начать звонок').toString()); return }
    call.cid = String(res.cid || '')
    call.chat = Number(res.chat || chatId)
    call.status = 'ringing'
    call.note = 'Ждем ответ...'
    playRing()
    ensurePopup()
    updatePopupUi()
  }

  async function acceptCall(): Promise<void> {
    if (!incomingCall.value) return
    await ensureMedia()
    call.cid = incomingCall.value.cid
    call.chat = incomingCall.value.chat
    incomingCall.value = null
    stopRing()
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
    stopRing()
    await sendAndWait({ act: 'call_rej', cid }, 'call_rej').catch(() => null)
  }

  async function endCall(): Promise<void> {
    if (call.cid) await sendAndWait({ act: 'call_end', cid: call.cid }, 'call_end').catch(() => null)
    stopRing()
    stopWebrtc(true)
    call.cid = ''
    call.chat = 0
    call.status = 'idle'
    call.note = ''
    closePopup()
    if (viewMode.value === 'calls') await loadCallHistory().catch(() => null)
  }

  function callStatusText(st: string): string {
    if (st === 'ended') return 'Завершен'
    if (st === 'rejected') return 'Отклонен'
    if (st === 'missed') return 'Пропущен'
    if (st === 'talk') return 'Разговор'
    return 'Ожидание'
  }

  return {
    playRing, stopRing,
    ensurePopup, updatePopupUi, closePopup,
    hydrateMedia,
    toggleMic, toggleCamera,
    stopWebrtc, startWebrtc,
    loadCallHistory,
    startCall, acceptCall, rejectCall, endCall,
    callStatusText,
  }
}