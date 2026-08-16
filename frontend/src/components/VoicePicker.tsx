import { memo, useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent } from 'react'
import { Flame, Loader2, Play, Search, Square } from 'lucide-react'
import { api, type Voice, type VoiceProfile } from '../lib/api'
import { toastError } from '../store/ui'
import { LangBadge, Skeleton, VoiceAvatar } from './ui'

const LANG_CHIPS: { id: string; label: string }[] = [
  { id: 'all', label: 'Tất cả' },
  { id: 'vi', label: 'Tiếng Việt' },
  { id: 'en', label: 'English' },
  { id: 'zh', label: 'Trung' },
  { id: 'ja', label: 'Nhật' },
  { id: 'ko', label: 'Hàn' },
  { id: 'other', label: 'Khác' },
]
const MAIN = new Set(['vi', 'en', 'zh', 'ja', 'ko'])
const PROVIDER_CHIPS: { id: string; label: string }[] = [
  { id: 'all', label: 'Mọi nguồn' },
  { id: 'edge', label: 'Edge Neural' },
  { id: 'tiktok', label: 'TikTok' },
  { id: 'clone', label: 'Giọng clone' },
]
const PROVIDER_LABEL: Record<string, string> = { edge: 'Edge TTS', tiktok: 'TikTok', clone: 'Clone' }

export default function VoicePicker({ value, onChange, compact = false }: { value: string; onChange: (id: string, voice: Voice | null) => void; compact?: boolean }) {
  const [voices, setVoices] = useState<Voice[] | null>(null)
  const [loadErr, setLoadErr] = useState(false)
  const [profiles, setProfiles] = useState<VoiceProfile[]>([])
  const [lang, setLang] = useState('all')
  const [provider, setProvider] = useState('all')
  const [q, setQ] = useState('')
  const [playing, setPlaying] = useState<string | null>(null)
  const [loading, setLoading] = useState<string | null>(null)
  const [focusIdx, setFocusIdx] = useState(0)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const reqRef = useRef(0) // request token: ignore stale preview responses
  const listRef = useRef<HTMLDivElement>(null)

  const load = useCallback(() => {
    setLoadErr(false)
    setVoices(null)
    api.voices().then(setVoices).catch((e) => { setVoices([]); setLoadErr(true); toastError(e, 'Không tải được danh sách giọng') })
    api.profiles().then(setProfiles).catch(() => setProfiles([]))
  }, [])
  useEffect(() => {
    load()
    return () => { audioRef.current?.pause(); audioRef.current = null }
  }, [load])

  const all: Voice[] = useMemo(() => {
    const cloneVoices: Voice[] = profiles.map((p) => ({ id: `clone:${p.id}`, name: p.name, provider: 'clone', locale: p.language, lang: p.language, gender: p.gender, hot: false }))
    return [...cloneVoices, ...(voices ?? [])]
  }, [voices, profiles])

  const filtered = useMemo(() => {
    const qq = q.trim().toLowerCase()
    return all.filter((v) => {
      if (provider !== 'all' && v.provider !== provider) return false
      if (lang !== 'all' && (lang === 'other' ? MAIN.has(v.lang) : v.lang !== lang)) return false
      if (qq && !`${v.name} ${v.id} ${v.locale}`.toLowerCase().includes(qq)) return false
      return true
    })
  }, [all, lang, provider, q])

  const selected = all.find((v) => v.id === value) ?? null

  // Keep the roving focus index on the selected voice when the list changes; scroll it into view.
  useEffect(() => {
    const i = filtered.findIndex((v) => v.id === value)
    setFocusIdx(i >= 0 ? i : 0)
  }, [filtered, value])
  useEffect(() => {
    const el = listRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')
    el?.scrollIntoView({ block: 'nearest' })
  }, [selected?.id, voices])

  const stop = useCallback(() => {
    reqRef.current++
    audioRef.current?.pause()
    audioRef.current = null
    setPlaying(null)
    setLoading(null)
  }, [])

  const preview = useCallback(async (v: Voice) => {
    if (playing === v.id || loading === v.id) return stop()
    stop()
    if (v.provider === 'clone') return
    const token = ++reqRef.current
    setLoading(v.id)
    try {
      const { url } = await api.previewVoice(v.id)
      if (token !== reqRef.current) return // user clicked something else meanwhile
      const a = new Audio(url)
      audioRef.current = a
      a.onended = () => setPlaying((p) => (p === v.id ? null : p))
      await a.play()
      if (token !== reqRef.current) { a.pause(); return }
      setPlaying(v.id)
    } catch (e) {
      if (token === reqRef.current) toastError(e, 'Không nghe thử được')
    } finally {
      if (token === reqRef.current) setLoading(null)
    }
  }, [playing, loading, stop])

  const select = useCallback((v: Voice) => onChange(v.id, v), [onChange])

  const onListKey = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!filtered.length) return
    let next = focusIdx
    if (e.key === 'ArrowDown') next = Math.min(filtered.length - 1, focusIdx + 1)
    else if (e.key === 'ArrowUp') next = Math.max(0, focusIdx - 1)
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = filtered.length - 1
    else if (e.key === 'PageDown') next = Math.min(filtered.length - 1, focusIdx + 10)
    else if (e.key === 'PageUp') next = Math.max(0, focusIdx - 10)
    else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); select(filtered[focusIdx]); return }
    else if (e.key.toLowerCase() === 'p') { e.preventDefault(); preview(filtered[focusIdx]); return }
    else return
    e.preventDefault()
    setFocusIdx(next)
    ;(listRef.current?.children[next] as HTMLElement | undefined)?.focus()
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap gap-1.5" role="group" aria-label="Lọc theo ngôn ngữ">
        {LANG_CHIPS.map((c) => (
          <button key={c.id} className={`chip ${lang === c.id ? 'chip-active' : ''}`} aria-pressed={lang === c.id} onClick={() => setLang(c.id)}>{c.label}</button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Lọc theo nguồn">
          {PROVIDER_CHIPS.map((c) => (
            <button key={c.id} className={`chip ${provider === c.id ? 'chip-active' : ''}`} aria-pressed={provider === c.id} onClick={() => setProvider(c.id)}>{c.label}</button>
          ))}
        </div>
        <div className="relative ml-auto">
          <Search size={14} className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-subtle" aria-hidden />
          <input className="input h-8! w-48! pl-8!" placeholder="Tìm giọng…" aria-label="Tìm giọng" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
      </div>

      <div
        ref={listRef}
        className={`list overflow-auto ${compact ? 'max-h-60' : 'max-h-80'}`}
        role="listbox"
        aria-label="Danh sách giọng đọc — dùng phím mũi tên để duyệt, Enter để chọn, P để nghe thử"
        aria-activedescendant={filtered[focusIdx] ? `voice-${filtered[focusIdx].id}` : undefined}
        onKeyDown={onListKey}
      >
        {voices === null && Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="list-row"><Skeleton className="h-8 w-8" /><div className="flex-1"><Skeleton className="mb-1.5 h-3 w-40" /><Skeleton className="h-2.5 w-24" /></div></div>
        ))}
        {voices !== null && filtered.length === 0 && (
          <div className="p-6 text-center text-xs text-fg-muted">
            {loadErr ? <>Không tải được danh sách giọng. <button className="font-semibold text-secondary-fg underline" onClick={load}>Thử lại</button></> : 'Không có giọng phù hợp bộ lọc.'}
          </div>
        )}
        {filtered.map((v, i) => (
          <VoiceRow
            key={v.id}
            v={v}
            active={v.id === value}
            focusable={i === focusIdx}
            playing={playing === v.id}
            loading={loading === v.id}
            onSelect={select}
            onPreview={preview}
          />
        ))}
      </div>
      <div className="flex items-center gap-2 text-xs text-fg-muted">
        {selected ? (
          <>
            <span>Đã chọn:</span>
            <span className="font-semibold text-fg">{selected.name}</span>
            <span className="font-mono text-fg-subtle">{selected.id}</span>
            {selected.provider !== 'clone' && (
              <button className="btn-ghost btn-sm ml-auto" onClick={() => preview(selected)} aria-pressed={playing === selected.id}>
                {loading === selected.id ? <Loader2 size={13} className="animate-spin" /> : playing === selected.id ? <Square size={12} /> : <Play size={13} />}
                {playing === selected.id ? 'Dừng' : 'Nghe thử giọng đã chọn'}
              </button>
            )}
          </>
        ) : <span>Chưa chọn giọng.</span>}
      </div>
    </div>
  )
}

const VoiceRow = memo(function VoiceRow({ v, active, focusable, playing, loading, onSelect, onPreview }: {
  v: Voice; active: boolean; focusable: boolean; playing: boolean; loading: boolean
  onSelect: (v: Voice) => void; onPreview: (v: Voice) => void
}) {
  return (
    <div
      id={`voice-${v.id}`}
      role="option"
      aria-selected={active}
      tabIndex={focusable ? 0 : -1}
      onClick={() => onSelect(v)}
      className={`list-row cursor-pointer ${active ? 'list-row-active' : 'list-row-hover'}`}
    >
      <VoiceAvatar gender={v.gender} provider={v.provider} name={v.name} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 text-[13px] font-semibold">
          <span className="truncate">{v.name}</span>
          {v.hot && <span className="tag tag-primary" title="Phổ biến"><Flame size={10} className="mr-0.5" />Hot</span>}
        </div>
        <div className="flex items-center gap-1.5 text-[11px] text-fg-muted">
          <LangBadge lang={v.lang} />
          <span className="truncate">{v.locale} · {PROVIDER_LABEL[v.provider]} · {v.gender === 'female' ? 'Nữ' : v.gender === 'male' ? 'Nam' : '—'}</span>
        </div>
      </div>
      {/* Mouse affordance only (tabIndex -1): keyboard users press P or use "Nghe thử giọng đã chọn". */}
      {v.provider !== 'clone' && (
        <button
          tabIndex={-1}
          aria-hidden
          className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border transition-colors duration-[var(--dur)] active:scale-95 ${
            playing ? 'border-primary bg-primary text-primary-fg' : 'border-line-strong text-fg-muted hover:border-primary hover:text-primary'
          }`}
          title={playing ? 'Dừng' : 'Nghe thử'}
          onClick={(e) => { e.stopPropagation(); onPreview(v) }}
        >
          {loading ? <Loader2 size={14} className="animate-spin" /> : playing ? <Square size={12} /> : <Play size={14} />}
        </button>
      )}
    </div>
  )
})
