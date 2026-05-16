
export const API_BASE = ((import.meta.env.VITE_API_BASE as string | undefined)?.trim() || 'https://cryptohomyak.team/api').replace(/\/$/, '')

export function apiUrl(path: string): string {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

export function wsUrl(): string {
  const u = new URL(API_BASE)
  const proto = u.protocol === 'https:' ? 'wss:' : 'ws:'
  const pth = u.pathname.replace(/\/$/, '')
  return `${proto}//${u.host}${pth}/ws`
}