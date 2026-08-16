import { useEffect, useRef, useState } from 'react'
import { Cpu, Download, Loader2, Mic, Mic2, Play, Plus, Square, Trash2, Upload, Users } from 'lucide-react'
import { api, type CloneStatus, type Job, type VoiceProfile } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { toastError, toastOk } from '../store/ui'
import { Alert, Card, EmptyState, Field, LangBadge, PageHeader, ProgressBar, Segmented, VoiceAvatar, fmtBytes } from '../components/ui'

const PREVIEW_LANGS: [string, string][] = [['vi', 'Việt'], ['en', 'English'], ['zh', 'Trung'], ['ja', 'Nhật'], ['ko', 'Hàn'], ['fr', 'Pháp'], ['de', 'Đức'], ['es', 'T. Ban Nha']]

export default function ClonePage() {
  const [status, setStatus] = useState<CloneStatus | null>(null)
  const [profiles, setProfiles] = useState<VoiceProfile[] | null>(null)
  const installJob = useJobs(selectJobsByKind('clone_install'))[0]
  const installing = !!installJob && (installJob.status === 'running' || installJob.status === 'queued')

  const refresh = async () => {
    const [s, p] = await Promise.all([api.cloneStatus(), api.profiles()])
    setStatus(s)
    setProfiles(p)
  }
  useEffect(() => { refresh().catch((e) => toastError(e)) }, [])
  const prevInstall = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (prevInstall.current && prevInstall.current !== 'done' && installJob?.status === 'done') refresh().catch(() => undefined)
    prevInstall.current = installJob?.status
  }, [installJob?.status])

  return (
    <div className="mx-auto max-w-[1440px] p-6">
      <PageHeader title="Clone giọng" subtitle="Một mẫu giọng 10–25 giây → dùng cho mọi ngôn ngữ: Edge TTS đọc đúng ngôn ngữ, Seed-VC đổi sang chất giọng của bạn" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="flex flex-col gap-4">
          <Card title="Engine" icon={<Cpu size={14} />}>
            {status ? (
              <>
                <Alert kind={status.installed ? (status.device === 'cuda' ? 'success' : 'warning') : 'warning'}>{status.message}</Alert>
                <div className="mt-2 text-xs text-fg-muted">
                  PyTorch: {status.torch.installed ? `${status.torch.version} · ${status.torch.cuda ? `CUDA (${status.torch.device_name})` : 'CPU'}` : 'chưa cài'} · Model Seed-VC: {status.models_ready ? 'đã tải' : 'tải khi dùng lần đầu (~1 GB)'}
                </div>
                {!status.installed && (
                  <button className="btn-primary mt-3" disabled={installing} onClick={() => api.installClone().catch((e) => toastError(e))}>
                    {installing ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />} Cài đặt Clone giọng (~2–3 GB)
                  </button>
                )}
                {installJob && installJob.status !== 'done' && <div className="mt-3"><ProgressBar value={installJob.progress} label={installJob.message} status={installJob.status} /></div>}
              </>
            ) : <div className="text-sm text-fg-muted">Đang kiểm tra…</div>}
            <div className="subcard mt-3 text-xs leading-relaxed text-fg-muted">
              <b className="text-fg">Cách hoạt động.</b> Văn bản → giọng Edge cùng ngôn ngữ &amp; giới tính → chuyển đổi chất giọng (voice conversion, zero-shot) → file cuối mang âm sắc của mẫu. Vì chuyển đổi trên audio nên không phụ thuộc ngôn ngữ.
              <br /><b className="text-fg">Mẹo.</b> Mẫu 10–25 s, một người nói, không nhạc nền, không vang. GPU ≥ 4 GB xử lý nhanh; CPU rất chậm.
            </div>
          </Card>
          <NewProfile onCreated={() => refresh()} />
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-[15px] font-bold tracking-tight"><Users size={16} className="text-secondary-fg" /> Voice profiles {profiles && <span className="tag tag-muted">{profiles.length}</span>}</div>
          {profiles === null && <div className="card"><div className="skeleton h-4 w-40" /></div>}
          {profiles && profiles.length === 0 && (
            <EmptyState icon={<Mic2 size={20} />} title="Chưa có giọng clone" hint='Tạo profile ở bên trái, sau đó chọn "Giọng clone" trong trang Tạo giọng nói.' />
          )}
          {profiles?.map((p) => <ProfileCard key={p.id} p={p} installed={!!status?.installed} onDeleted={() => refresh()} />)}
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
  const [secs, setSecs] = useState(0)
  const recRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  // Unmount safety: stop recorder, release the microphone, clear the timer.
  useEffect(() => () => {
    if (recRef.current && recRef.current.state !== 'inactive') recRef.current.stop()
    streamRef.current?.getTracks().forEach((t) => t.stop())
    if (timerRef.current) window.clearInterval(timerRef.current)
  }, [])

  const startRec = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } })
      streamRef.current = stream
      const rec = new MediaRecorder(stream)
      chunksRef.current = []
      rec.ondataavailable = (e) => { if (e.data.size) chunksRef.current.push(e.data) }
      rec.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: rec.mimeType || 'audio/webm' })
        setFile(new File([blob], `ghi-am.${(rec.mimeType || 'audio/webm').includes('ogg') ? 'ogg' : 'webm'}`, { type: blob.type }))
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null
      }
      rec.start()
      recRef.current = rec
      setRecording(true)
      setSecs(0)
      timerRef.current = window.setInterval(() => setSecs((s) => s + 1), 1000)
    } catch (e) { toastError(e, 'Không truy cập được micro') }
  }
  const stopRec = () => { recRef.current?.stop(); setRecording(false); if (timerRef.current) window.clearInterval(timerRef.current) }
  useEffect(() => { if (recording && secs >= 25) stopRec() }, [secs, recording])

  const submit = async () => {
    if (!file || !name.trim()) return
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('name', name.trim()); fd.append('gender', gender); fd.append('language', language); fd.append('file', file)
      await api.createProfile(fd)
      toastOk('Đã tạo voice profile', name.trim())
      setName(''); setFile(null); onCreated()
    } catch (e) { toastError(e, 'Không tạo được profile') } finally { setBusy(false) }
  }

  return (
    <Card title="Tạo voice profile" icon={<Plus size={14} />}>
      <div className="grid gap-3.5">
        <Field label="Tên giọng"><input className="input" placeholder="vd: Giọng của tôi" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Giới tính (chọn giọng gốc)">
            <Segmented ariaLabel="Giới tính" value={gender} onChange={setGender} options={[{ value: 'female', label: 'Nữ' }, { value: 'male', label: 'Nam' }]} />
          </Field>
          <Field label="Ngôn ngữ chính">
            <select className="input" value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Ngôn ngữ chính">{PREVIEW_LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </Field>
        </div>
        <Field label="Mẫu giọng (10–25 giây)" help="Một người nói, không nhạc nền. File dài sẽ tự cắt còn 25 giây đầu.">
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-outline" onClick={() => fileRef.current?.click()} disabled={recording}><Upload size={15} /> Tải file</button>
            <input ref={fileRef} type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
            {!recording ? <button className="btn-outline" onClick={startRec}><Mic size={15} /> Ghi âm</button> : <button className="btn-danger" onClick={stopRec}><Square size={14} /> Dừng ({secs}s / 25s)</button>}
            {file && <span className="truncate text-xs text-fg-muted">{file.name} · {fmtBytes(file.size)}</span>}
          </div>
        </Field>
        <button className="btn-primary" onClick={submit} disabled={busy || !file || !name.trim()}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Tạo profile
        </button>
      </div>
    </Card>
  )
}

function ProfileCard({ p, installed, onDeleted }: { p: VoiceProfile; installed: boolean; onDeleted: () => void }) {
  const previews = useJobs(selectJobsByKind('clone_preview')).filter((j) => j.params?.profile === p.id)
  const [playing, setPlaying] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const jobFor = (lang: string): Job | undefined => previews.find((j) => j.params?.lang === lang)

  useEffect(() => () => { audioRef.current?.pause(); audioRef.current = null }, [])
  const play = async (url: string, key: string) => {
    audioRef.current?.pause()
    if (playing === key) { setPlaying(null); return }
    const a = new Audio(url)
    audioRef.current = a
    a.onended = () => setPlaying(null)
    try {
      await a.play()
      setPlaying(key)
    } catch (e) {
      setPlaying(null)
      toastError(e, 'Không phát được audio')
    }
  }
  const preview = async (lang: string) => {
    const j = jobFor(lang)
    if (j?.status === 'done' && j.result) return play((j.result as { url: string }).url, lang)
    try { await api.previewProfile(p.id, lang) } catch (e) { toastError(e) }
  }
  const remove = async () => {
    if (!confirm(`Xóa voice profile "${p.name}"?`)) return
    try { await api.deleteProfile(p.id); toastOk('Đã xóa profile', p.name); onDeleted() } catch (e) { toastError(e) }
  }

  return (
    <div className="card">
      <div className="flex items-start gap-3">
        <VoiceAvatar gender={p.gender} provider="clone" name={p.name} size={40} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-semibold">{p.name}</span>
            <span className="tag tag-muted">{p.gender === 'female' ? 'Nữ' : 'Nam'}</span>
            <LangBadge lang={p.language} />
            <button className="chip ml-auto" onClick={() => play(`/api/system/file?path=${encodeURIComponent(p.ref_path)}`, 'ref')} aria-pressed={playing === 'ref'}>
              {playing === 'ref' ? <Square size={12} /> : <Play size={12} />} Mẫu gốc
            </button>
            <button className="btn-icon btn-icon-sm hover:text-danger" aria-label={`Xóa ${p.name}`} onClick={remove}><Trash2 size={15} /></button>
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-fg-subtle">clone:{p.id} · {new Date(p.created_at).toLocaleString('vi-VN')}</div>
          <div className="mt-2.5 flex flex-wrap gap-1.5" role="group" aria-label="Nghe thử theo ngôn ngữ">
            {PREVIEW_LANGS.map(([lang, label]) => {
              const j = jobFor(lang)
              const busy = !!j && (j.status === 'running' || j.status === 'queued')
              const done = j?.status === 'done'
              return (
                <button key={lang} className={`chip ${done ? 'chip-primary' : ''}`} disabled={!installed || busy} title={installed ? `Nghe thử ${label}` : 'Cần cài engine'} aria-pressed={playing === lang} onClick={() => preview(lang)}>
                  {busy ? <Loader2 size={12} className="animate-spin" /> : playing === lang ? <Square size={12} /> : <Play size={12} />}
                  {label}
                </button>
              )
            })}
          </div>
          {previews.filter((j) => j.status === 'running').map((j) => <div key={j.id} className="mt-2"><ProgressBar value={j.progress} label={j.message} status={j.status} /></div>)}
          {previews.filter((j) => j.status === 'error').slice(0, 1).map((j) => <div key={j.id} className="mt-2"><Alert kind="danger">{j.message}</Alert></div>)}
        </div>
      </div>
    </div>
  )
}
