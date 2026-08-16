import { create } from 'zustand'
import type { Book } from '../lib/api'

/** Cross-page hand-off: Transcript page → TTS page ("Gửi sang TTS"). */
interface TransferState {
  pendingBook: Book | null
  navigate: ((page: string) => void) | null
  send: (book: Book) => void
  take: () => Book | null
  setNavigate: (fn: (page: string) => void) => void
}

export const useTransfer = create<TransferState>((set, get) => ({
  pendingBook: null,
  navigate: null,
  send: (book) => {
    set({ pendingBook: book })
    get().navigate?.('tts')
  },
  take: () => {
    const b = get().pendingBook
    if (b) set({ pendingBook: null })
    return b
  },
  setNavigate: (fn) => set({ navigate: fn }),
}))
