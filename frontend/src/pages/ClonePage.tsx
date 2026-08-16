import { useEffect, useRef, useState } from 'react'
import { Download, Loader2, Mic, Play, Plus, Square, Trash2, Upload } from 'lucide-react'
import { api, type CloneStatus, type Job, type VoiceProfile } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { Empty, PageHeader, ProgressBar } from '../components/ui'

const PREVIEW_LANGS: [string, string][] = [
  ['vi', '🇻🇳 Việt'], ['en', '🇺🇸 English'], ['zh', '🇨🇳 Trung'], ['ja', '🇯🇵 Nhật'], ['ko', '🇰🇷 Hàn'],
  ['fr', '🇫🇷 Pháp'], ['de', '🇩🇪 Đức'], ['es', '🇪🇸 TBN'],
]

interface StatusFull extends CloneStatus {
  torch: { installed: boolean; version: string | null; cuda: boolean; device_name: string | null }
  models_ready: boolean
}

export default function ClonePage() {
  const [status, setStatus] = useState<StatusFull | null>(null)
  const [profiles, setProfiles] = useState<VoiceProfile[]>([])
  const [err, setErr] = useState('')
  const installJobs = useJobs(selectJobsByKind('clone_install'))
  const installJob = installJobs[0]
  const installing = installJob && (installJob.status === 'running' || installJob.status === 'queued')

  const refresh = async () => {
    const [s, p] = await Promise.all([api.cloneStatus() as Promise<StatusFull>, api.profiles()])
    setStatus(s)
    setProfiles(p)
  }
  useEffect(() => { refresh().catch((e) => setErr(String(e))) }, [])
  useEffect(() => { if (installJob?.status === 'done') refresh().catch(() => undefined) }, [installJob?.status])

  return (
    <div className="p-6">
      <PageHeader
        title="Clone giọng"
        subtitle="Một mẫu giọng 10–25 giây → dùng cho MỌI ngôn ngữ (Edge TTS đọc đúng ngôn ngữ, Seed-VC đổi sang chất giọng của bạn)"
      />
      <div className="grid gap-5 xl:grid-cols-[1fr_1.4fr]">
        <div className="flex flex-col gap-4">
          <section className="card">
            <h2 className="mb-2 font-bold">Engine</h2>
            {status ? (
              <>
                <div className={`text-sm ${status.installed ? 'text-ok' : 'text-warn'}`}>{status.message}</div>
                <div className="mt-1 text-xs text-muted">
                  PyTorch: {status.torch.installed ? `${status.torch.version} · ${status.torch.cuda ? `CUDA (${status.torch.device_name})` : 'CPU'}` : 'chưa cài'} · Model Seed-VC: {status.models_ready ? 'đã tải' : 'tải khi dùng lần đầu (~1 GB)'}
                </div>
                {!status.installed && (
                  <button className="btn-primary mt-3" disabled={!!installing} onClick={() => api.installClone().catch((e) => setErr(String(e)))}>
                    {installing ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Cài đặt Clone giọng (~2–3 GB)
                  </button>
                )}
                {installJob && installJob.status !== 'done' && (
                  <div className="mt-3"><ProgressBar value={installJob.progress} label={installJob.message} status={installJob.status} /></div>
                )}
              </>
            ) : <div className="text-sm text-muted">Đang kiểm tra…</div>}
            <div className="mt-3 rounded-lg bg-panel2 p-3 text-xs leading-relaxed text-muted">
              <b className="text-text">Cách hoạt động:</b> văn bản → giọng Edge cùng ngôn ngữ & giới tính → chuyển đổi chất giọng (voice conversion, zero-shot) → file cuối mang âm sắc của mẫu.
              Vì chuyển đổi trên audio nên không phụ thuộc ngôn ngữ: một mẫu tiếng Việt vẫn đọc được tiếng Anh, Trung, Nhật…
              <br />Mẹo: mẫu 10–25 s, một người nói, không nhạc nền, không vang. GPU ≥ 4 GB nhanh; CPU chạy được nhưng chậm.
            </div>
          </section>
          <NewProfile onCreated={() => refresh()} />
          {err && <div className="rounded-lg bg-err/10 px-3 py-2 text-xs text-err">{err}</div>}
        </div>

        <div className="flex flex-col gap-3">
          <h2 className="font-bold">Voice profiles ({profiles.length})</h2>
          {profiles.length === 0 ? (
            <Empty>Chưa có giọng clone. Tạo profile bên trái — sau đó chọn "🎤 Giọng clone" trong trang Tạo giọng nói.</Empty>
          ) : (
            profiles.map((p) => <ProfileCard key={p.id} p={p} installed={!!status?.installed} onDeleted={() => refresh()} />)
          )}
        </div>
      </div>
    </div>
  )
}

function NewProfile({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [gender, setGender] = useState<'female' | 'male'>('female')
  const [language, setLanguage] = useState('vi')
  const [file, setFile] = useState<File | null>(null)
  const [recording, setRecording] = useState(false)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const [secs, setSecs] = useState(0)
  const recRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const startRec = async () => {
    setErr('')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data) }
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' })
        setFile(new File([blob], `ghi-am.${(rec.mimeType || 'audio/webm').includes('ogg') ? 'ogg' : 'webm'}`, { type: blob.type }))
        stream.getTracks().forEach((t) => t.stop())
      }
      rec.start()
      recRef.current = rec
      setRecording(true)
      setSecs(0)
      timerRef.current = window.setInterval(() => setSecs((s) => s + 1), 1000)
    } catch (e) {
      setErr(`Không truy cập được micro: ${String(e)}`)
    }
  }
  const stopRec = () => {
    recRef.current?.stop()
    setRecording(false)
    if (timerRef.current) window.clearInterval(timerRef.current)
  }
  useEffect(() => { if (recording && secs >= 25) stopRec() }, [secs, recording])

  const submit = async () => {
    if (!file || !name.trim()) return
    setBusy(true)
    setErr('')
    try {
      const fd = new FormData()
      fd.append('name', name.trim())
      fd.append('gender', gender)
      fd.append('language', language)
      fd.append('file', file)
      await api.createProfile(fd)
      setName('')
      setFile(null)
      onCreated()
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2 className="mb-3 font-bold">Tạo voice profile</h2>
      <div className="grid gap-3">
        <input className="input" placeholder="Tên giọng (vd: Giọng của tôi)" value={name} onChange={(e) => setName(e.target.value)} />
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="label">Giới tính (chọn giọng gốc)</label>
            <select className="input" value={gender} onChange={(e) => setGender(e.target.value as 'female' | 'male')}>
              <option value="female">Nữ</option>
              <option value="male">Nam</option>
            </select>
          </div>
          <div>
            <label className="label">Ngôn ngữ chính</label>
            <select className="input" value={language} onChange={(e) => setLanguage(e.target.value)}>
              {PREVIEW_LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
            </select>
          </div>
        </div>
        <div>
          <label className="label">Mẫu giọng (10–25 giây)</label>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost" onClick={() => fileRef.current?.click()} disabled={recording}><Upload size={14} /> Tải file</button>
            <input ref={fileRef} type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            {!recording ? (
              <button className="btn-ghost" onClick={startRec}><Mic size={14} /> Ghi âm</button>
            ) : (
              <button className="btn-danger" onClick={stopRec}><Square size={14} /> Dừng ({secs}s)</button>
            )}
            {file && <span className="truncate text-xs text-muted">{file.name} · {(file.size / 1024).toFixed(0)} KB</span>}
          </div>
        </div>
        <button className="btn-primary" onClick={submit} disabled={busy || !file || !name.trim()}>
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Plus size={14} />} Tạo profile
        </button>
        {err && <div className="rounded-lg bg-err/10 px-3 py-2 text-xs text-err">{err}</div>}
      </div>
    </section>
  )
}

function ProfileCard({ p, installed, onDeleted }: { p: VoiceProfile; installed: boolean; onDeleted: () => void }) {
  const previews = useJobs(selectJobsByKind('clone_preview')).filter((j) => j.params?.profile === p.id)
  const [playing, setPlaying] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  const jobFor = (lang: string): Job | undefined => previews.find((j) => j.params?.lang === lang)
  const play = async (url: string, key: string) => {
    audioRef.current?.pause()
    if (playing === key) { setPlaying(null); return }
    const a = new Audio(url)
    audioRef.current = a
    a.onended = () => setPlaying(null)
    await a.play()
    setPlaying(key)
  }
  const preview = async (lang: string) => {
    const j = jobFor(lang)
    if (j?.status === 'done' && j.result) {
      await play((j.result as { url: string }).url, lang)
      return
    }
    await api.previewProfile(p.id, lang)
  }

  return (
    <div className="card">
      <div className="flex items-start gap-3">
        <div className="grid h-10 w-10 place-items-center rounded-xl bg-accent/15 text-lg">🎤</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-semibold">{p.name}</span>
            <span className="tag bg-panel2 text-muted">{p.gender === 'female' ? 'Nữ' : 'Nam'} · {p.language}</span>
            <span className="tag bg-panel2 text-muted">{p.engine}</span>
            <button className="chip ml-auto" onClick={() => play(`/api/system/file?path=${encodeURIComponent(p.ref_path)}`, 'ref')}>
              <Play size={12} className="mr-1" /> Mẫu gốc
            </button>
            <button className="text-muted hover:text-err" title="Xóa" onClick={() => api.deleteProfile(p.id).then(onDeleted)}>
              <Trash2 size={16} />
            </button>
          </div>
          <div className="mt-1 text-[11px] text-muted">ID: clone:{p.id} · {new Date(p.created_at).toLocaleString('vi-VN')}</div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {PREVIEW_LANGS.map(([lang, label]) => {
              const j = jobFor(lang)
              const busy = j && (j.status === 'running' || j.status === 'queued')
              const done = j?.status === 'done'
              return (
                <button key={lang} className={`chip ${done ? 'chip-active' : ''}`} disabled={!installed || !!busy} title={installed ? 'Nghe thử giọng clone' : 'Cần cài engine'} onClick={() => preview(lang)}>
                  {busy ? <Loader2 size={12} className="mr-1 animate-spin" /> : <Play size={12} className="mr-1" />}
                  {label}
                </button>
              )
            })}
          </div>
          {previews.filter((j) => j.status === 'running').map((j) => (
            <div key={j.id} className="mt-2"><ProgressBar value={j.progress} label={j.message} status={j.status} /></div>
          ))}
          {previews.filter((j) => j.status === 'error').slice(0, 1).map((j) => (
            <div key={j.id} className="mt-2 rounded-lg bg-err/10 px-2 py-1 text-[11px] text-err">{j.message}</div>
          ))}
        </div>
      </div>
    </div>
  )
}
