import { create } from 'zustand'
import { api } from '../lib/api'

export type Theme = 'dark' | 'light'
export type ToastKind = 'info' | 'success' | 'warning' | 'danger'
export interface Toast {
  id: number
  kind: ToastKind
  title: string
  detail?: string
}

interface UiState {
  theme: Theme
  setTheme: (t: Theme) => void
  toggleTheme: () => void
  toasts: Toast[]
  toast: (kind: ToastKind, title: string, detail?: string, ttl?: number) => void
  dismiss: (id: number) => void
}

const KEY = 'tts.theme'
function initialTheme(): Theme {
  const saved = localStorage.getItem(KEY)
  if (saved === 'light' || saved === 'dark') return saved
  return 'dark' // brand default: dark-first pro tool; user can switch in Settings
}
function applyTheme(t: Theme) {
  document.documentElement.dataset.theme = t
  localStorage.setItem(KEY, t)
}

let seq = 1

export const useUi = create<UiState>((set, get) => ({
  theme: (() => {
    const t = initialTheme()
    applyTheme(t)
    return t
  })(),
  setTheme: (t) => {
    applyTheme(t)
    set({ theme: t })
  },
  toggleTheme: () => get().setTheme(get().theme === 'dark' ? 'light' : 'dark'),
  toasts: [],
  toast: (kind, title, detail, ttl = kind === 'danger' ? 8000 : 4000) => {
    const id = seq++
    set((s) => ({ toasts: [...s.toasts.slice(-4), { id, kind, title, detail }] }))
    window.setTimeout(() => get().dismiss(id), ttl)
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}))

/** Convenience for catch blocks: toastError(e) */
export const toastError = (e: unknown, title = 'Có lỗi xảy ra') => {
  const detail = e instanceof Error ? e.message : String(e)
  useUi.getState().toast('danger', title, detail)
  // every error the user sees is also written to the per-session error log (backend)
  api.reportClientError({ message: `${title}: ${detail}`, stack: e instanceof Error ? e.stack ?? '' : '', source: 'toast', url: location.hash || location.pathname })
}
export const toastOk = (title: string, detail?: string) => useUi.getState().toast('success', title, detail)
