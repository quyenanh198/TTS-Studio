// Typed API client for the local FastAPI backend.

export type JobStatus = 'queued' | 'running' | 'done' | 'error' | 'cancelled'

export interface Job<R = unknown> {
  id: string
  kind: string
  status: JobStatus
  progress: number
  message: string
  params: Record<string, unknown>
  result: R | null
  error: string | null
  created_at: string
  updated_at: string
}

export interface SystemInfo {
  platform: string
  python: string
  data_dir: string
  ffmpeg: string | null
  ffprobe: string | null
  gpu: { cuda: boolean; name: string | null; vram_mb: number | null; torch: string | null }
  modules: Record<string, boolean>
}

export interface Settings {
  output_dir: string
  tiktok_session_id: string
  default_voice: string
  default_format: 'mp3' | 'wav'
  default_rate: number
  default_volume: number
  keep_pitch: boolean
  asr_model: string
  asr_device: string
  vc_device: string
  vc_steps: number
  concurrency: number
  language_ui: string
}

export interface Voice {
  id: string
  name: string
  provider: 'edge' | 'tiktok' | 'clone'
  locale: string
  lang: string
  gender: 'female' | 'male' | 'unknown'
  hot?: boolean
  emoji?: string
}

export interface Chapter {
  index: number
  title: string
  text: string
  chars: number
  cues?: Cue[] | null
}

export interface Cue {
  index: number
  start: number
  end: number
  text: string
}

export interface Book {
  title: string
  source: string
  format: string
  chapters: Chapter[]
  total_chars: number
}

export interface VoiceProfile {
  id: string
  name: string
  gender: 'female' | 'male'
  language: string
  ref_path: string
  engine: string
  base_voice: string | null
  notes: string
  created_at: string
}

const BASE = ''

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: init?.body instanceof FormData ? undefined : { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!res.ok) {
    let detail = res.statusText
    try {
      const j = await res.json()
      detail = j.detail ?? JSON.stringify(j)
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

const json = (body: unknown) => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  system: () => req<SystemInfo>('/api/system'),
  installFfmpeg: () => req<Job>('/api/system/ffmpeg/install', { method: 'POST' }),
  openPath: (path: string) => req<{ ok: boolean }>('/api/system/open', json({ path })),
  fileUrl: (path: string) => `/api/system/file?path=${encodeURIComponent(path)}`,

  settings: () => req<Settings>('/api/settings'),
  saveSettings: (s: Partial<Settings>) =>
    req<Settings>('/api/settings', { method: 'PUT', body: JSON.stringify(s) }),

  jobs: (kind?: string, limit = 100) =>
    req<Job[]>(`/api/jobs?limit=${limit}${kind ? `&kind=${kind}` : ''}`),
  job: (id: string) => req<Job>(`/api/jobs/${id}`),
  cancelJob: (id: string) => req<{ ok: boolean }>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  deleteJob: (id: string) => req<{ ok: boolean }>(`/api/jobs/${id}`, { method: 'DELETE' }),

  // ---- TTS (Phase 2) ----
  voices: () => req<Voice[]>('/api/voices'),
  previewVoice: (voice: string, text?: string) =>
    req<{ path: string; url: string }>('/api/voices/preview', json({ voice, text })),
  synthesize: (body: SynthesizeRequest) => req<Job>('/api/tts/synthesize', json(body)),

  // ---- Inputs (Phase 3) ----
  parseText: (text: string, title?: string) => req<Book>('/api/inputs/text', json({ text, title })),
  parseFile: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return req<Book>('/api/inputs/file', { method: 'POST', body: fd })
  },

  // ---- Transcript (Phase 5) ----
  transcribe: (body: TranscribeRequest) => req<Job>('/api/transcript', json(body)),
  uploadMedia: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return req<{ path: string; duration: number }>('/api/transcript/upload', { method: 'POST', body: fd })
  },
  asrModels: () => req<AsrModelInfo[]>('/api/transcript/models'),
  downloadAsrModel: (name: string) => req<Job>('/api/transcript/models/download', json({ name })),

  // ---- Voice clone (Phase 6) ----
  profiles: () => req<VoiceProfile[]>('/api/clone/profiles'),
  createProfile: (fd: FormData) => req<VoiceProfile>('/api/clone/profiles', { method: 'POST', body: fd }),
  deleteProfile: (id: string) => req<{ ok: boolean }>(`/api/clone/profiles/${id}`, { method: 'DELETE' }),
  cloneStatus: () => req<CloneStatus>('/api/clone/status'),
  installClone: () => req<Job>('/api/clone/install', { method: 'POST' }),
  previewProfile: (id: string, lang: string) =>
    req<Job>(`/api/clone/profiles/${id}/preview`, json({ lang })),
}

export interface SynthesizeRequest {
  title: string
  chapters: { title: string; text: string; cues?: Cue[] | null }[]
  voice: string
  rate: number
  volume: number
  keep_pitch: boolean
  pitch: number
  format: 'mp3' | 'wav'
  export_mode: 'per_chapter' | 'merged' | 'range' | 'per_cue'
  range_start?: number
  range_end?: number
  merge_every?: number
  make_srt: boolean
  make_zip: boolean
  make_m4b: boolean
  clone_profile?: string | null
  output_dir?: string | null
}

export interface TranscribeRequest {
  path: string
  model: string
  language: string | null
  device: string
  separate_vocals: boolean
  word_timestamps: boolean
  formats: string[]
}

export interface AsrModelInfo {
  name: string
  size_mb: number
  downloaded: boolean
  desc: string
}

export interface CloneStatus {
  installed: boolean
  device: string
  engines: string[]
  message: string
}
