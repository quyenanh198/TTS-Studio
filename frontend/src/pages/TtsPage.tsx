import { useEffect, useMemo, useRef, useState } from 'react'
import { BookOpen, CheckSquare, ClipboardPaste, Download, FileUp, FolderOpen, Layers, Loader2, Mic2, Play, Settings2, Sparkles, Square as SquareIcon, Trash2, Upload, Wand2 } from 'lucide-react'
import { api, safeCall, type Book, type Chapter, type SynthesizeRequest, type Voice } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { useTransfer } from '../store/transfer'
import { toastError, toastOk } from '../store/ui'
import VoicePicker from '../components/VoicePicker'
import { Alert, Card, EmptyState, Field, PageHeader, ProgressBar, Segmented, Slider, StatusTag, fmtNum, fmtTime } from '../components/ui'

type ExportMode = SynthesizeRequest['export_mode']

interface TtsResult {
  outputs: { name: string; path: string; duration: number; srt: string | null; kind: string }[]
  out_dir: string
  zip: string | null
  m4b: string | null
  duration: number
}

const ACCEPT = '.txt,.md,.markdown,.epub,.pdf,.docx,.srt,.mobi,.azw,.azw3,.fb2'

export default function TtsPage({ active = true }: { active?: boolean }) {
  const [tab, setTab] = useState<'paste' | 'file'>('paste')
  const [pasted, setPasted] = useState('')
  const [pasteTitle, setPasteTitle] = useState('')
  const [book, setBook] = useState<Book | null>(null)
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [editing, setEditing] = useState<number | null>(null)
  const [busy, setBusy] = useState(false)
  const [dragOver, setDragOver] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

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
  const [expressive, setExpressive] = useState(true)
  const [expressiveLevel, setExpressiveLevel] = useState(0.7)

  const ttsJobs = useJobs(selectJobsByKind('tts'))
  const latest = ttsJobs[0]
  const cancel = useJobs((s) => s.cancel)
  const running = !!latest && (latest.status === 'queued' || latest.status === 'running')

  const takeTransfer = useTransfer((s) => s.take)
  const pendingBook = useTransfer((s) => s.pendingBook)
  useEffect(() => {
    const b = takeTransfer()
    if (b) { loadBook(b); setTab('file'); toastOk('Đã nhận transcript', `${b.chapters[0]?.cues?.length ?? 0} dòng phụ đề`) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingBook])

  useEffect(() => {
    api.settings().then((s) => { setVoice(s.default_voice); setFormat(s.default_format); setRate(s.default_rate); setVolume(s.default_volume); setKeepPitch(s.keep_pitch) }).catch(() => undefined)
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
  }
  const parsePaste = async () => {
    if (!pasted.trim()) return
    setBusy(true)
    try {
      const b = await api.parseText(pasted, pasteTitle || undefined)
      loadBook(b)
      toastOk('Đã phân tích', `${b.chapters.length} chương · ${fmtNum(b.total_chars)} ký tự`)
    } catch (e) { toastError(e, 'Không phân tích được văn bản') } finally { setBusy(false) }
  }
  const onFile = async (f: File | undefined) => {
    if (!f) return
    setBusy(true)
    try {
      const b = await api.parseFile(f)
      loadBook(b)
      setTab('file')
      toastOk(`Đã đọc ${f.name}`, `${b.chapters.length} chương · ${fmtNum(b.total_chars)} ký tự`)
    } catch (e) { toastError(e, 'Không đọc được file') } finally { setBusy(false); if (fileRef.current) fileRef.current.value = '' }
  }
  const toggle = (i: number) => setSelected((s) => { const n = new Set(s); if (n.has(i)) n.delete(i); else n.add(i); return n })
  const updateChapter = (i: number, patch: Partial<Chapter>) =>
    setBook((b) => (b ? { ...b, chapters: b.chapters.map((c) => (c.index === i ? { ...c, ...patch, chars: (patch.text ?? c.text).length } : c)) } : b))
  const removeChapter = (i: number) => {
    if (!book) return
    const kept = book.chapters.filter((c) => c.index !== i)
    const chapters = kept.map((c, k) => ({ ...c, index: k + 1 }))
    const nextSel = new Set<number>()
    kept.forEach((c, k) => { if (selected.has(c.index)) nextSel.add(k + 1) })
    setBook({ ...book, chapters })
    setSelected(nextSel)
    setEditing(null)
  }

  const chosen = useMemo(() => (book ? book.chapters.filter((c) => selected.has(c.index)) : []), [book, selected])
  const totalChars = chosen.reduce((n, c) => n + c.text.length, 0)
  const estMin = Math.max(1, Math.round(totalChars / 900 / rate))
  const rangeOk = mode !== 'range' || (rangeStart >= 1 && rangeEnd >= rangeStart && rangeEnd <= (book?.chapters.length ?? 0))
  const canSubmit = !!book && chosen.length > 0 && !running && rangeOk

  const submit = async () => {
    if (!canSubmit || !book) return
    const isClone = voice.startsWith('clone:')
    const body: SynthesizeRequest = {
      title: book.title || 'Audio',
      chapters: chosen.map((c) => ({ title: c.title, text: c.text, cues: c.cues ?? null })),
      voice, rate, volume, keep_pitch: keepPitch, pitch, format, export_mode: mode,
      ...(mode === 'range' ? { range_start: Math.max(1, rangeStart || 1), range_end: Math.max(1, rangeEnd || 1), merge_every: mergeEvery || undefined } : {}),
      make_srt: makeSrt, make_zip: makeZip, make_m4b: makeM4b, clone_profile: isClone ? voice.slice(6) : null,
      expressive, expressive_level: expressiveLevel,
    }
    try { await api.synthesize(body); toastOk('Đã thêm vào hàng đợi', `${chosen.length} chương · giọng ${voiceObj?.name ?? voice}`) } catch (e) { toastError(e, 'Không tạo được job') }
  }
  const submitRef = useRef(submit)
  submitRef.current = submit
  useEffect(() => {
    if (!active) return
    const onKey = (e: KeyboardEvent) => { if (e.ctrlKey && e.key === 'Enter') { e.preventDefault(); submitRef.current() } }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active])

  return (
    <div className="mx-auto max-w-[1440px] p-6">
      <PageHeader title="Tạo giọng nói" subtitle="Dán văn bản hoặc tải ebook / SRT → chọn giọng → xuất WAV/MP3 kèm phụ đề" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        {/* ============ LEFT: content ============ */}
        <div className="flex flex-col gap-4">
          <Card title="1. Nội dung" icon={<BookOpen size={14} />}>
            <Segmented ariaLabel="Nguồn nội dung" value={tab} onChange={setTab} options={[
              { value: 'paste', label: <span className="inline-flex items-center gap-1.5"><ClipboardPaste size={13} /> Dán văn bản</span> },
              { value: 'file', label: <span className="inline-flex items-center gap-1.5"><FileUp size={13} /> Ebook · SRT · DOCX · PDF</span> },
            ]} />
            <div className="mt-3">
              {tab === 'paste' ? (
                <div className="flex flex-col gap-2.5">
                  <input className="input" placeholder="Tiêu đề (tùy chọn)" aria-label="Tiêu đề" value={pasteTitle} onChange={(e) => setPasteTitle(e.target.value)} />
                  <textarea className="input min-h-44 resize-y" aria-label="Nội dung văn bản" placeholder={'Dán nội dung. Dòng "Chương 1", "Chapter 2", "第三章" sẽ tự tách chương.'} value={pasted} onChange={(e) => setPasted(e.target.value)} />
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-xs text-fg-muted tabular-nums">{fmtNum(pasted.length)} ký tự</span>
                    <button className="btn-primary" onClick={parsePaste} disabled={busy || !pasted.trim()}>
                      {busy ? <Loader2 size={15} className="animate-spin" /> : <Wand2 size={15} />} Phân tích & tách chương
                    </button>
                  </div>
                </div>
              ) : (
                <div
                  className={`grid place-items-center rounded-[var(--radius-lg)] border-2 border-dashed px-6 py-9 text-center transition-colors duration-[var(--dur)] ${dragOver ? 'border-primary bg-primary-soft' : 'border-line-strong hover:border-secondary'}`}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => { e.preventDefault(); setDragOver(false); onFile(e.dataTransfer.files?.[0]) }}
                >
                  <div className="mb-2 grid h-11 w-11 place-items-center rounded-full bg-surface-2 text-fg-muted"><Upload size={20} /></div>
                  <div className="text-sm font-semibold">Kéo thả file vào đây</div>
                  <div className="mb-3 text-xs text-fg-muted">EPUB · PDF · DOCX · TXT · MD · SRT · MOBI/AZW3 (cần Calibre)</div>
                  <button className="btn-outline" onClick={() => fileRef.current?.click()} disabled={busy}>
                    {busy ? <Loader2 size={15} className="animate-spin" /> : <FileUp size={15} />} Chọn file
                  </button>
                  <input ref={fileRef} type="file" accept={ACCEPT} className="hidden" onChange={(e) => onFile(e.target.files?.[0])} />
                </div>
              )}
            </div>
          </Card>

          {book ? (
            <Card title="2. Chương" icon={<Layers size={14} />} right={<span className="tag tag-muted">{book.format}</span>}>
              <div className="mb-3 flex items-center gap-2">
                <input className="input font-semibold" aria-label="Tên sách" value={book.title} onChange={(e) => setBook({ ...book, title: e.target.value })} />
              </div>
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2 text-xs text-fg-muted">
                <span className="tabular-nums">{book.chapters.length} chương · chọn {chosen.length} · {fmtNum(totalChars)} ký tự · ~{estMin} phút audio</span>
                <div className="flex gap-1.5">
                  <button className="chip" onClick={() => setSelected(new Set(book.chapters.map((c) => c.index)))}><CheckSquare size={12} /> Chọn hết</button>
                  <button className="chip" onClick={() => setSelected(new Set())}>Bỏ chọn</button>
                </div>
              </div>
              <div className="list max-h-80 overflow-auto">
                {book.chapters.map((c) => (
                  <div key={c.index} className={`border-b border-line last:border-b-0 ${editing === c.index ? 'bg-surface-2' : ''}`}>
                    <div className="flex min-h-10 items-center gap-2 px-3 py-1.5">
                      <input type="checkbox" aria-label={`Chọn chương ${c.index}`} checked={selected.has(c.index)} onChange={() => toggle(c.index)} />
                      <span className="w-7 text-right font-mono text-[11px] text-fg-subtle tabular-nums">{c.index}</span>
                      <button className="min-w-0 flex-1 truncate text-left text-[13px] hover:text-secondary-fg" onClick={() => setEditing(editing === c.index ? null : c.index)} title="Bấm để sửa">
                        {c.title}
                        {c.cues && <span className="tag tag-info ml-2">SRT · {c.cues.length} dòng</span>}
                      </button>
                      <span className="text-[11px] text-fg-muted tabular-nums">{fmtNum(c.chars)}</span>
                      <button className="btn-icon btn-icon-sm hover:text-danger" aria-label={`Xóa chương ${c.index}`} onClick={() => removeChapter(c.index)}><Trash2 size={14} /></button>
                    </div>
                    {editing === c.index && (
                      <div className="flex flex-col gap-2 px-3 pb-3">
                        <input className="input" aria-label="Tiêu đề chương" value={c.title} onChange={(e) => updateChapter(c.index, { title: e.target.value })} />
                        <textarea className="input min-h-40 resize-y" aria-label="Nội dung chương" value={c.text} disabled={!!c.cues} onChange={(e) => updateChapter(c.index, { text: e.target.value })} />
                        {c.cues && <p className="help">Nội dung SRT được đọc theo từng dòng phụ đề — thời gian được giữ nguyên.</p>}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </Card>
          ) : (
            <EmptyState icon={<Sparkles size={20} />} title="Chưa có nội dung" hint="Dán văn bản hoặc tải ebook ở trên. Chương sẽ tự động được nhận diện để bạn chọn phần cần đọc." />
          )}
        </div>

        {/* ============ RIGHT: voice + export ============ */}
        <div className="flex flex-col gap-4">
          <Card title="3. Giọng đọc" icon={<Mic2 size={14} />}>
            <VoicePicker value={voice} onChange={(id, v) => { setVoice(id); setVoiceObj(v) }} compact />
            <div className="mt-4 rounded-[var(--radius-md)] border border-line bg-surface-2 p-3">
              <label className="flex items-center gap-2 text-[13px] font-semibold">
                <input type="checkbox" checked={expressive} onChange={(e) => setExpressive(e.target.checked)} /> Biểu cảm theo ngữ cảnh
                <span className="tag tag-primary">Mới</span>
              </label>
              <p className="help mt-1">Tự thay đổi ngữ điệu theo câu hỏi, câu cảm thán, lời thoại, từ ngữ cảm xúc (vui/buồn/giận/sợ) và ngắt nghỉ tự nhiên cuối đoạn. Áp dụng cho giọng Edge Neural.</p>
              {expressive && (
                <div className="mt-2">
                  <Slider label="Mức độ biểu cảm" value={expressiveLevel} min={0.2} max={1} step={0.1} format={(v) => (v < 0.45 ? 'Nhẹ' : v < 0.8 ? 'Vừa' : 'Mạnh')} onChange={setExpressiveLevel} />
                </div>
              )}
            </div>
            {voiceObj?.provider === 'tiktok' && <div className="mt-3"><Alert kind="warning">Giọng TikTok cần <b>sessionid</b> trong Cài đặt. Văn bản dài được cắt ~280 ký tự/lần.</Alert></div>}
            {voice.startsWith('clone:') && <div className="mt-3"><Alert kind="info">Pipeline: Edge TTS đúng ngôn ngữ → chuyển đổi sang giọng clone (cần GPU để nhanh).</Alert></div>}
          </Card>

          <Card title="4. Điều chỉnh" icon={<Settings2 size={14} />}>
            <div className="grid gap-4 md:grid-cols-2">
              <Slider label="Tốc độ" value={rate} min={0.5} max={2.0} step={0.05} format={(v) => `${v.toFixed(2)}×`} onChange={setRate} />
              <Slider label="Âm lượng" value={volume} min={0.2} max={2.0} step={0.05} format={(v) => `${Math.round(v * 100)}%`} onChange={setVolume} />
              <Field label="Cao độ khi đổi tốc độ">
                <Segmented ariaLabel="Cao độ" value={keepPitch ? 'keep' : 'change'} onChange={(v) => setKeepPitch(v === 'keep')} options={[{ value: 'keep', label: 'Giữ nguyên' }, { value: 'change', label: 'Đổi theo tốc độ' }]} />
              </Field>
              <Slider label="Dịch cao độ (nửa cung)" value={pitch} min={-6} max={6} step={1} format={(v) => (v > 0 ? `+${v}` : `${v}`)} onChange={setPitch} />
              <Field label="Định dạng">
                <Segmented ariaLabel="Định dạng file" value={format} onChange={setFormat} options={[{ value: 'mp3', label: 'MP3' }, { value: 'wav', label: 'WAV' }]} />
              </Field>
              <div className="flex flex-col justify-end gap-2 text-[13px]">
                <label className="flex items-center gap-2"><input type="checkbox" checked={makeSrt} onChange={(e) => setMakeSrt(e.target.checked)} /> Tạo phụ đề SRT</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={makeZip} onChange={(e) => setMakeZip(e.target.checked)} /> Nén ZIP</label>
                <label className="flex items-center gap-2"><input type="checkbox" checked={makeM4b} onChange={(e) => setMakeM4b(e.target.checked)} /> Audiobook M4B (có chương)</label>
              </div>
            </div>
          </Card>

          <Card title="5. Cách xuất" icon={<Download size={14} />}>
            <div className="grid gap-2 text-[13px]" role="radiogroup" aria-label="Cách xuất">
              {isSrtBook && <label className="flex items-center gap-2"><input type="radio" name="mode" checked={mode === 'per_cue'} onChange={() => setMode('per_cue')} /> Theo dòng phụ đề SRT (giữ đúng mốc thời gian)</label>}
              <label className="flex items-center gap-2"><input type="radio" name="mode" checked={mode === 'per_chapter'} onChange={() => setMode('per_chapter')} /> Mỗi chương một file</label>
              <label className="flex items-center gap-2"><input type="radio" name="mode" checked={mode === 'merged'} onChange={() => setMode('merged')} /> Gộp toàn bộ thành một file</label>
              <label className="flex items-center gap-2"><input type="radio" name="mode" checked={mode === 'range'} onChange={() => setMode('range')} /> Khoảng chương / gộp theo nhóm</label>
              {mode === 'range' && (
                <div className="ml-6 flex flex-wrap items-center gap-2 text-xs text-fg-muted">
                  Từ <input className="input !h-8 !w-20" type="number" min={1} aria-label="Từ chương" value={rangeStart} onChange={(e) => setRangeStart(Number(e.target.value))} />
                  đến <input className="input !h-8 !w-20" type="number" min={1} aria-label="Đến chương" value={rangeEnd} onChange={(e) => setRangeEnd(Number(e.target.value))} />
                  · gộp mỗi <input className="input !h-8 !w-20" type="number" min={0} aria-label="Gộp mỗi N chương" value={mergeEvery} onChange={(e) => setMergeEvery(Number(e.target.value))} /> chương (0 = một file)
                  {!rangeOk && <span className="w-full text-danger">Khoảng chương không hợp lệ (1 ≤ từ ≤ đến ≤ {book?.chapters.length ?? 0}).</span>}
                </div>
              )}
            </div>
            <button className="btn-primary btn-lg mt-4 w-full" onClick={submit} disabled={!canSubmit} title="Ctrl+Enter">
              {running ? <Loader2 size={18} className="animate-spin" /> : <Play size={18} />} Tạo giọng nói
              <span className="kbd ml-1 hidden md:inline">Ctrl+↵</span>
            </button>
          </Card>

          {latest && (
            <Card title="Job gần nhất" right={<span className="flex items-center gap-2"><StatusTag status={latest.status} />{running && <button className="btn-danger btn-sm" onClick={() => cancel(latest.id)}><SquareIcon size={12} /> Hủy</button>}</span>}>
              <div className="mb-2 truncate text-xs text-fg-muted">{String(latest.params?.title ?? '')}</div>
              {(running || latest.status === 'error') && <ProgressBar value={latest.progress} label={latest.message} status={latest.status} />}
              {latest.status === 'error' && <div className="mt-2"><Alert kind="danger">{latest.message}</Alert></div>}
              {latest.status === 'done' && latest.result ? <ResultView r={latest.result as TtsResult} /> : null}
            </Card>
          )}
        </div>
      </div>
    </div>
  )
}

function ResultView({ r }: { r: TtsResult }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
        <span className="tabular-nums">{r.outputs.length} file · {fmtTime(r.duration)}</span>
        <button className="chip ml-auto" onClick={() => safeCall(api.openPath(r.out_dir), 'Không mở được thư mục')}><FolderOpen size={12} /> Mở thư mục</button>
        {r.zip && <a className="chip" href={api.fileUrl(r.zip)} target="_blank" rel="noreferrer">ZIP</a>}
      </div>
      <div className="list max-h-64 overflow-auto">
        {r.outputs.map((o) => (
          <div key={o.path} className="flex flex-col gap-1.5 border-b border-line px-3 py-2 last:border-b-0">
            <div className="flex items-center gap-2 text-[13px]">
              <span className="truncate font-semibold">{o.name}</span>
              <span className="text-[11px] text-fg-muted tabular-nums">{fmtTime(o.duration)}</span>
              {o.srt && <a className="tag tag-info ml-auto" href={api.fileUrl(o.srt)} target="_blank" rel="noreferrer">SRT</a>}
            </div>
            {o.kind !== 'm4b' && <audio className="h-9 w-full" controls preload="none" src={api.fileUrl(o.path)} />}
          </div>
        ))}
      </div>
    </div>
  )
}
