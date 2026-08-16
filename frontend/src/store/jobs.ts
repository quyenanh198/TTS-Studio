import { create } from 'zustand'
import { api, type Job } from '../lib/api'

interface JobsState {
  jobs: Record<string, Job>
  connected: boolean
  load: () => Promise<void>
  connect: () => void
  upsert: (job: Job) => void
  remove: (id: string) => Promise<void>
  cancel: (id: string) => Promise<void>
}

let socket: WebSocket | null = null
let retryTimer: number | null = null

export const useJobs = create<JobsState>((set, get) => ({
  jobs: {},
  connected: false,

  load: async () => {
    const list = await api.jobs(undefined, 200)
    const map: Record<string, Job> = {}
    for (const j of list) map[j.id] = j
    set({ jobs: map })
  },

  upsert: (job) => set((s) => ({ jobs: { ...s.jobs, [job.id]: job } })),

  remove: async (id) => {
    await api.deleteJob(id)
    set((s) => {
      const next = { ...s.jobs }
      delete next[id]
      return { jobs: next }
    })
  },

  cancel: async (id) => {
    await api.cancelJob(id)
  },

  connect: () => {
    if (socket && (socket.readyState === WebSocket.OPEN || socket.readyState === WebSocket.CONNECTING)) return
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    socket = new WebSocket(`${proto}://${location.host}/api/ws/jobs`)
    socket.onopen = () => set({ connected: true })
    socket.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'job') get().upsert(msg.job as Job)
      } catch {
        /* ignore */
      }
    }
    socket.onclose = () => {
      set({ connected: false })
      if (retryTimer) window.clearTimeout(retryTimer)
      retryTimer = window.setTimeout(() => get().connect(), 1500)
    }
    socket.onerror = () => socket?.close()
  },
}))

// Derived selectors return new arrays — memoize on the jobs map identity to keep
// snapshots stable for useSyncExternalStore (avoids React #185 update loops).
const memo = new WeakMap<Record<string, Job>, Map<string, Job[]>>()
function derive(s: JobsState, key: string, fn: (list: Job[]) => Job[]): Job[] {
  let m = memo.get(s.jobs)
  if (!m) {
    m = new Map()
    memo.set(s.jobs, m)
  }
  let v = m.get(key)
  if (!v) {
    v = fn(Object.values(s.jobs))
    m.set(key, v)
  }
  return v
}

export const selectJobsByKind = (kind: string) => (s: JobsState) =>
  derive(s, `kind:${kind}`, (list) =>
    list.filter((j) => j.kind === kind).sort((a, b) => (a.created_at < b.created_at ? 1 : -1)),
  )

export const selectActiveJobs = (s: JobsState) =>
  derive(s, 'active', (list) => list.filter((j) => j.status === 'queued' || j.status === 'running'))

export const selectAllJobs = (s: JobsState) =>
  derive(s, 'all', (list) => [...list].sort((a, b) => (a.created_at < b.created_at ? 1 : -1)))
