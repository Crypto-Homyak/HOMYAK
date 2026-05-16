import { reactive, ref } from 'vue'
import type {
  ViewMode,
  ProfileMode,
  UserLite,
  WsMessage,
  ChatItem,
  CallHistory,
} from './mestypes'

export const viewMode = ref<ViewMode>('chats')
export const isMobile = ref(false)
export const mobilePane = ref<'list' | 'chat'>('list')
export const infoOpen = ref(false)
export const infoMode = ref<ProfileMode>('user')
export const toast = ref('')
export const socketErr = ref('')
export const connected = ref(false)
export let toastTimer = 0

export const token = ref('')
export const me = ref<UserLite | null>(null)

export const chats = ref<ChatItem[]>([])
export const activeChatId = ref(0)
export const messagesByChat = reactive<Record<number, WsMessage[]>>({})
export const draft = ref('')
export const search = ref('')
export const searchUsersRes = ref<UserLite[]>([])
export const searchingUsers = ref(false)
export const loadingMessages = ref(false)
export const messageScroller = ref<HTMLElement | null>(null)

export const createMenuOpen = ref(false)
export const createModal = reactive({
  open: false,
  kind: 'group' as 'group' | 'channel',
  title: '',
  members: '',
  busy: false,
})

export const settingsForm = reactive({
  name: '',
  username: '',
  phone: '',
  bio: '',
})
export const settingsBusy = ref(false)

export const infoUser = ref<UserLite | null>(null)
export const infoChat = ref<ChatItem | null>(null)

export const callHistory = ref<CallHistory[]>([])
export const loadingCallHistory = ref(false)
export const call = reactive({
  cid: '',
  chat: 0,
  status: 'idle' as 'idle' | 'ringing' | 'talk' | 'error',
  note: '',
  micMuted: false,
  camOff: false,
})
export const incomingCall = ref<{
  cid: string
  chat: number
  from: { id: number; username: string; name: string }
} | null>(null)

export const hiddenLocalVideo = ref<HTMLVideoElement | null>(null)
export const hiddenRemoteVideo = ref<HTMLVideoElement | null>(null)
export const hiddenRemoteAudio = ref<HTMLAudioElement | null>(null)

export let manualWsClose = false
export let reconnectTimer = 0
export let mobileMql: MediaQueryList | null = null

export let pc: RTCPeerConnection | null = null
export let localStream: MediaStream | null = null
export let remoteStream: MediaStream | null = null

export let callPopup: Window | null = null
export let popupLocalVideo: HTMLVideoElement | null = null
export let popupRemoteVideo: HTMLVideoElement | null = null
export let popupStatus: HTMLElement | null = null
export let popupMicBtn: HTMLButtonElement | null = null
export let popupCamBtn: HTMLButtonElement | null = null

export let ringAudio: HTMLAudioElement | null = null

export const wsState = {
  ws: null as WebSocket | null,
  manualWsClose: false,
  reconnectTimer: 0,
  mobileMql: null as MediaQueryList | null,
}

export const rtcState = {
  pc: null as RTCPeerConnection | null,
  localStream: null as MediaStream | null,
  remoteStream: null as MediaStream | null,
}

export const popupState = {
  callPopup: null as Window | null,
  popupLocalVideo: null as HTMLVideoElement | null,
  popupRemoteVideo: null as HTMLVideoElement | null,
  popupStatus: null as HTMLElement | null,
  popupMicBtn: null as HTMLButtonElement | null,
  popupCamBtn: null as HTMLButtonElement | null,
  ringAudio: null as HTMLAudioElement | null,
}