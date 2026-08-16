import { useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, CheckSquare, ClipboardPaste, FileUp, FolderOpen, Loader2, Play, Square as SquareIcon, Trash2, Upload, Wand2 } from 'lucide-react'
import { api, type Book, type Chapter, type SynthesizeRequest, type Voice } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { useTransfer } from '../store/transfer'
import VoicePicker from '../components/VoicePicker'
import { Empty, PageHeader, ProgressBar, Slider, StatusTag, fmtTime } from '../components/ui'

type ExportMode = SynthesizeRequest['export_mode']

interface TtsResult {
  outputs: { name: string; path: string; duration: number; srt: string | null; kind: string }[]
  out_dir: string
  zip: string | null
  m4b: string | null
  duration: number
}

const ACCEPT = '.txt,.md,.markdown,.epub,.pdf,.docx,.srt,.mobi,.azw,.azw3,.fb2'

export default function TtsPage() {
  // ---- input --------------------------------------------------------------
  const [tab, setTab] = useState<'paste' | 'file'>('paste')
  const [pasted, setPasted] = useState('')
  const [pasteTitle, setPasteTitle] = useState('')
  const [book, setBook] = useState<Book | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [editing, setEditing] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  // ---- voice + controls ----------------------------------------------------------
  const [voice, setVoice] = useState('vi-VN-HoaiMyNeural')
  const [voiceObj, setVoiceObj] = useState<Voice | null>(null)
  const [rate, setRate] = useState(1.0)
  const [volume, setVolume] = useState(1.0)
  const [keepPitch, setKeepPitch] = useState(true)
  const [pitch, setPitch] = useState(0)
  const [format, setFormat] = useState<'mp3' | 'wav'>('mp3')
  const [mode, setMode] = useState<ExportMode>('per_chapter')
  const [rangeStart, setRangeStart] = useState(1)
  const [rangeEnd, setRangeEnd] = useState(1)
  const [mergeEvery, setMergeEvery] = useState(0)
  const [makeSrt, setMakeSrt] = useState(true)
  const [makeZip, setMakeZip] = useState(false)
  const [makeM4b, setMakeM4b] = useState(false)

  const ttsJobs = useJobs(selectJobsByKind('tts'))
  const latest = ttsJobs[0]
  const cancel = useJobs((s) => s.cancel)

  const takeTransfer = useTransfer((s) => s.take)
  const pendingBook = useTransfer((s) => s.pendingBook)
  useEffect(() => {
    const b = takeTransfer()
    if (b) {
      loadBook(b)
      setTab('file')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingBook])

  useEffect(() => {
    api.settings().then((s) => {
      setVoice(s.default_voice)
      setFormat(s.default_format)
      setRate(s.default_rate)
      setVolume(s.default_volume)
      setKeepPitch(s.keep_pitch)
    }).catch(() => undefined)
  }, [])

  const isSrtBook = !!book?.chapters.some((c) => c.cues && c.cues.length)
  useEffect(() => {
    if (isSrtBook) setMode('per_cue')
    else if (mode === 'per_cue') setMode('per_chapter')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isSrtBook])

  const loadBook = (b: Book) => {
    setBook(b)
    setSelected(new Set(b.chapters.map((c) => c.index)))
    setEditing(b.chapters.length === 1 ? b.chapters[0].index : null)
    setRangeStart(1)
    setRangeEnd(b.chapters.length)
    setErr('')
  }

  const parsePaste = async () => {
    if (!pasted.trim()) return
    setBusy(true)
    try {
      loadBook(await api.parseText(pasted, pasteTitle || undefined))
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  const onFile = async (f: File | undefined) => {
    if (!f) return
    setBusy(true)
    setErr('')
    try {
      loadBook(await api.parseFile(f))
      setTab('file')
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  const toggle = (i: number) =>
    setSelected((s) => {
      const n = new Set(s)
      if (n.has(i)) n.delete(i)
      else n.add(i)
      return n
    })

  const updateChapter = (i: number, patch: Partial<Chapter>) =>
    setBook((b) => (b ? { ...b, chapters: b.chapters.map((c) => (c.index === i ? { ...c, ...patch, chars: (patch.text ?? c.text).length } : c)) } : b))

  const removeChapter = (i: number) =>
    setBook((b) => {
      if (!b) return b
      const chapters = b.chapters.filter((c) => c.index !== i).map((c, k) => ({ ...c, index: k + 1 }))
      setSelected(new Set(chapters.map((c) => c.index)))
      setEditing(null)
      return { ...b, chapters }
    })

  const chosen = useMemo(() => (book ? book.chapters.filter((c) => selected.has(c.index)) : []), [book, selected])
  const totalChars = chosen.reduce((n, c) => n + c.text.length, 0)
  const estMin = Math.round(totalChars / 900) // ~900 chars/min at 1.0x Vietnamese
  const running = latest && (latest.status === 'queued' || latest.status === 'running')

  const submit = async () => {
    if (!book || chosen.length === 0) return
    setErr('')
    const isClone = voice.startsWith('clone:')
    const body: SynthesizeRequest = {
      title: book.title || 'Audio',
      chapters: chosen.map((c) => ({ title: c.title, text: c.text, cues: c.cues ?? null })),
      voice,
      rate,
      volume,
      keep_pitch: keepPitch,
      pitch,
      format,
      export_mode: mode,
      range_start: rangeStart,
      range_end: rangeEnd,
      merge_every: mergeEvery || undefined,
      make_srt: makeSrt,
      make_zip: makeZip,
      make_m4b: makeM4b,
      clone_profile: isClone ? voice.slice(6) : null,
    }
    try {
      await api.synthesize(body)
    } catch (e) {
      setErr(String(e))
    }
  }

  return (
    <div className="p-6">
      <PageHeader
        title="Tạo giọng nói"
        subtitle="Dán văn bản hoặc tải ebook / SRT → chọn giọng → xuất WAV/MP3 kèm phụ đề"
      />
      <div className="grid gap-5 xl:grid-cols-[1.15fr_1fr]">
        {/* ------------------------------ LEFT: input ------------------------------ */}
        <div className="flex flex-col gap-4">
          <section className="card">
            <div className="mb-3 flex gap-1 rounded-lg bg-panel2 p-1">
              <button className={`flex-1 rounded-md px-3 py-1.5 text-sm font-semibold ${tab === 'paste' ? 'bg-panel text-text' : 'text-muted'}`} onClick={() => setTab('paste')}>
                <ClipboardPaste size={14} className="mr-1 inline" /> Dán văn bản
              </button>
              <button className={`flex-1 rounded-md px-3 py-1.5 text-sm font-semibold ${tab === 'file' ? 'bg-panel text-text' : 'text-muted'}`} onClick={() => setTab('file')}>
                <FileUp size={14} className="mr-1 inline" /> Ebook / SRT / DOCX / PDF
              </button>
            </div>
            {tab === 'paste' ? (
              <div className="flex flex-col gap-2">
                <input className="input" placeholder="Tiêu đề (tùy chọn)" value={pasteTitle} onChange={(e) => setPasteTitle(e.target.value)} />
                <textarea
                  className="input min-h-40 resize-y font-[inherit]"
                  placeholder={'Dán nội dung tại đây. Dòng "Chương 1", "Chapter 2", "第三章" sẽ tự tách chương.'}
                  value={pasted}
                  onChange={(e) => setPasted(e.target.value)}
                />
                <div className="flex items-center justify-between">
                  <span className="text-xs text-muted">{pasted.length.toLocaleString('vi-VN')} ký tự</span>
                  <button className="btn-primary" onClick={parsePaste} disabled={busy || !pasted.trim()}>
                    {busy ? <Loader2 size={14} className="animate-spin" /> : <Wand2 size={14} />} Phân tích & tách chương
                  </button>
                </div>
              </div>
            ) : (
              <div
                className="grid place-items-center rounded-xl border-2 border-dashed border-line py-10 text-center hover:border-accent/60"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault()
                  onFile(e.dataTransfer.files?.[0])
                }}
              >
                <Upload size={28} className="mb-2 text-muted" />
                <div className="text-sm font-semibold">Kéo thả file vào đây</div>
                <div className="mb-3 text-xs text-muted">EPUB · PDF · DOCX · TXT · MD · SRT · MOBI/AZW3 (cần Calibre)</div>
                <button className="btn-ghost" onClick={() => fileRef.current?.click()} disabled={busy}>
                  {busy ? <Loader2 size={14} className="animate-spin" /> : <FileUp size={14} />} Chọn file
                </button>
                <input ref={fileRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
              </div>
            )}
            {err && <div className="mt-2 rounded-lg bg-err/10 px-3 py-2 text-xs text-err">{err}</div>}
          </section>

          {book && (
            <section className="card">
              <div className="mb-3 flex items-center gap-2">
                <BookOpen size={16} className="text-accent" />
                <input className="input !w-auto flex-1 font-semibold" value={book.title} onChange={(e) => setBook({ ...book, title: e.target.value })} />
                <span className="tag bg-panel2 text-muted">{book.format}</span>
              </div>
              <div className="mb-2 flex items-center justify-between text-xs text-muted">
                <span>
                  {book.chapters.length} chương · đã chọn {chosen.length} · {totalChars.toLocaleString('vi-VN')} ký tự · ~{estMin} phút audio
                </span>
                <div className="flex gap-2">
                  <button className="chip" onClick={() => setSelected(new Set(book.chapters.map((c) => c.index)))}>
                    <CheckSquare size={12} className="mr-1" /> Chọn hết
                  </button>
                  <button className="chip" onClick={() => setSelected(new Set())}>Bỏ chọn</button>
                </div>
              </div>
              <div className="max-h-72 overflow-auto rounded-lg border border-line">
                {book.chapters.map((c) => (
                  <div key={c.index} className={`border-b border-line/60 last:border-b-0 ${editing === c.index ? 'bg-panel2' : ''}`}>
                    <div className="flex items-center gap-2 px-3 py-2">
                      <input type="checkbox" checked={selected.has(c.index)} onChange={() => toggle(c.index)} />
                      <span className="w-8 text-right font-mono text-[11px] text-muted">{c.index}</span>
                      <button className="min-w-0 flex-1 truncate text-left text-sm hover:text-accent" onClick={() => setEditing(editing === c.index ? null : c.index)} title="Sửa">
                        {c.title}
                        {c.cues && <span className="tag ml-2 bg-accent2/15 text-accent2">SRT {c.cues.length} dòng</span>}
                      </button>
                      <span className="text-[11px] text-muted">{c.chars.toLocaleString('vi-VN')}</span>
                      <button className="text-muted hover:text-err" title="Xóa chương" onClick={() => removeChapter(c.index)}>
                        <Trash2 size={14} />
                      </button>
                    </div>
                    {editing === c.index && (
                      <div className="flex flex-col gap-2 px-3 pb-3">
                        <input className="input" value={c.title} onChange={(e) => updateChapter(c.index, { title: e.target.value })} />
                        <textarea
                          className="input min-h-40 resize-y"
                          value={c.text}
                          disabled={!!c.cues}
                          onChange={(e) => updateChapter(c.index, { text: e.target.value })}
                        />
                        {c.cues && <div className="text-[11px] text-muted">Nội dung SRT được đọc theo từng dòng phụ đề — thời gian được giữ nguyên.</div>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>

        {/* ------------------------------ RIGHT: voice + export ------------------------------ */}
        <div className="flex flex-col gap-4">
          <section className="card">
            <h2 className="mb-3 font-bold">Giọng đọc</h2>
            <VoicePicker value={voice} onChange={(id, v) => { setVoice(id); setVoiceObj(v) }} compact />
          </section>

          <section className="card">
            <h2 className="mb-3 font-bold">Điều chỉnh</h2>
            <div className="grid gap-4 md:grid-cols-2">
              <Slider label="Tốc độ" value={rate} min={0.5} max={2.0} step={0.05} format={(v) => `${v.toFixed(2)}x`} onChange={setRate} />
              <Slider label="Âm lượng" value={volume} min={0.2} max={2.0} step={0.05} format={(v) => `${Math.round(v * 100)}%`} onChange={setVolume} />
              <div>
                <label className="label">Cao độ</label>
                <div className="flex gap-1 rounded-lg bg-panel2 p-1 text-xs">
                  <button className={`flex-1 rounded-md py-1 font-semibold ${keepPitch ? 'bg-panel text-text' : 'text-muted'}`} onClick={() => setKeepPitch(true)}>Giữ nguyên</button>
                  <button className={`flex-1 rounded-md py-1 font-semibold ${!keepPitch ? 'bg-panel text-text' : 'text-muted'}`} onClick={() => setKeepPitch(false)}>Đổi theo tốc độ</button>
                </div>
              </div>
              <Slider label="Dịch cao độ (nửa cung)" value={pitch} min={-6} max={6} step={1} format={(v) => (v > 0 ? `+${v}` : `${v}`)} onChange={setPitch} />
              <div>
                <label className="label">Định dạng</label>
                <div className="flex gap-1 rounded-lg bg-panel2 p-1 text-xs">
                  {(['mp3', 'wav'] as const).map((f) => (
                    <button key={f} className={`flex-1 rounded-md py-1 font-semibold uppercase ${format === f ? 'bg-panel text-text' : 'text-muted'}`} onClick={() => setFormat(f)}>{f}</button>
                  ))}
                </div>
              </div>
              <div className="flex flex-col justify-end gap-1.5 text-sm">
                <label className="flex items-center gap-2"><input type="checkbox" checked={makeSrt} onChange={(e) => setMakeSrt(e.target.checked)} /> Tạo phụ đề SRT</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={makeZip} onChange={(e) => setMakeZip(e.target.checked)} /> Nén ZIP</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={makeM4b} onChange={(e) => setMakeM4b(e.target.checked)} /> Audiobook M4B (có chương)</label>
              </div>
            </div>
            {voiceObj?.provider === 'tiktok' && (
              <div className="mt-3 rounded-lg bg-warn/10 px-3 py-2 text-xs text-warn">Giọng TikTok cần sessionid trong Cài đặt. Đoạn dài sẽ được cắt ~280 ký tự/lần.</div>
            )}
          </section>

          <section className="card">
            <h2 className="mb-3 font-bold">Cách xuất</h2>
            <div className="grid gap-2 text-sm">
              {isSrtBook && (
                <label className="flex items-center gap-2"><input type="radio" checked={mode === 'per_cue'} onChange={() => setMode('per_cue')} /> Theo dòng phụ đề SRT (giữ đúng mốc thời gian)</label>
              )}
              <label className="flex items-center gap-2"><input type="radio" checked={mode === 'per_chapter'} onChange={() => setMode('per_chapter')} /> Mỗi chương một file</label>
              <label className="flex items-center gap-2"><input type="radio" checked={mode === 'merged'} onChange={() => setMode('merged')} /> Gộp toàn bộ thành một file</label>
              <label className="flex items-center gap-2"><input type="radio" checked={mode === 'range'} onChange={() => setMode('range')} /> Khoảng chương / gộp theo nhóm</label>
              {mode === 'range' && (
                <div className="ml-6 flex flex-wrap items-center gap-2 text-xs">
                  Từ <input className="input !w-20" type="number" min={1} value={rangeStart} onChange={(e) => setRangeStart(Number(e.target.value))} />
                  đến <input className="input !w-20" type="number" min={1} value={rangeEnd} onChange={(e) => setRangeEnd(Number(e.target.value))} />
                  · gộp mỗi <input className="input !w-20" type="number" min={0} value={mergeEvery} onChange={(e) => setMergeEvery(Number(e.target.value))} /> chương (0 = một file)
                </div>
              )}
            </div>
            <button className="btn-primary mt-4 w-full justify-center py-3 text-base" onClick={submit} disabled={!book || chosen.length === 0 || !!running}>
              {running ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />} Tạo giọng nói
            </button>
          </section>

          {latest && (
            <section className="card">
              <div className="mb-2 flex items-center gap-2">
                <h2 className="font-bold">Job gần nhất</h2>
                <StatusTag status={latest.status} />
                <span className="truncate text-xs text-muted">{String(latest.params?.title ?? '')}</span>
                {running && (
                  <button className="btn-danger ml-auto !px-2 !py-1" onClick={() => cancel(latest.id)}>
                    <SquareIcon size={12} /> Hủy
                  </button>
                )}
              </div>
              {(running || latest.status === 'error') && <ProgressBar value={latest.progress} label={latest.message} status={latest.status} />}
              {latest.status === 'done' && latest.result ? <ResultView r={latest.result as TtsResult} /> : null}
            </section>
          )}
        </div>
      </div>
      {!book && !latest && (
        <div className="mt-6">
          <Empty>Bắt đầu bằng cách dán văn bản hoặc tải ebook ở bên trái.</Empty>
        </div>
      )}
    </div>
  )
}

function ResultView({ r }: { r: TtsResult }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2 text-xs text-muted">
        <span>{r.outputs.length} file · {fmtTime(r.duration)}</span>
        <button className="chip ml-auto" onClick={() => api.openPath(r.out_dir)}>
          <FolderOpen size={12} className="mr-1" /> Mở thư mục
        </button>
        {r.zip && <a className="chip" href={api.fileUrl(r.zip)} target="_blank" rel="noreferrer">ZIP</a>}
      </div>
      <div className="max-h-64 overflow-auto rounded-lg border border-line">
        {r.outputs.map((o) => (
          <div key={o.path} className="flex flex-col gap-1 border-b border-line/60 px-3 py-2 last:border-b-0">
            <div className="flex items-center gap-2 text-sm">
              <span className="truncate font-semibold">{o.name}</span>
              <span className="text-[11px] text-muted">{fmtTime(o.duration)}</span>
              {o.srt && <a className="tag ml-auto bg-accent2/15 text-accent2" href={api.fileUrl(o.srt)} target="_blank" rel="noreferrer">SRT</a>}
            </div>
            {o.kind !== 'm4b' && <audio className="h-8 w-full" controls preload="none" src={api.fileUrl(o.path)} />}
          </div>
        ))}
      </div>
    </div>
  )
}
