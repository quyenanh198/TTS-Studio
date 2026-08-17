import { useEffect, useRef, useState } from 'react'
import { Cpu, Download, Loader2, Mic, Mic2, Play, Plus, Smile, Square, Trash2, Upload, Users } from 'lucide-react'
import { api, type CloneStatus, type EmotionSample, type F5Status, type Job, type VoiceProfile } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { toastError, toastOk } from '../store/ui'
import { Alert, Card, EmptyState, Field, LangBadge, PageHeader, ProgressBar, Segmented, VoiceAvatar, fmtBytes } from '../components/ui'

const PREVIEW_LANGS: [string, string][] = [['vi', 'Việt'], ['en', 'English'], ['zh', 'Trung'], ['ja', 'Nhật'], ['ko', 'Hàn'], ['fr', 'Pháp'], ['de', 'Đức'], ['es', 'T. Ban Nha']]
const EMOTIONS: [string, string][] = [['neutral', 'Kể chuyện'], ['sad', 'Buồn'], ['happy', 'Vui'], ['angry', 'Giận'], ['fear', 'Sợ / hồi hộp'], ['calm', 'Nhẹ nhàng']]
const emotionLabel = (id: string) => EMOTIONS.find(([e]) => e === id)?.[1] ?? id
/** Suggested lines to read when recording a sample — F5 needs the exact transcript of the clip. */
const SCRIPTS: Record<string, string> = {
  neutral: 'Xin chào, tôi là người kể chuyện của bạn. Hôm nay chúng ta sẽ cùng nhau bước vào một câu chuyện mới, và tôi hy vọng bạn sẽ thích nó.',
  sad: 'Tôi đứng lặng nhìn theo bóng người khuất dần cuối con đường, lòng nặng trĩu một nỗi buồn không tên.',
  happy: 'Tuyệt vời quá! Cuối cùng chúng ta cũng làm được rồi, tôi vui không thể tả nổi!',
  angry: 'Đủ rồi! Tôi không thể chịu đựng thêm một lời dối trá nào nữa, đừng nói thêm gì cả!',
  fear: 'Có tiếng bước chân sau lưng... tôi nín thở, tim đập thình thịch trong bóng tối.',
  calm: 'Nhẹ nhàng thôi, hít một hơi thật sâu, mọi chuyện rồi sẽ ổn cả, tôi hứa với bạn.',
}
type Engine = 'seedvc' | 'f5vi'

export default function ClonePage() {
  const [status, setStatus] = useState<CloneStatus | null>(null)
  const [f5, setF5] = useState<F5Status | null>(null)
  const [profiles, setProfiles] = useState<VoiceProfile[] | null>(null)
  const installJob = useJobs(selectJobsByKind('clone_install'))[0]
  const f5Job = useJobs(selectJobsByKind('f5_install'))[0]
  const installing = !!installJob && (installJob.status === 'running' || installJob.status === 'queued')
  const f5Installing = !!f5Job && (f5Job.status === 'running' || f5Job.status === 'queued')

  const refresh = async () => {
    const [s, f, p] = await Promise.all([api.cloneStatus(), api.f5Status().catch(() => null), api.profiles()])
    setStatus(s)
    setF5(f)
    setProfiles(p)
    window.dispatchEvent(new Event('profiles-changed')) // VoicePicker on the TTS page refreshes its clone list
  }
  useEffect(() => { refresh().catch((e) => toastError(e)) }, [])
  const prevInstall = useRef<string | undefined>(undefined)
  const prevF5 = useRef<string | undefined>(undefined)
  useEffect(() => {
    if (prevInstall.current && prevInstall.current !== 'done' && installJob?.status === 'done') refresh().catch(() => undefined)
    prevInstall.current = installJob?.status
  }, [installJob?.status])
  useEffect(() => {
    if (prevF5.current && prevF5.current !== 'done' && f5Job?.status === 'done') refresh().catch(() => undefined)
    prevF5.current = f5Job?.status
  }, [f5Job?.status])

  return (
    <div className="mx-auto max-w-[1440px] p-6">
      <PageHeader title="Clone giọng" subtitle="Một mẫu giọng 10–25 giây → dùng cho mọi ngôn ngữ (Seed-VC), hoặc giọng Việt có cảm xúc, chạy offline (F5-TTS Việt)" />
      <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div className="flex flex-col gap-4">
          <Card title="Engine 1 · Seed-VC (đa ngôn ngữ)" icon={<Cpu size={14} />}>
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
              <b className="text-fg">Cách hoạt động.</b> Văn bản → giọng Edge cùng ngôn ngữ &amp; giới tính → chuyển đổi chất giọng (voice conversion, zero-shot) → file cuối mang âm sắc của mẫu. Không phụ thuộc ngôn ngữ.
            </div>
          </Card>

          <Card title="Engine 2 · F5-TTS Việt (offline, có cảm xúc)" icon={<Smile size={14} />}>
            {f5 ? (
              <>
                <Alert kind={f5.installed && f5.models_ready ? (f5.device === 'cuda' ? 'success' : 'warning') : 'warning'}>{f5.message}</Alert>
                <div className="mt-2 text-xs text-fg-muted">
                  Model: {f5.models_ready ? 'đã tải' : 'chưa tải (~1.3 GB)'} · Thiết bị: {f5.device === 'cuda' ? `GPU (${f5.torch.device_name})` : 'CPU (chậm)'}
                </div>
                {!(f5.installed && f5.models_ready) && (
                  <button className="btn-primary mt-3" disabled={f5Installing} onClick={() => api.installF5().catch((e) => toastError(e))}>
                    {f5Installing ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />} Cài đặt F5-TTS Việt {f5.torch.installed ? '(~1.5 GB)' : '(kèm PyTorch, ~3–4 GB)'}
                  </button>
                )}
                {f5Job && f5Job.status !== 'done' && <div className="mt-3"><ProgressBar value={f5Job.progress} label={f5Job.message} status={f5Job.status} /></div>}
                <div className="subcard mt-3 text-xs leading-relaxed text-fg-muted">
                  <b className="text-fg">Cách hoạt động.</b> Đọc thẳng tiếng Việt bằng giọng của mẫu (zero-shot). Cảm xúc lấy từ chính mẫu tham chiếu: thêm mẫu <i>Buồn / Vui / Giận / Sợ / Nhẹ nhàng</i> cho profile, app tự chọn mẫu phù hợp cho từng câu theo ngữ cảnh.
                  <br /><b className="text-fg">Lưu ý.</b> {f5.license}
                </div>
              </>
            ) : <div className="text-sm text-fg-muted">Đang kiểm tra…</div>}
          </Card>

          <NewProfile onCreated={() => refresh()} />
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-2 text-[15px] font-bold tracking-tight"><Users size={16} className="text-secondary-fg" /> Voice profiles {profiles && <span className="tag tag-muted">{profiles.length}</span>}</div>
          {profiles === null && <div className="card"><div className="skeleton h-4 w-40" /></div>}
          {profiles && profiles.length === 0 && (
            <EmptyState icon={<Mic2 size={20} />} title="Chưa có giọng clone" hint='Tạo profile ở bên trái, sau đó chọn "Giọng clone" trong trang Tạo giọng nói.' />
          )}
          {profiles?.map((p) => (
            <ProfileCard key={p.id} p={p} installed={p.engine === 'f5vi' ? !!(f5?.installed && f5?.models_ready) : !!status?.installed} onChanged={() => refresh()} />
          ))}
        </div>
      </div>
    </div>
  )
}

/** Shared mic recorder + file picker (used for the profile reference and for emotion samples). */
function useAudioInput(maxSecs: number) {
  const [file, setFile] = useState<File | null>(null)
  const [recording, setRecording] = useState(false)
  const [secs, setSecs] = useState(0)
  const recRef = useRef<MediaRecorder | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const timerRef = useRef<number | null>(null)

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
  useEffect(() => { if (recording && secs >= maxSecs) stopRec() }, [secs, recording]) // eslint-disable-line react-hooks/exhaustive-deps
  return { file, setFile, recording, secs, startRec, stopRec }
}

function AudioInput({ a, maxSecs, disabled }: { a: ReturnType<typeof useAudioInput>; maxSecs: number; disabled?: boolean }) {
  const fileRef = useRef<HTMLInputElement>(null)
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button className="btn-outline" onClick={() => fileRef.current?.click()} disabled={a.recording || disabled}><Upload size={15} /> Tải file</button>
      <input ref={fileRef} type="file" accept="audio/*,video/*" className="hidden" onChange={(e) => a.setFile(e.target.files?.[0] ?? null)} />
      {!a.recording
        ? <button className="btn-outline" onClick={a.startRec} disabled={disabled}><Mic size={15} /> Ghi âm</button>
        : <button className="btn-danger" onClick={a.stopRec}><Square size={14} /> Dừng ({a.secs}s / {maxSecs}s)</button>}
      {a.file && <span className="truncate text-xs text-fg-muted">{a.file.name} · {fmtBytes(a.file.size)}</span>}
    </div>
  )
}

function NewProfile({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState('')
  const [gender, setGender] = useState<'female' | 'male'>('female')
  const [language, setLanguage] = useState('vi')
  const [engine, setEngine] = useState<Engine>('seedvc')
  const [refText, setRefText] = useState('')
  const [busy, setBusy] = useState(false)
  const audio = useAudioInput(25)
  const file = audio.file

  const submit = async () => {
    if (!file || !name.trim()) return
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('name', name.trim()); fd.append('gender', gender); fd.append('language', engine === 'f5vi' ? 'vi' : language)
      fd.append('engine', engine); fd.append('ref_text', refText.trim()); fd.append('file', file)
      await api.createProfile(fd)
      toastOk('Đã tạo voice profile', name.trim())
      setName(''); audio.setFile(null); setRefText(''); onCreated()
    } catch (e) { toastError(e, 'Không tạo được profile') } finally { setBusy(false) }
  }

  return (
    <Card title="Tạo voice profile" icon={<Plus size={14} />}>
      <div className="grid gap-3.5">
        <Field label="Engine">
          <Segmented ariaLabel="Engine" value={engine} onChange={setEngine} options={[{ value: 'seedvc', label: 'Seed-VC · đa ngôn ngữ' }, { value: 'f5vi', label: 'F5-TTS Việt · cảm xúc' }]} />
        </Field>
        <Field label="Tên giọng"><input className="input" placeholder="vd: Giọng của tôi" value={name} onChange={(e) => setName(e.target.value)} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Giới tính">
            <Segmented ariaLabel="Giới tính" value={gender} onChange={setGender} options={[{ value: 'female', label: 'Nữ' }, { value: 'male', label: 'Nam' }]} />
          </Field>
          <Field label="Ngôn ngữ chính">
            {engine === 'f5vi'
              ? <div className="input flex items-center text-fg-muted">Tiếng Việt</div>
              : <select className="input" value={language} onChange={(e) => setLanguage(e.target.value)} aria-label="Ngôn ngữ chính">{PREVIEW_LANGS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}
          </Field>
        </div>
        <Field label={engine === 'f5vi' ? 'Mẫu giọng kể chuyện (3–12 giây)' : 'Mẫu giọng (10–25 giây)'} help={engine === 'f5vi' ? 'Nói tiếng Việt rõ ràng, giọng trung tính. Mẫu dài sẽ tự cắt còn 12 giây.' : 'Một người nói, không nhạc nền. File dài sẽ tự cắt còn 25 giây đầu.'}>
          {engine === 'f5vi' && (
            <div className="subcard mb-2 text-xs leading-relaxed">
              <span className="text-fg-muted">Bấm Ghi âm và đọc câu này:</span>
              <div className="mt-1 font-medium text-fg">“{SCRIPTS.neutral}”</div>
              <button className="chip mt-1.5" onClick={() => setRefText(SCRIPTS.neutral)}>Dùng câu này làm lời thoại</button>
            </div>
          )}
          <AudioInput a={audio} maxSecs={engine === 'f5vi' ? 12 : 25} />
        </Field>
        {engine === 'f5vi' && (
          <Field label="Lời thoại trong mẫu (nên nhập chính xác)" help="F5-TTS cần đúng lời của đoạn ghi âm. Nếu tải file của riêng bạn, hãy gõ lại lời; để trống thì app tự nhận dạng bằng Whisper (tải ~460 MB lần đầu, có thể sai vài từ).">
            <textarea className="input min-h-[64px]" placeholder="vd: xin chào, hôm nay tôi sẽ kể cho các bạn nghe một câu chuyện." value={refText} onChange={(e) => setRefText(e.target.value)} />
          </Field>
        )}
        <button className="btn-primary" onClick={submit} disabled={busy || !file || !name.trim()}>
          {busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Tạo profile
        </button>
      </div>
    </Card>
  )
}

function ProfileCard({ p, installed, onChanged }: { p: VoiceProfile; installed: boolean; onChanged: () => void }) {
  const previews = useJobs(selectJobsByKind('clone_preview')).filter((j) => j.params?.profile === p.id)
  const [playing, setPlaying] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const isF5 = p.engine === 'f5vi'
  const jobFor = (key: string): Job | undefined => previews.find((j) => j.params?.lang === key)

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
  const preview = async (key: string) => {
    const j = jobFor(key)
    if (j?.status === 'done' && j.result) return play((j.result as { url: string }).url, key)
    try {
      if (isF5) await api.previewProfile(p.id, 'vi', key.replace(/^emo:/, ''))
      else await api.previewProfile(p.id, key)
    } catch (e) { toastError(e) }
  }
  const remove = async () => {
    if (!confirm(`Xóa voice profile "${p.name}"?`)) return
    try { await api.deleteProfile(p.id); toastOk('Đã xóa profile', p.name); onChanged() } catch (e) { toastError(e) }
  }

  const chips: [string, string][] = isF5 ? EMOTIONS.map(([e, l]) => [`emo:${e}`, l]) : PREVIEW_LANGS
  const have = new Set((p.samples ?? []).map((s) => s.emotion))

  return (
    <div className="card">
      <div className="flex items-start gap-3">
        <VoiceAvatar gender={p.gender} provider="clone" name={p.name} size={40} />
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="truncate font-semibold">{p.name}</span>
            <span className="tag tag-muted">{p.gender === 'female' ? 'Nữ' : 'Nam'}</span>
            <LangBadge lang={p.language} />
            <span className={`tag ${isF5 ? 'tag-primary' : 'tag-muted'}`}>{isF5 ? 'F5-TTS Việt' : 'Seed-VC'}</span>
            <button className="chip ml-auto" onClick={() => play(`/api/system/file?path=${encodeURIComponent(p.ref_path)}`, 'ref')} aria-pressed={playing === 'ref'}>
              {playing === 'ref' ? <Square size={12} /> : <Play size={12} />} Mẫu gốc
            </button>
            <button className="btn-icon btn-icon-sm hover:text-danger" aria-label={`Xóa ${p.name}`} onClick={remove}><Trash2 size={15} /></button>
          </div>
          <div className="mt-0.5 font-mono text-[11px] text-fg-subtle">clone:{p.id} · {new Date(p.created_at).toLocaleString('vi-VN')}</div>
          <div className="mt-2.5 flex flex-wrap gap-1.5" role="group" aria-label={isF5 ? 'Nghe thử theo cảm xúc' : 'Nghe thử theo ngôn ngữ'}>
            {chips.map(([key, label]) => {
              const j = jobFor(key)
              const busy = !!j && (j.status === 'running' || j.status === 'queued')
              const done = j?.status === 'done'
              const emo = key.replace(/^emo:/, '')
              const fallback = isF5 && !have.has(emo)
              return (
                <button key={key} className={`chip ${done ? 'chip-primary' : ''}`} disabled={!installed || busy}
                  title={!installed ? 'Cần cài engine' : fallback ? `Chưa có mẫu "${label}" — sẽ dùng mẫu kể chuyện` : `Nghe thử ${label}`}
                  aria-pressed={playing === key} onClick={() => preview(key)}>
                  {busy ? <Loader2 size={12} className="animate-spin" /> : playing === key ? <Square size={12} /> : <Play size={12} />}
                  {label}{fallback && <span className="text-fg-subtle">*</span>}
                </button>
              )
            })}
          </div>
          {previews.filter((j) => j.status === 'running').map((j) => <div key={j.id} className="mt-2"><ProgressBar value={j.progress} label={j.message} status={j.status} /></div>)}
          {previews.filter((j) => j.status === 'error').slice(0, 1).map((j) => <div key={j.id} className="mt-2"><Alert kind="danger">{j.message}</Alert></div>)}
          {isF5 && <SampleManager p={p} onChanged={onChanged} onPlay={play} playing={playing} />}
        </div>
      </div>
    </div>
  )
}

function SampleManager({ p, onChanged, onPlay, playing }: { p: VoiceProfile; onChanged: () => void; onPlay: (url: string, key: string) => void; playing: string | null }) {
  const [open, setOpen] = useState(false)
  const [emotion, setEmotion] = useState('sad')
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const audio = useAudioInput(12)
  const samples: EmotionSample[] = p.samples ?? []

  const add = async () => {
    if (!audio.file) return
    setBusy(true)
    try {
      const fd = new FormData()
      fd.append('emotion', emotion); fd.append('text', text.trim()); fd.append('file', audio.file)
      await api.addSample(p.id, fd)
      toastOk('Đã thêm mẫu cảm xúc', emotionLabel(emotion))
      audio.setFile(null); setText(''); onChanged()
    } catch (e) { toastError(e, 'Không thêm được mẫu') } finally { setBusy(false) }
  }
  const remove = async (emo: string) => {
    try { await api.deleteSample(p.id, emo); onChanged() } catch (e) { toastError(e) }
  }

  return (
    <div className="subcard mt-3">
      <div className="flex items-center gap-2 text-xs font-semibold"><Smile size={13} className="text-secondary-fg" /> Bộ mẫu cảm xúc <span className="tag tag-muted">{samples.length}/{EMOTIONS.length}</span>
        <button className="chip ml-auto" onClick={() => setOpen((o) => !o)} aria-expanded={open}><Plus size={12} /> Thêm mẫu</button>
      </div>
      {samples.length > 0 && (
        <ul className="mt-2 grid gap-1">
          {samples.map((s) => (
            <li key={s.emotion} className="flex items-center gap-2 text-xs">
              <button className="chip" onClick={() => onPlay(`/api/system/file?path=${encodeURIComponent(s.wav)}`, `s:${s.emotion}`)} aria-pressed={playing === `s:${s.emotion}`}>
                {playing === `s:${s.emotion}` ? <Square size={11} /> : <Play size={11} />} {emotionLabel(s.emotion)}
              </button>
              <span className="text-fg-subtle">{s.duration.toFixed(1)}s</span>
              <span className="min-w-0 flex-1 truncate text-fg-muted" title={s.text}>“{s.text}”</span>
              {s.emotion !== 'neutral' && <button className="btn-icon btn-icon-sm hover:text-danger" aria-label={`Xóa mẫu ${emotionLabel(s.emotion)}`} onClick={() => remove(s.emotion)}><Trash2 size={13} /></button>}
            </li>
          ))}
        </ul>
      )}
      {open && (
        <div className="mt-3 grid gap-2.5">
          <Field label="Cảm xúc">
            <select className="input" value={emotion} onChange={(e) => setEmotion(e.target.value)} aria-label="Cảm xúc">{EMOTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
          </Field>
          <Field label="Mẫu 3–12 giây" help="Đọc đúng cảm xúc đó (buồn thì chậm, trầm; giận thì gằn, mạnh…). Câu ngắn, rõ, không nhạc nền.">
            <div className="subcard mb-2 text-xs leading-relaxed">
              <span className="text-fg-muted">Gợi ý câu để đọc ({emotionLabel(emotion)}):</span>
              <div className="mt-1 font-medium text-fg">“{SCRIPTS[emotion]}”</div>
              <button className="chip mt-1.5" onClick={() => setText(SCRIPTS[emotion])}>Dùng câu này làm lời thoại</button>
            </div>
            <AudioInput a={audio} maxSecs={12} />
          </Field>
          <Field label="Lời thoại trong mẫu (nên nhập chính xác)" help="Để trống thì app tự nhận dạng bằng Whisper.">
            <input className="input" value={text} onChange={(e) => setText(e.target.value)} placeholder="vd: sao lại thế này, tôi không tin nổi nữa..." />
          </Field>
          <div className="flex gap-2">
            <button className="btn-primary" onClick={add} disabled={busy || !audio.file}>{busy ? <Loader2 size={15} className="animate-spin" /> : <Plus size={15} />} Lưu mẫu</button>
            <button className="btn-outline" onClick={() => setOpen(false)}>Đóng</button>
          </div>
        </div>
      )}
    </div>
  )
}
