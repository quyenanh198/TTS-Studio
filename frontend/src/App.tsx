import { useEffect, useState } from 'react'
import { AudioLines, Mic2, FileAudio, Settings as SettingsIcon, History } from 'lucide-react'
import { useJobs, selectActiveJobs } from './store/jobs'
import { useTransfer } from './store/transfer'
import TtsPage from './pages/TtsPage'
import TranscriptPage from './pages/TranscriptPage'
import ClonePage from './pages/ClonePage'
import SettingsPage from './pages/SettingsPage'
import HistoryPage from './pages/HistoryPage'

type Page = 'tts' | 'transcript' | 'clone' | 'history' | 'settings'

const NAV: { id: Page; label: string; icon: typeof AudioLines }[] = [
  { id: 'tts', label: 'Tạo giọng nói', icon: AudioLines },
  { id: 'transcript', label: 'Phụ đề / Transcript', icon: FileAudio },
  { id: 'clone', label: 'Clone giọng', icon: Mic2 },
  { id: 'history', label: 'Lịch sử', icon: History },
  { id: 'settings', label: 'Cài đặt', icon: SettingsIcon },
]

export default function App() {
  const [page, setPage] = useState<Page>('tts')
  const load = useJobs((s) => s.load)
  const connect = useJobs((s) => s.connect)
  const connected = useJobs((s) => s.connected)
  const active = useJobs(selectActiveJobs)

  const setNavigate = useTransfer((s) => s.setNavigate)

  useEffect(() => {
    load().catch(() => undefined)
    connect()
    setNavigate((p) => setPage(p as Page))
  }, [load, connect, setNavigate])

  return (
    <div className="flex h-full">
      <aside className="flex w-60 shrink-0 flex-col border-r border-line bg-panel">
        <div className="flex items-center gap-2 px-5 py-5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-accent to-accent2 text-lg">🎤</div>
          <div>
            <div className="text-base font-extrabold leading-tight">TTS Studio</div>
            <div className="text-[11px] text-muted">Giọng nói · Phụ đề · Clone</div>
          </div>
        </div>
        <nav className="flex flex-col gap-1 px-3">
          {NAV.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              onClick={() => setPage(id)}
              className={`flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm font-semibold transition ${
                page === id ? 'bg-accent/15 text-text' : 'text-muted hover:bg-panel2 hover:text-text'
              }`}
            >
              <Icon size={18} className={page === id ? 'text-accent' : ''} />
              {label}
              {id === 'history' && active.length > 0 && (
                <span className="ml-auto rounded-full bg-accent px-2 py-0.5 text-[10px] font-bold text-white">
                  {active.length}
                </span>
              )}
            </button>
          ))}
        </nav>
        <div className="mt-auto px-5 py-4 text-[11px] text-muted">
          <span className={`mr-1.5 inline-block h-2 w-2 rounded-full ${connected ? 'bg-ok' : 'bg-err'}`} />
          {connected ? 'Backend đã kết nối' : 'Đang kết nối backend…'}
        </div>
      </aside>
      <main className="min-w-0 flex-1 overflow-auto">
        {page === 'tts' && <TtsPage />}
        {page === 'transcript' && <TranscriptPage />}
        {page === 'clone' && <ClonePage />}
        {page === 'history' && <HistoryPage />}
        {page === 'settings' && <SettingsPage />}
      </main>
    </div>
  )
}
