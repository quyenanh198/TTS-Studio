import { useEffect, useState } from 'react'
import { Download, FolderOpen, RefreshCw, Save } from 'lucide-react'
import { api, type Settings, type SystemInfo } from '../lib/api'
import { useJobs, selectJobsByKind } from '../store/jobs'
import { PageHeader, ProgressBar } from '../components/ui'

export default function SettingsPage() {
  const [sys, setSys] = useState<SystemInfo | null>(null)
  const [settings, setSettings] = useState<Settings | null>(null)
  const [saving, setSaving] = useState(false)
  const [msg, setMsg] = useState('')
  const ffJobs = useJobs(selectJobsByKind('ffmpeg_install'))
  const ffJob = ffJobs[0]

  const refresh = async () => {
    const [s, st] = await Promise.all([api.system(), api.settings()])
    setSys(s)
    setSettings(st)
  }

  useEffect(() => {
    refresh().catch((e) => setMsg(String(e)))
  }, [])

  useEffect(() => {
    if (ffJob?.status === 'done') refresh().catch(() => undefined)
  }, [ffJob?.status])

  const save = async () => {
    if (!settings) return
    setSaving(true)
    try {
      setSettings(await api.saveSettings(settings))
      setMsg('Đã lưu cài đặt')
    } catch (e) {
      setMsg(String(e))
    } finally {
      setSaving(false)
    }
  }

  const set = <K extends keyof Settings>(k: K, v: Settings[K]) =>
    setSettings((s) => (s ? { ...s, [k]: v } : s))

  return (
    <div className="mx-auto max-w-4xl p-6">
      <PageHeader title="Cài đặt" subtitle="Hệ thống, thư mục xuất, TikTok session, GPU" />

      <section className="card mb-4">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-bold">Hệ thống</h2>
          <button className="btn-ghost" onClick={() => refresh()}>
            <RefreshCw size={14} /> Làm mới
          </button>
        </div>
        {sys ? (
          <dl className="grid grid-cols-[160px_1fr] gap-y-2 text-sm">
            <dt className="text-muted">Nền tảng</dt>
            <dd>{sys.platform} · Python {sys.python}</dd>
            <dt className="text-muted">Thư mục dữ liệu</dt>
            <dd className="flex items-center gap-2">
              <code className="text-xs">{sys.data_dir}</code>
              <button className="btn-ghost !px-2 !py-1" onClick={() => api.openPath(sys.data_dir)}>
                <FolderOpen size={14} />
              </button>
            </dd>
            <dt className="text-muted">GPU</dt>
            <dd>
              {sys.gpu.name ? (
                <>
                  {sys.gpu.name} · {sys.gpu.vram_mb} MB ·{' '}
                  <span className={sys.gpu.cuda ? 'text-ok' : 'text-warn'}>
                    {sys.gpu.cuda ? 'CUDA sẵn sàng' : 'CUDA chưa sẵn sàng (torch CPU hoặc chưa cài)'}
                  </span>
                </>
              ) : (
                <span className="text-muted">Không phát hiện GPU NVIDIA — chạy CPU</span>
              )}
            </dd>
            <dt className="text-muted">FFmpeg</dt>
            <dd>
              {sys.ffmpeg ? (
                <code className="text-xs text-ok">{sys.ffmpeg}</code>
              ) : (
                <div className="flex items-center gap-3">
                  <span className="text-warn">Chưa cài</span>
                  <button
                    className="btn-primary !px-3 !py-1.5"
                    disabled={ffJob?.status === 'running' || ffJob?.status === 'queued'}
                    onClick={() => api.installFfmpeg().catch((e) => setMsg(String(e)))}
                  >
                    <Download size={14} /> Tải FFmpeg tự động
                  </button>
                </div>
              )}
              {ffJob && ffJob.status !== 'done' && (
                <div className="mt-2 w-80">
                  <ProgressBar value={ffJob.progress} label={ffJob.message} status={ffJob.status} />
                </div>
              )}
            </dd>
            <dt className="text-muted">Module</dt>
            <dd className="flex flex-wrap gap-2">
              {Object.entries(sys.modules).map(([k, v]) => (
                <span key={k} className={`tag ${v ? 'bg-ok/15 text-ok' : 'bg-line text-muted'}`}>
                  {k}
                </span>
              ))}
            </dd>
          </dl>
        ) : (
          <div className="text-sm text-muted">Đang tải…</div>
        )}
      </section>

      {settings && (
        <section className="card">
          <h2 className="mb-3 font-bold">Tùy chọn</h2>
          <div className="grid gap-4 md:grid-cols-2">
            <div className="md:col-span-2">
              <label className="label">Thư mục xuất file</label>
              <div className="flex gap-2">
                <input className="input" value={settings.output_dir} onChange={(e) => set('output_dir', e.target.value)} />
                <button className="btn-ghost" onClick={() => api.openPath(settings.output_dir)}>
                  <FolderOpen size={14} />
                </button>
              </div>
            </div>
            <div className="md:col-span-2">
              <label className="label">TikTok sessionid (tùy chọn — cần để dùng giọng TikTok)</label>
              <input
                className="input"
                type="password"
                placeholder="Dán giá trị cookie sessionid từ tiktok.com"
                value={settings.tiktok_session_id}
                onChange={(e) => set('tiktok_session_id', e.target.value)}
              />
              <p className="mt-1 text-xs text-muted">
                Đăng nhập tiktok.com trên trình duyệt → DevTools → Application → Cookies → copy <code>sessionid</code>.
              </p>
            </div>
            <div>
              <label className="label">Định dạng mặc định</label>
              <select className="input" value={settings.default_format} onChange={(e) => set('default_format', e.target.value as 'mp3' | 'wav')}>
                <option value="mp3">MP3</option>
                <option value="wav">WAV</option>
              </select>
            </div>
            <div>
              <label className="label">Số job chạy song song</label>
              <input className="input" type="number" min={1} max={8} value={settings.concurrency} onChange={(e) => set('concurrency', Number(e.target.value))} />
            </div>
            <div>
              <label className="label">Thiết bị ASR (Whisper)</label>
              <select className="input" value={settings.asr_device} onChange={(e) => set('asr_device', e.target.value)}>
                <option value="auto">Tự động</option>
                <option value="cuda">GPU (CUDA)</option>
                <option value="cpu">CPU</option>
              </select>
            </div>
            <div>
              <label className="label">Thiết bị Clone giọng</label>
              <select className="input" value={settings.vc_device} onChange={(e) => set('vc_device', e.target.value)}>
                <option value="auto">Tự động</option>
                <option value="cuda">GPU (CUDA)</option>
                <option value="cpu">CPU</option>
              </select>
            </div>
            <div>
              <label className="label">Chất lượng clone (số bước diffusion)</label>
              <select className="input" value={settings.vc_steps ?? 0} onChange={(e) => set('vc_steps', Number(e.target.value))}>
                <option value={0}>Tự động (25 GPU / 10 CPU)</option>
                <option value={10}>10 — nhanh</option>
                <option value={15}>15</option>
                <option value={25}>25 — cân bằng</option>
                <option value={40}>40 — chất lượng cao (chậm)</option>
              </select>
            </div>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <button className="btn-primary" onClick={save} disabled={saving}>
              <Save size={14} /> Lưu cài đặt
            </button>
            {msg && <span className="text-sm text-muted">{msg}</span>}
          </div>
        </section>
      )}
    </div>
  )
}
