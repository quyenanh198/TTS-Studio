import { useEffect, useMemo, useRef, useState } from 'react'
import { Cpu, Download, FileAudio, FolderOpen, Languages, ListMusic, Loader2, Play, Save, Send, Square, Upload } from 'lucide-react'
import { api, type AsrModelInfo, type Cue, type Job } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { useTransfer } from '../store/transfer'
import { toastError, toastOk } from '../store/ui'
import { Alert, Card, EmptyState, Field, PageHeader, ProgressBar, StatusTag, fmtTime } from '../components/ui'

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
interface GpuInfo { cuda: boolean; libs_installed: boolean; demucs: boolean }

const LANGS: [string, string][] = [
  ['', 'Tự động phát hiện'], ['vi', 'Tiếng Việt'], ['en', 'English'], ['zh', 'Trung'], ['ja', 'Nhật'], ['ko', 'Hàn'],
  ['th', 'Thái'], ['fr', 'Pháp'], ['de', 'Đức'], ['es', 'Tây Ban Nha'], ['id', 'Indonesia'],
]
const FORMATS = ['srt', 'vtt', 'txt', 'lrc']
const ACCEPT = '.mp3,.wav,.m4a,.aac,.flac,.ogg,.opus,.wma,.mp4,.mkv,.mov,.webm,.avi,.m4b'
const fmtSize = (mb: number) => (mb >= 1000 ? `${(mb / 1000).toFixed(1)} GB` : `${mb} MB`)

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
  const [gpu, setGpu] = useState<GpuInfo | null>(null)
  const [busy, setBusy] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const trJobs = useJobs(selectJobsByKind('transcript'))
  const modelJobs = useJobs(selectJobsByKind('asr_model'))
  const gpuJobs = useJobs(selectJobsByKind('gpu_install'))
  const cancel = useJobs((s) => s.cancel)
  const latest = trJobs[0]
  const running = !!latest && (latest.status === 'queued' || latest.status === 'running')

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
  const gpuJob = gpuJobs[0]

  const onFile = async (f: File | undefined) => {
    if (!f) return
    setBusy(true)
    try {
      const m = await api.uploadMedia(f)
      setMedia({ path: m.path, name: f.name, duration: m.duration })
    } catch (e) { toastError(e, 'Không tải được media') } finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }
  const start = async () => {
    if (!media) return
    try {
      await api.transcribe({ path: media.path, model, language: lang || null, device, separate_vocals: separate, word_timestamps: wordTs, formats, initial_prompt: prompt || undefined } as never)
      toastOk('Bắt đầu nhận dạng', `${media.name} · model ${model}`)
    } catch (e) { toastError(e, 'Không chạy được transcript') }
  }
  const canStart = !!media && !!modelInfo?.downloaded && !running && formats.length > 0

  return (
    <div className="mx-auto max-w-[1440px] p-6">
      <PageHeader title="Phụ đề / Transcript" subtitle="Nhận dạng giọng nói offline bằng Whisper → SRT · VTT · TXT · LRC (lời bài hát)" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.3fr)]">
        <div className="flex flex-col gap-4">
          <Card title="1. Media" icon={<FileAudio size={14} />}>
            <div
              className={`grid place-items-center rounded-[var(--radius-lg)] border-2 border-dashed px-6 py-8 text-center transition-colors duration-[var(--dur)] ${dragOver ? 'border-primary bg-primary-soft' : 'border-line-strong hover:border-secondary'}`}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
              onDragLeave={() => setDragOver(false)}
              onDrop={(e) => { e.preventDefault(); setDragOver(false); onFile(e.dataTransfer.files?.[0]) }}
            >
              <div className="mb-2 grid h-11 w-11 place-items-center rounded-full bg-surface-2 text-fg-muted"><Upload size={20} /></div>
              <div className="text-sm font-semibold">Kéo thả audio / video</div>
              <div className="mb-3 text-xs text-fg-muted">MP3 · WAV · M4A · FLAC · MP4 · MKV …</div>
              <button className="btn-outline" onClick={() => fileRef.current?.click()} disabled={busy}>
                {busy ? <Loader2 size={15} className="animate-spin" /> : <FileAudio size={15} />} Chọn file
              </button>
              <input ref={fileRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
            </div>
            {media && (
              <div className="subcard mt-3 flex items-center gap-2 text-[13px]">
                <FileAudio size={16} className="shrink-0 text-secondary-fg" />
                <span className="truncate font-semibold">{media.name}</span>
                <span className="ml-auto text-xs text-fg-muted tabular-nums">{fmtTime(media.duration)}</span>
              </div>
            )}
          </Card>

          <Card title="2. Model & tùy chọn" icon={<Cpu size={14} />}>
            <div className="grid gap-3.5">
              <Field label="Model Whisper" help={modelInfo && !modelInfo.downloaded ? `Chưa tải (${fmtSize(modelInfo.size_mb)}) — bấm Tải.` : undefined}>
                <div className="flex gap-2">
                  <select className="input" value={model} onChange={(e) => setModel(e.target.value)} aria-label="Model Whisper">
                    {models.map((m) => (
                      <option key={m.name} value={m.name}>{m.name} · {fmtSize(m.size_mb)} {m.downloaded ? '✓' : ''} — {m.desc}</option>
                    ))}
                  </select>
                  {modelInfo && !modelInfo.downloaded && (
                    <button className="btn-primary shrink-0" disabled={!!modelJob} onClick={() => api.downloadAsrModel(model).catch((e) => toastError(e))}>
                      {modelJob ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />} Tải
                    </button>
                  )}
                </div>
                {modelJob && <div className="mt-2"><ProgressBar value={modelJob.progress} label={modelJob.message} status={modelJob.status} /></div>}
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Ngôn ngữ">
                  <select className="input" value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Ngôn ngữ">{LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
                </Field>
                <Field label="Thiết bị">
                  <select className="input" value={device} onChange={(e) => setDevice(e.target.value)} aria-label="Thiết bị">
                    <option value="auto">Tự động {gpu ? (gpu.cuda ? '(GPU)' : '(CPU)') : ''}</option>
                    <option value="cuda">GPU (CUDA)</option>
                    <option value="cpu">CPU</option>
                  </select>
                </Field>
              </div>
              {gpu && !gpu.cuda && (
                <Alert kind="info">
                  GPU chưa dùng được cho Whisper.{' '}
                  {gpu.libs_installed ? 'Thư viện đã cài — khởi động lại ứng dụng.' : (
                    <button className="font-semibold underline underline-offset-2" disabled={gpuJob?.status === 'running'} onClick={() => fetch('/api/transcript/gpu/install', { method: 'POST' })}>Cài thư viện CUDA (~1 GB)</button>
                  )}
                  {gpuJob && gpuJob.status !== 'done' && <div className="mt-2 text-fg"><ProgressBar value={gpuJob.progress} label={gpuJob.message} status={gpuJob.status} /></div>}
                </Alert>
              )}
              <div className="flex flex-col gap-2 text-[13px]">
                <label className="flex items-center gap-2"><input type="checkbox" checked={wordTs} onChange={(e) => setWordTs(e.target.checked)} /> Mốc thời gian theo từ (phụ đề gọn hơn)</label>
                <label className={`flex items-center gap-2 ${gpu?.demucs ? '' : 'text-fg-muted'}`} title={gpu?.demucs ? '' : 'Cần cài demucs'}>
                  <input type="checkbox" checked={separate} disabled={!gpu?.demucs} onChange={(e) => setSeparate(e.target.checked)} /> Tách giọng hát khỏi nhạc (lyrics){gpu && !gpu.demucs && <span className="tag tag-muted">chưa cài demucs</span>}
                </label>
              </div>
              <Field label="Định dạng xuất">
                <div className="flex gap-1.5" role="group" aria-label="Định dạng xuất">
                  {FORMATS.map((f) => (
                    <button key={f} className={`chip uppercase ${formats.includes(f) ? 'chip-active' : ''}`} aria-pressed={formats.includes(f)} onClick={() => setFormats((s) => (s.includes(f) ? s.filter((x) => x !== f) : [...s, f]))}>{f}</button>
                  ))}
                </div>
              </Field>
              <Field label="Gợi ý ngữ cảnh (tùy chọn)" help="Tên riêng, thuật ngữ giúp nhận dạng chính xác hơn.">
                <input className="input" value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder="Ví dụ: Sơn Tùng, Hà Nội, blockchain" />
              </Field>
            </div>
            <button className="btn-primary btn-lg mt-4 w-full" onClick={start} disabled={!canStart}>
              {running ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />} Bắt đầu nhận dạng
            </button>
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          {latest ? <ResultPanel job={latest} onCancel={() => cancel(latest.id)} /> : (
            <EmptyState icon={<ListMusic size={20} />} title="Kết quả transcript sẽ hiện ở đây" hint="Bạn có thể sửa từng dòng, phát lại từ mốc thời gian, xuất lại SRT/LRC hoặc gửi thẳng sang trang Tạo giọng nói." />
          )}
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
  const send = useTransfer((s) => s.send)
  const audioRef = useRef<HTMLAudioElement>(null)

  useEffect(() => { if (res?.cues) { setCues(res.cues); setDirty(false) } }, [job.id, res?.cues])
  const text = useMemo(() => cues.map((c) => c.text).join('\n'), [cues])
  const stem = res?.source.split(/[\\/]/).pop()?.replace(/\.[^.]+$/, '') ?? 'transcript'

  const update = (i: number, patch: Partial<Cue>) => { setCues((cs) => cs.map((c, k) => (k === i ? { ...c, ...patch } : c))); setDirty(true) }
  const exportEdited = async (fmts: string[]) => {
    if (!res) return
    try {
      const r = await fetch('/api/transcript/export', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ cues, formats: fmts, stem, out_dir: res.out_dir, title: '' }) })
      const j = await r.json()
      if (!r.ok) throw new Error(String(j.detail))
      toastOk('Đã lưu', j.outputs.map((o: { name: string }) => o.name).join(', '))
      setDirty(false)
    } catch (e) { toastError(e, 'Không lưu được') }
  }
  const sendToTts = () => {
    if (!res) return
    send({ title: stem, source: res.source, format: 'srt', total_chars: text.length, chapters: [{ index: 1, title: stem, text, chars: text.length, cues }] })
  }

  return (
    <Card title="Kết quả" icon={<Languages size={14} />} right={<span className="flex items-center gap-2"><StatusTag status={job.status} />{running && <button className="btn-danger btn-sm" onClick={onCancel}><Square size={12} /> Hủy</button>}</span>}>
      <div className="mb-2 truncate text-xs text-fg-muted">{String(job.params?.title ?? '')}</div>
      {(running || job.status === 'error') && <ProgressBar value={job.progress} label={job.message} status={job.status} />}
      {job.status === 'error' && <div className="mt-2"><Alert kind="danger">{job.message}</Alert></div>}
      {res && job.status === 'done' && (
        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
            <span>Ngôn ngữ <b className="text-fg">{res.language}</b> ({Math.round(res.language_probability * 100)}%)</span>
            <span className="tabular-nums">· {cues.length} dòng · {fmtTime(res.duration)} · {res.model}/{res.device}</span>
            <button className="chip ml-auto" onClick={() => api.openPath(res.out_dir)}><FolderOpen size={12} /> Thư mục</button>
            {res.outputs.map((o) => <a key={o.path} className="chip uppercase" href={api.fileUrl(o.path)} target="_blank" rel="noreferrer">{o.kind}</a>)}
          </div>
          <audio ref={audioRef} className="h-9 w-full" controls preload="none" src={api.fileUrl(res.source)} />
          <div className="list max-h-[420px] overflow-auto">
            {cues.map((c, i) => (
              <div key={i} className="grid grid-cols-[60px_60px_1fr] items-center gap-2 border-b border-line px-2 py-1 last:border-b-0">
                <button className="rounded px-1 text-left font-mono text-[11px] tabular-nums text-secondary-fg hover:underline" title="Phát từ đây" onClick={() => { if (audioRef.current) { audioRef.current.currentTime = c.start; audioRef.current.play() } }}>{fmtTime(c.start)}</button>
                <span className="font-mono text-[11px] tabular-nums text-fg-subtle">{fmtTime(c.end)}</span>
                <input className="input !h-8 !bg-transparent !border-transparent hover:!border-line focus:!bg-surface-2" aria-label={`Dòng ${i + 1}`} value={c.text} onChange={(e) => update(i, { text: e.target.value })} />
              </div>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <button className="btn-ghost" onClick={() => exportEdited(['srt'])}><Save size={14} /> Lưu SRT{dirty && <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-label="có thay đổi" />}</button>
            <button className="btn-ghost" onClick={() => exportEdited(['lrc'])}><Save size={14} /> Lưu LRC</button>
            <button className="btn-ghost" onClick={() => exportEdited(['txt', 'vtt'])}><Save size={14} /> TXT + VTT</button>
            <button className="btn-primary ml-auto" onClick={sendToTts}><Send size={14} /> Gửi sang TTS</button>
          </div>
        </div>
      )}
    </Card>
  )
}
