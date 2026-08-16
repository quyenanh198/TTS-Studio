import { useEffect, useMemo, useRef, useState } from 'react'
import { Loader2, Play, Search, Square } from 'lucide-react'
import { api, type Voice, type VoiceProfile } from '../lib/api'

const LANG_CHIPS: { id: string; label: string }[] = [
  { id: 'all', label: 'Tất cả' },
  { id: 'vi', label: '🇻🇳 Việt' },
  { id: 'en', label: '🇺🇸 English' },
  { id: 'zh', label: '🇨🇳 Trung' },
  { id: 'ja', label: '🇯🇵 Nhật' },
  { id: 'ko', label: '🇰🇷 Hàn' },
  { id: 'other', label: '🌏 Khác' },
]
const MAIN = new Set(['vi', 'en', 'zh', 'ja', 'ko'])

const PROVIDER_CHIPS: { id: string; label: string }[] = [
  { id: 'all', label: 'Mọi nguồn' },
  { id: 'edge', label: 'Edge Neural' },
  { id: 'tiktok', label: 'TikTok' },
  { id: 'clone', label: '🎤 Giọng clone' },
]

export default function VoicePicker({
  value,
  onChange,
  compact = false,
}: {
  value: string
  onChange: (id: string, voice: Voice | null) => void
  compact?: boolean
}) {
  const [voices, setVoices] = useState<Voice[]>([])
  const [profiles, setProfiles] = useState<VoiceProfile[]>([])
  const [lang, setLang] = useState('all')
  const [provider, setProvider] = useState('all')
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')
  const [playing, setPlaying] = useState<string | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  useEffect(() => {
    api.voices().then(setVoices).catch((e) => setErr(String(e)))
    api.profiles().then(setProfiles).catch(() => setProfiles([]))
  }, [])

  const all: Voice[] = useMemo(() => {
    const cloneVoices: Voice[] = profiles.map((p) => ({
      id: `clone:${p.id}`,
      name: p.name,
      provider: 'clone',
      locale: p.language,
      lang: p.language,
      gender: p.gender,
      emoji: '🎤',
      hot: false,
    }))
    return [...cloneVoices, ...voices]
  }, [voices, profiles])

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase()
    return all.filter((v) => {
      if (provider !== 'all' && v.provider !== provider) return false
      if (lang !== 'all') {
        if (lang === 'other' ? MAIN.has(v.lang) : v.lang !== lang) return false
      }
      if (qq && !`${v.name} ${v.id} ${v.locale}`.toLowerCase().includes(qq)) return false
      return true
    })
  }, [all, lang, provider, q])

  const selected = all.find((v) => v.id === value) ?? null

  const stop = () => {
    audioRef.current?.pause()
    audioRef.current = null
    setPlaying(null)
  }

  const preview = async (v: Voice) => {
    if (playing === v.id) return stop()
    stop()
    if (v.provider === 'clone') {
      setErr('Nghe thử giọng clone ở trang Clone giọng')
      return
    }
    setLoading(v.id)
    setErr('')
    try {
      const { url } = await api.previewVoice(v.id)
      const a = new Audio(url)
      audioRef.current = a
      a.onended = () => setPlaying(null)
      await a.play()
      setPlaying(v.id)
    } catch (e) {
      setErr(String(e))
    } finally {
      setLoading(null)
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5">
        {LANG_CHIPS.map((c) => (
          <button key={c.id} className={`chip ${lang === c.id ? 'chip-active' : ''}`} onClick={() => setLang(c.id)}>
            {c.label}
          </button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {PROVIDER_CHIPS.map((c) => (
          <button key={c.id} className={`chip ${provider === c.id ? 'chip-active' : ''}`} onClick={() => setProvider(c.id)}>
            {c.label}
          </button>
        ))}
        <div className="relative ml-auto">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-2.5 text-muted" />
          <input className="input !w-48 !pl-8 !py-1.5" placeholder="Tìm giọng…" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>
      {err && <div className="text-xs text-err">{err}</div>}
      <div className={`overflow-auto rounded-xl border border-line ${compact ? 'max-h-56' : 'max-h-80'}`}>
        {filtered.length === 0 && <div className="p-4 text-center text-xs text-muted">Không có giọng phù hợp</div>}
        {filtered.map((v) => {
          const active = v.id === value
          return (
            <div
              key={v.id}
              onClick={() => onChange(v.id, v)}
              className={`flex cursor-pointer items-center gap-3 border-b border-line/60 px-3 py-2 last:border-b-0 ${
                active ? 'bg-accent/15' : 'hover:bg-panel2'
              }`}
            >
              <div className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-panel2 text-base">{v.emoji ?? '🎙️'}</div>
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 text-sm font-semibold">
                  <span className="truncate">{v.name}</span>
                  {v.hot && <span className="tag bg-err/20 text-err">HOT</span>}
                </div>
                <div className="truncate text-[11px] text-muted">
                  {v.locale} · {v.provider === 'edge' ? 'Edge TTS' : v.provider === 'tiktok' ? 'TikTok' : 'Clone'} ·{' '}
                  {v.gender === 'female' ? 'Nữ' : v.gender === 'male' ? 'Nam' : '—'}
                </div>
              </div>
              <button
                className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border transition ${
                  playing === v.id ? 'border-accent bg-accent text-white' : 'border-line text-muted hover:border-accent hover:text-text'
                }`}
                title="Nghe thử"
                onClick={(e) => {
                  e.stopPropagation()
                  preview(v)
                }}
              >
                {loading === v.id ? <Loader2 size={14} className="animate-spin" /> : playing === v.id ? <Square size={12} /> : <Play size={14} />}
              </button>
            </div>
          )
        })}
      </div>
      {selected && (
        <div className="text-xs text-muted">
          Đã chọn: <span className="font-semibold text-text">{selected.name}</span> ({selected.id})
        </div>
      )}
    </div>
  )
}
