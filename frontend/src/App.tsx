import { useEffect, useState } from 'react'
import { AudioLines, AudioWaveform, FileAudio, History, Mic2, Moon, Settings as SettingsIcon, Sun } from 'lucide-react'
import { useJobs, selectActiveJobs } from './store/jobs'
import { useTransfer } from './store/transfer'
import { useUi } from './store/ui'
import { ToastHost } from './components/ui'
import TtsPage from './pages/TtsPage'
import TranscriptPage from './pages/TranscriptPage'
import ClonePage from './pages/ClonePage'
import SettingsPage from './pages/SettingsPage'
import HistoryPage from './pages/HistoryPage'

type Page = 'tts' | 'transcript' | 'clone' | 'history' | 'settings'

const NAV: { id: Page; label: string; icon: typeof AudioLines; hint: string }[] = [
  { id: 'tts', label: 'Tạo giọng nói', icon: AudioLines, hint: 'Văn bản, ebook → audio' },
  { id: 'transcript', label: 'Phụ đề / Transcript', icon: FileAudio, hint: 'Audio → SRT, LRC' },
  { id: 'clone', label: 'Clone giọng', icon: Mic2, hint: 'Giọng của bạn, mọi ngôn ngữ' },
  { id: 'history', label: 'Lịch sử', icon: History, hint: 'Job & kết quả' },
]

export default function App() {
  const [page, setPage] = useState<Page>('tts')
  const load = useJobs((s) => s.load)
  const connect = useJobs((s) => s.connect)
  const connected = useJobs((s) => s.connected)
  const active = useJobs(selectActiveJobs)
  const setNavigate = useTransfer((s) => s.setNavigate)
  const theme = useUi((s) => s.theme)
  const toggleTheme = useUi((s) => s.toggleTheme)

  useEffect(() => {
    load().catch(() => undefined)
    connect()
    setNavigate((p) => setPage(p as Page))
  }, [load, connect, setNavigate])

  // Keyboard: Ctrl+1..5 switch pages
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!e.ctrlKey || e.altKey) return
      const idx = Number(e.key) - 1
      const all: Page[] = ['tts', 'transcript', 'clone', 'history', 'settings']
      if (idx >= 0 && idx < all.length) {
        e.preventDefault()
        setPage(all[idx])
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  return (
    <div className="flex h-full">
      <aside className="flex w-[var(--sidebar-w)] shrink-0 flex-col border-r border-line bg-surface" aria-label="Điều hướng chính">
        <div className="flex items-center gap-2.5 px-4 pb-4 pt-5">
          <div className="grid h-9 w-9 place-items-center rounded-[var(--radius-md)] bg-primary text-primary-fg shadow-[var(--shadow-glow)]">
            <AudioWaveform size={18} strokeWidth={2.4} />
          </div>
          <div className="min-w-0">
            <div className="text-[15px] font-bold leading-tight tracking-tight">TTS Studio</div>
            <div className="truncate text-[11px] text-fg-muted">Giọng nói · Phụ đề · Clone</div>
          </div>
        </div>

        <nav className="flex flex-col gap-0.5 px-2" aria-label="Trang">
          {NAV.map(({ id, label, icon: Icon, hint }, i) => {
            const isActive = page === id
            return (
              <button
                key={id}
                onClick={() => setPage(id)}
                aria-current={isActive ? 'page' : undefined}
                title={`${label} (Ctrl+${i + 1})`}
                className={`group flex min-h-11 items-center gap-3 rounded-[var(--radius-md)] px-3 py-2 text-left transition-colors duration-[var(--dur)] ${
                  isActive ? 'bg-secondary-soft text-fg' : 'text-fg-muted hover:bg-surface-2 hover:text-fg'
                }`}
              >
                <Icon size={18} className={`shrink-0 ${isActive ? 'text-secondary-fg' : ''}`} />
                <span className="min-w-0 flex-1">
                  <span className="block text-[13px] font-semibold leading-tight">{label}</span>
                  <span className="block truncate text-[11px] text-fg-subtle group-hover:text-fg-muted">{hint}</span>
                </span>
                {id === 'history' && active.length > 0 && (
                  <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-bold leading-none text-primary-fg" aria-label={`${active.length} job đang chạy`}>
                    {active.length}
                  </span>
                )}
              </button>
            )
          })}
        </nav>

        <div className="mt-auto flex flex-col gap-1 px-2 pb-3">
          <button
            onClick={() => setPage('settings')}
            aria-current={page === 'settings' ? 'page' : undefined}
            className={`flex min-h-10 items-center gap-3 rounded-[var(--radius-md)] px-3 text-[13px] font-semibold transition-colors duration-[var(--dur)] ${
              page === 'settings' ? 'bg-secondary-soft text-fg' : 'text-fg-muted hover:bg-surface-2 hover:text-fg'
            }`}
          >
            <SettingsIcon size={18} className={page === 'settings' ? 'text-secondary-fg' : ''} /> Cài đặt
          </button>
          <div className="mt-1 flex items-center justify-between px-3 py-1.5 text-[11px] text-fg-muted">
            <span className="flex items-center gap-1.5">
              <span className={`inline-block h-2 w-2 rounded-full ${connected ? 'bg-success' : 'bg-danger animate-pulse'}`} aria-hidden />
              {connected ? 'Đã kết nối' : 'Đang kết nối…'}
            </span>
            <button className="btn-icon btn-icon-sm" onClick={toggleTheme} aria-label={theme === 'dark' ? 'Chuyển sang giao diện sáng' : 'Chuyển sang giao diện tối'} title="Đổi giao diện sáng/tối">
              {theme === 'dark' ? <Sun size={15} /> : <Moon size={15} />}
            </button>
          </div>
        </div>
      </aside>

      <main className="min-w-0 flex-1 overflow-auto bg-bg" id="main">
        {page === 'tts' && <TtsPage />}
        {page === 'transcript' && <TranscriptPage />}
        {page === 'clone' && <ClonePage />}
        {page === 'history' && <HistoryPage />}
        {page === 'settings' && <SettingsPage />}
      </main>
      <ToastHost />
    </div>
  )
}
