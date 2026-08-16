import { useEffect, useMemo, useRef, useState } from 'react'
import { Download, FileAudio, FolderOpen, Loader2, Play, Save, Send, Square, Upload } from 'lucide-react'
import { api, type AsrModelInfo, type Cue, type Job } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { useTransfer } from '../store/transfer'
import { Empty, PageHeader, ProgressBar, StatusTag, fmtTime } from '../components/ui'

interface TranscriptResult {
  out_dir: string
  outputs: { name: string; path: string; kind: string }[]
  cues: Cue[]
  language: string
  language_probability: number
  duration: number
  device: string
  model: string
  source: string
}

const LANGS: [string, string][] = [
  ['', 'Tự động phát hiện'], ['vi', 'Tiếng Việt'], ['en', 'English'], ['zh', 'Trung'], ['ja', 'Nhật'],
  ['ko', 'Hàn'], ['th', 'Thái'], ['fr', 'Pháp'], ['de', 'Đức'], ['es', 'Tây Ban Nha'], ['id', 'Indonesia'],
]
const FORMATS = ['srt', 'vtt', 'txt', 'lrc']
const ACCEPT = '.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,.wma,.mp4,.mkv,.mov,.webm,.avi,.m4b'

export default function TranscriptPage() {
  const [media, setMedia] = useState<{ path: string; name: string; duration: number } | null>(null)
  const [models, setModels] = useState<AsrModelInfo[]>([])
  const [model, setModel] = useState('small')
  const [lang, setLang] = useState('')
  const [device, setDevice] = useState('auto')
  const [wordTs, setWordTs] = useState(true)
  const [separate, setSeparate] = useState(false)
  const [formats, setFormats] = useState<string[]>(['srt', 'txt'])
  const [prompt, setPrompt] = useState('')
  const [gpu, setGpu] = useState<{ cuda: boolean; libs_installed: boolean; demucs: boolean } | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const trJobs = useJobs(selectJobsByKind('transcript'))
  const modelJobs = useJobs(selectJobsByKind('asr_model'))
  const gpuJobs = useJobs(selectJobsByKind('gpu_install'))
  const cancel = useJobs((s) => s.cancel)
  const latest = trJobs[0]
  const running = latest && (latest.status === 'queued' || latest.status === 'running')

  const refreshModels = () => api.asrModels().then(setModels).catch(() => undefined)
  useEffect(() => {
    refreshModels()
    fetch('/api/transcript/gpu').then((r) => r.json()).then(setGpu).catch(() => undefined)
    api.settings().then((s) => { setModel(s.asr_model); setDevice(s.asr_device) }).catch(() => undefined)
  }, [])
  const modelJobDone = modelJobs.filter((j) => j.status === 'done').length
  useEffect(() => { refreshModels() }, [modelJobDone])

  const modelInfo = models.find((m) => m.name === model)
  const modelJob = modelJobs.find((j) => j.params?.name === model && (j.status === 'running' || j.status === 'queued'))

  const onFile = async (f: File | undefined) => {
    if (!f) return
    setBusy(true)
    setErr('')
    try {
      const m = await api.uploadMedia(f)
      setMedia({ path: m.path, name: f.name, duration: m.duration })
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const start = async () => {
    if (!media) return
    setErr('')
    try {
      await api.transcribe({ path: media.path, model, language: lang || null, device, separate_vocals: separate, word_timestamps: wordTs, formats, initial_prompt: prompt || undefined } as never)
    } catch (e) {
      setErr(String(e))
    }
  }

  return (
    <div className="p-6">
      <PageHeader title="Phụ đề / Transcript" subtitle="Nhận dạng giọng nói offline bằng Whisper → SRT · VTT · TXT · LRC (lời bài hát)" />
      <div className="grid gap-5 xl:grid-cols-[1fr_1.3fr]">
        <div className="flex flex-col gap-4">
          <section className="card">
            <h2 className="mb-3 font-bold">1. Media</h2>
            <div
              className="grid place-items-center rounded-xl border-2 border-dashed border-line py-8 text-center hover:border-accent/60"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => { e.preventDefault(); onFile(e.dataTransfer.files?.[0]) }}
            >
              <Upload size={26} className="mb-2 text-muted" />
              <div className="text-sm font-semibold">Kéo thả audio / video</div>
              <div className="mb-3 text-xs text-muted">MP3 · WAV · M4A · FLAC · MP4 · MKV …</div>
              <button className="btn-ghost" onClick={() => fileRef.current?.click()} disabled={busy}>
                {busy ? <Loader2 size={14} className="animate-spin" /> : <FileAudio size={14} />} Chọn file
              </button>
              <input ref={fileRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
            </div>
            {media && (
              <div className="mt-3 flex items-center gap-2 rounded-lg bg-panel2 px-3 py-2 text-sm">
                <FileAudio size={16} className="text-accent" />
                <span className="truncate font-semibold">{media.name}</span>
                <span className="ml-auto text-xs text-muted">{fmtTime(media.duration)}</span>
              </div>
            )}
          </section>

          <section className="card">
            <h2 className="mb-3 font-bold">2. Model & tùy chọn</h2>
            <div className="grid gap-3">
              <div>
                <label className="label">Model Whisper</label>
                <div className="flex gap-2">
                  <select className="input" value={model} onChange={(e) => setModel(e.target.value)}>
                    {models.map((m) => (
                      <option key={m.name} value={m.name}>
                        {m.name} · {m.size_mb >= 1000 ? `${(m.size_mb / 1000).toFixed(1)} GB` : `${m.size_mb} MB`} {m.downloaded ? '✓' : '(chưa tải)'} — {m.desc}
                      </option>
                    ))}
                  </select>
                  {modelInfo && !modelInfo.downloaded && (
                    <button className="btn-primary shrink-0" disabled={!!modelJob} onClick={() => api.downloadAsrModel(model).catch((e) => setErr(String(e)))}>
                      {modelJob ? <Loader2 size={14} className="animate-spin" /> : <Download size={14} />} Tải
                    </button>
                  )}
                </div>
                {modelJob && <div className="mt-2"><ProgressBar value={modelJob.progress} label={modelJob.message} status={modelJob.status} /></div>}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="label">Ngôn ngữ</label>
                  <select className="input" value={lang} onChange={(e) => setLang(e.target.value)}>
                    {LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
                  </select>
                </div>
                <div>
                  <label className="label">Thiết bị</label>
                  <select className="input" value={device} onChange={(e) => setDevice(e.target.value)}>
                    <option value="auto">Tự động {gpu ? (gpu.cuda ? '(GPU)' : '(CPU)') : ''}</option>
                    <option value="cuda">GPU (CUDA)</option>
                    <option value="cpu">CPU</option>
                  </select>
                </div>
              </div>
              {gpu && !gpu.cuda && (
                <div className="rounded-lg bg-panel2 px-3 py-2 text-xs text-muted">
                  GPU chưa dùng được cho Whisper.{' '}
                  {gpu.libs_installed ? 'Thư viện đã cài — khởi động lại ứng dụng.' : (
                    <button className="text-accent underline" disabled={gpuJobs.some((j) => j.status === 'running')} onClick={() => fetch('/api/transcript/gpu/install', { method: 'POST' })}>
                      Cài thư viện CUDA (~1GB)
                    </button>
                  )}
                  {gpuJobs[0] && gpuJobs[0].status !== 'done' && <div className="mt-1"><ProgressBar value={gpuJobs[0].progress} label={gpuJobs[0].message} status={gpuJobs[0].status} /></div>}
                </div>
              )}
              <div className="flex flex-wrap gap-4 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" checked={wordTs} onChange={(e) => setWordTs(e.target.checked)} /> Mốc thời gian theo từ (phụ đề gọn hơn)</label>
                <label className="flex items-center gap-2" title={gpu?.demucs ? '' : 'Cần cài demucs'}>
                  <input type="checkbox" checked={separate} disabled={!gpu?.demucs} onChange={(e) => setSeparate(e.target.checked)} /> Tách giọng hát khỏi nhạc (lyrics) {gpu && !gpu.demucs && <span className="text-muted">— chưa cài demucs</span>}
                </label>
              </div>
              <div>
                <label className="label">Định dạng xuất</label>
                <div className="flex gap-2">
                  {FORMATS.map((f) => (
                    <button key={f} className={`chip uppercase ${formats.includes(f) ? 'chip-active' : ''}`} onClick={() => setFormats((s) => (s.includes(f) ? s.filter((x) => x !== f) : [...s, f]))}>{f}</button>
                  ))}
                </div>
              </div>
              <div>
                <label className="label">Gợi ý ngữ cảnh (tùy chọn: tên riêng, thuật ngữ…)</label>
                <input className="input" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Ví dụ: Sơn Tùng, Hà Nội, blockchain" />
              </div>
            </div>
            <button className="btn-primary mt-4 w-full justify-center py-3 text-base" onClick={start} disabled={!media || !modelInfo?.downloaded || !!running}>
              {running ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />} Bắt đầu nhận dạng
            </button>
            {err && <div className="mt-2 rounded-lg bg-err/10 px-3 py-2 text-xs text-err">{err}</div>}
          </section>
        </div>

        <div className="flex flex-col gap-4">
          {latest ? <ResultPanel job={latest} onCancel={() => cancel(latest.id)} /> : <Empty>Kết quả transcript sẽ hiện ở đây. Có thể sửa từng dòng rồi xuất lại hoặc gửi sang TTS.</Empty>}
        </div>
      </div>
    </div>
  )
}

function ResultPanel({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const running = job.status === 'queued' || job.status === 'running'
  const res = job.result as TranscriptResult | null
  const [cues, setCues] = useState<Cue[]>([])
  const [dirty, setDirty] = useState(false)
  const [msg, setMsg] = useState('')
  const send = useTransfer((s) => s.send)
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => {
    if (res?.cues) {
      setCues(res.cues)
      setDirty(false)
    }
  }, [job.id, res?.cues])

  const text = useMemo(() => cues.map((c) => c.text).join('\n'), [cues])

  const update = (i: number, patch: Partial<Cue>) => {
    setCues((cs) => cs.map((c, k) => (k === i ? { ...c, ...patch } : c)))
    setDirty(true)
  }
  const exportEdited = async (fmts: string[]) => {
    if (!res) return
    const r = await fetch('/api/transcript/export', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cues, formats: fmts, stem: res.source.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') ?? 'transcript', out_dir: res.out_dir, title: '' }),
    })
    const j = await r.json()
    setMsg(r.ok ? `Đã lưu ${j.outputs.map((o: { name: string }) => o.name).join(', ')}` : String(j.detail))
    if (r.ok) setDirty(false)
  }
  const sendToTts = () => {
    if (!res) return
    const title = res.source.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') ?? 'Transcript'
    send({
      title,
      source: res.source,
      format: 'srt',
      total_chars: text.length,
      chapters: [{ index: 1, title, text, chars: text.length, cues }],
    })
  }

  return (
    <section className="card">
      <div className="mb-3 flex items-center gap-2">
        <h2 className="font-bold">Kết quả</h2>
        <StatusTag status={job.status} />
        <span className="truncate text-xs text-muted">{String(job.params?.title ?? '')}</span>
        {running && (
          <button className="btn-danger ml-auto !px-2 !py-1" onClick={onCancel}><Square size={12} /> Hủy</button>
        )}
      </div>
      {(running || job.status === 'error') && <ProgressBar value={job.progress} label={job.message} status={job.status} />}
      {job.status === 'error' && <pre className="mt-2 max-h-40 overflow-auto rounded-lg bg-err/10 p-2 text-[11px] text-err">{job.message}</pre>}
      {res && job.status === 'done' && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <span>Ngôn ngữ: <b className="text-text">{res.language}</b> ({Math.round(res.language_probability * 100)}%)</span>
            <span>· {cues.length} dòng · {fmtTime(res.duration)} · {res.model}/{res.device}</span>
            <button className="chip ml-auto" onClick={() => api.openPath(res.out_dir)}><FolderOpen size={12} className="mr-1" /> Thư mục</button>
            {res.outputs.map((o) => (
              <a key={o.path} className="chip uppercase" href={api.fileUrl(o.path)} target="_blank" rel="noreferrer">{o.kind}</a>
            ))}
          </div>
          <audio ref={audioRef} className="h-8 w-full" controls preload="none" src={api.fileUrl(res.source)} />
          <div className="max-h-[420px] overflow-auto rounded-lg border border-line">
            {cues.map((c, i) => (
              <div key={i} className="grid grid-cols-[64px_64px_1fr] items-start gap-2 border-b border-line/60 px-2 py-1.5 last:border-b-0">
                <button
                  className="text-left font-mono text-[11px] text-accent hover:underline"
                  title="Phát từ đây"
                  onClick={() => { if (audioRef.current) { audioRef.current.currentTime = c.start; audioRef.current.play() } }}
                >
                  {fmtTime(c.start)}
                </button>
                <span className="font-mono text-[11px] text-muted">{fmtTime(c.end)}</span>
                <input className="input !py-1 !text-sm" value={c.text} onChange={(e) => update(i, { text: e.target.value })} />
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost" onClick={() => exportEdited(['srt'])}><Save size={14} /> Lưu SRT {dirty && '•'}</button>
            <button className="btn-ghost" onClick={() => exportEdited(['lrc'])}><Save size={14} /> Lưu LRC</button>
            <button className="btn-ghost" onClick={() => exportEdited(['txt', 'vtt'])}><Save size={14} /> TXT + VTT</button>
            <button className="btn-primary ml-auto" onClick={sendToTts}><Send size={14} /> Gửi sang TTS</button>
          </div>
          {msg && <div className="text-xs text-muted">{msg}</div>}
        </div>
      )}
    </section>
  )
}
