import { useEffect, useRef, useState } from 'react'
import { Cpu, Download, FolderOpen, Monitor, Moon, RefreshCw, Save, SlidersHorizontal, Sun } from 'lucide-react'
import { api, safeCall, type AsrModelInfo, type Settings, type SystemInfo, type Voice } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { toastError, toastOk, useUi } from '../store/ui'
import { Alert, Card, Field, PageHeader, ProgressBar, Segmented, Skeleton, Slider } from '../components/ui'

export default function SettingsPage() {
  const [sys, setSys] = useState<SystemInfo | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [voices, setVoices] = useState<Voice[]>([])
  const [models, setModels] = useState<AsrModelInfo[]>([])
  const [saving, setSaving] = useState(false)
  const [dirty, setDirty] = useState(false)
  const ffJob = useJobs(selectJobsByKind('ffmpeg_install'))[0]
  const theme = useUi((s) => s.theme)
  const setTheme = useUi((s) => s.setTheme)

  const refresh = async () => {
    const [s, st] = await Promise.all([api.system(), api.settings()])
    setSys(s)
    setSettings(st)
    setDirty(false)
  }
  useEffect(() => {
    refresh().catch((e) => toastError(e))
    api.voices().then(setVoices).catch(() => undefined)
    api.asrModels().then(setModels).catch(() => undefined)
  }, [])
  const prevFf = useRef<string | undefined>(undefined)
  useEffect(() => {
    // react only to a live running→done transition, not to a historical job on mount
    if (prevFf.current && prevFf.current !== 'done' && ffJob?.status === 'done') { refresh().catch(() => undefined); toastOk('FFmpeg đã sẵn sàng') }
    prevFf.current = ffJob?.status
  }, [ffJob?.status])

  const save = async () => {
    if (!settings) return
    setSaving(true)
    try { setSettings(await api.saveSettings(settings)); setDirty(false); toastOk('Đã lưu cài đặt') } catch (e) { toastError(e, 'Không lưu được') } finally { setSaving(false) }
  }
  const set = <K extends keyof Settings>(k: K, v: Settings[K]) => { setSettings((s) => (s ? { ...s, [k]: v } : s)); setDirty(true) }
  const ffBusy = ffJob?.status === 'running' || ffJob?.status === 'queued'

  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader title="Cài đặt" subtitle="Hệ thống, giao diện, thư mục xuất, TikTok session, GPU" />

      <Card title="Giao diện" icon={<Monitor size={14} />} className="mb-4">
        <div className="max-w-xs">
          <Segmented ariaLabel="Giao diện" value={theme} onChange={setTheme} options={[
            { value: 'dark', label: <span className="inline-flex items-center gap-1.5"><Moon size={13} /> Tối</span> },
            { value: 'light', label: <span className="inline-flex items-center gap-1.5"><Sun size={13} /> Sáng</span> },
          ]} />
        </div>
      </Card>

      <Card title="Hệ thống" icon={<Cpu size={14} />} className="mb-4" right={<button className="btn-ghost btn-sm" onClick={() => refresh()}><RefreshCw size={13} /> Làm mới</button>}>
        {sys ? (
          <dl className="grid grid-cols-[150px_1fr] gap-x-4 gap-y-2.5 text-[13px]">
            <dt className="text-fg-muted">Nền tảng</dt><dd>{sys.platform} · Python {sys.python}</dd>
            <dt className="text-fg-muted">Thư mục dữ liệu</dt>
            <dd className="flex items-center gap-2"><code className="truncate text-xs">{sys.data_dir}</code><button className="btn-icon btn-icon-sm" aria-label="Mở thư mục dữ liệu" onClick={() => safeCall(api.openPath(sys.data_dir), 'Không mở được thư mục')}><FolderOpen size={14} /></button></dd>
            <dt className="text-fg-muted">GPU</dt>
            <dd>{sys.gpu.name ? <>{sys.gpu.name} · {sys.gpu.vram_mb} MB · <span className={sys.gpu.cuda ? 'text-success' : 'text-warning'}>{sys.gpu.cuda ? 'CUDA sẵn sàng' : 'CUDA chưa sẵn sàng (torch CPU hoặc chưa cài)'}</span></> : <span className="text-fg-muted">Không phát hiện GPU NVIDIA — chạy CPU</span>}</dd>
            <dt className="text-fg-muted">FFmpeg</dt>
            <dd>
              {sys.ffmpeg ? <code className="text-xs text-success">{sys.ffmpeg}</code> : (
                <div className="flex flex-wrap items-center gap-3">
                  <span className="text-warning">Chưa cài</span>
                  <button className="btn-primary btn-sm" disabled={ffBusy} onClick={() => api.installFfmpeg().catch((e) => toastError(e))}><Download size={13} /> Tải FFmpeg tự động</button>
                </div>
              )}
              {ffJob && ffJob.status !== 'done' && <div className="mt-2 max-w-sm"><ProgressBar value={ffJob.progress} label={ffJob.message} status={ffJob.status} /></div>}
            </dd>
            <dt className="text-fg-muted">Module</dt>
            <dd className="flex flex-wrap gap-1.5">{Object.entries(sys.modules).map(([k, v]) => <span key={k} className={`tag ${v ? 'tag-success' : 'tag-muted'}`}>{k}</span>)}</dd>
            <dt className="text-fg-muted">Nhật ký lỗi</dt>
            <dd className="flex flex-col gap-1">
              <div className="flex items-center gap-2">
                <code className="truncate text-xs" title={sys.session_log ?? ''}>{sys.session_log ? sys.session_log.split(/[\\/]/).pop() : 'không khả dụng'}</code>
                {sys.session_log && <button className="btn-ghost btn-sm" onClick={() => safeCall(api.openPath(sys.session_log!), 'Không mở được file log')}><FolderOpen size={13} /> Hiện file phiên này</button>}
                {sys.logs_dir && <button className="btn-ghost btn-sm" onClick={() => safeCall(api.openPath(sys.logs_dir!), 'Không mở được thư mục')}><FolderOpen size={13} /> Thư mục logs</button>}
              </div>
              <span className="text-xs text-fg-muted">Mỗi lần mở app tạo một file <code>logs/errors/session-…log</code> ghi mọi lỗi của phiên (backend, job, giao diện). Gửi file này khi báo lỗi.</span>
            </dd>
          </dl>
        ) : <div className="flex flex-col gap-2"><Skeleton className="h-4 w-72" /><Skeleton className="h-4 w-56" /><Skeleton className="h-4 w-64" /></div>}
      </Card>

      {settings && (
        <Card title="Tùy chọn" icon={<SlidersHorizontal size={14} />}>
          <div className="grid gap-4 md:grid-cols-2">
            <Field label="Thư mục xuất file" className="md:col-span-2">
              <div className="flex gap-2">
                <input className="input" value={settings.output_dir} onChange={(e) => set('output_dir', e.target.value)} />
                <button className="btn-ghost" onClick={() => safeCall(api.openPath(settings.output_dir), 'Không mở được thư mục')} aria-label="Mở thư mục xuất"><FolderOpen size={15} /></button>
              </div>
            </Field>
            <Field label="TikTok sessionid (tùy chọn)" className="md:col-span-2" help={<>Đăng nhập tiktok.com trên trình duyệt → DevTools → Application → Cookies → copy <code>sessionid</code>. Cần để dùng giọng TikTok.</>}>
              <input className="input" type="password" autoComplete="off" placeholder="Dán giá trị cookie sessionid" value={settings.tiktok_session_id} onChange={(e) => set('tiktok_session_id', e.target.value)} />
            </Field>
            <Field label="Định dạng mặc định">
              <Segmented ariaLabel="Định dạng mặc định" value={settings.default_format} onChange={(v) => set('default_format', v)} options={[{ value: 'mp3', label: 'MP3' }, { value: 'wav', label: 'WAV' }]} />
            </Field>
            <Field label="Số job chạy song song" help="Áp dụng sau khi khởi động lại.">
              <input className="input" type="number" min={1} max={8} value={settings.concurrency} onChange={(e) => set('concurrency', Number(e.target.value))} />
            </Field>
            <Field label="Thiết bị ASR (Whisper)">
              <select className="input" value={settings.asr_device} onChange={(e) => set('asr_device', e.target.value)}><option value="auto">Tự động</option><option value="cuda">GPU (CUDA)</option><option value="cpu">CPU</option></select>
            </Field>
            <Field label="Thiết bị Clone giọng">
              <select className="input" value={settings.vc_device} onChange={(e) => set('vc_device', e.target.value)}><option value="auto">Tự động</option><option value="cuda">GPU (CUDA)</option><option value="cpu">CPU</option></select>
            </Field>
            <Field label="Giọng mặc định (trang Tạo giọng nói)" className="md:col-span-2">
              <select className="input" value={settings.default_voice} onChange={(e) => set('default_voice', e.target.value)}>
                {!voices.some((v) => v.id === settings.default_voice) && <option value={settings.default_voice}>{settings.default_voice}</option>}
                {voices.map((v) => <option key={v.id} value={v.id}>{v.name} · {v.locale} · {v.provider === 'edge' ? 'Edge' : v.provider === 'tiktok' ? 'TikTok' : 'Clone'}</option>)}
              </select>
            </Field>
            <Slider label="Tốc độ mặc định" value={settings.default_rate} min={0.5} max={2} step={0.05} format={(v) => `${v.toFixed(2)}×`} onChange={(v) => set('default_rate', v)} />
            <Slider label="Âm lượng mặc định" value={settings.default_volume} min={0.2} max={2} step={0.05} format={(v) => `${Math.round(v * 100)}%`} onChange={(v) => set('default_volume', v)} />
            <Field label="Cao độ khi đổi tốc độ (mặc định)">
              <Segmented ariaLabel="Cao độ mặc định" value={settings.keep_pitch ? 'keep' : 'change'} onChange={(v) => set('keep_pitch', v === 'keep')} options={[{ value: 'keep', label: 'Giữ nguyên' }, { value: 'change', label: 'Đổi theo tốc độ' }]} />
            </Field>
            <Field label="Model Whisper mặc định">
              <select className="input" value={settings.asr_model} onChange={(e) => set('asr_model', e.target.value)}>
                {models.length === 0 && <option value={settings.asr_model}>{settings.asr_model}</option>}
                {models.map((m) => <option key={m.name} value={m.name}>{m.name}{m.downloaded ? ' ✓' : ''} — {m.desc}</option>)}
              </select>
            </Field>
            <Field label="Chất lượng clone (bước diffusion)" className="md:col-span-2">
              <select className="input" value={settings.vc_steps ?? 0} onChange={(e) => set('vc_steps', Number(e.target.value))}>
                <option value={0}>Tự động (25 GPU / 10 CPU)</option><option value={10}>10 — nhanh</option><option value={15}>15</option><option value={25}>25 — cân bằng</option><option value={40}>40 — chất lượng cao (chậm)</option>
              </select>
            </Field>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button className="btn-primary" onClick={save} disabled={saving || !dirty}><Save size={15} /> Lưu cài đặt</button>
            {dirty && <span className="text-xs text-fg-muted">Có thay đổi chưa lưu</span>}
          </div>
        </Card>
      )}
      {sys && !sys.ffmpeg && <div className="mt-4"><Alert kind="warning">FFmpeg là bắt buộc cho mọi tính năng audio. Bấm "Tải FFmpeg tự động" ở trên (≈90 MB).</Alert></div>}
    </div>
  )
}
