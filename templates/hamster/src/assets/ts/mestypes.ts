export type ViewMode = 'chats' | 'calls' | 'settings'
export type ProfileMode = 'user' | 'chat'

export interface UserLite {
  id: number
  username: string
  name: string
  email: string
  avatar: string
  bio: string
  phone: string
  online: boolean
}

export interface ChatMember {
  id: number
  username: string
  name: string
  avatar: string
  role: string
  online: boolean
}

export interface WsMessage {
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

export interface ChatItem {
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

export interface CallHistory {
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

export interface WsPacket {
  act?: string
  ok?: boolean
  err?: string
  [key: string]: unknown
}