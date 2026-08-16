import type { ReactNode } from 'react'
import { AlertTriangle, CheckCircle2, Info, Mic, User, X, XCircle } from 'lucide-react'
import type { JobStatus } from '../lib/api'
import { useUi, type ToastKind } from '../store/ui'

/* ---------- Page scaffolding ---------- */
export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4">
      <div className="min-w-0">
        <h1 className="text-[22px] font-bold leading-tight tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-[13px] text-fg-muted">{subtitle}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
    </div>
  )
}

export function Card({ title, icon, right, children, className = '' }: { title?: string; icon?: ReactNode; right?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <section className={`card ${className}`}>
      {(title || right) && (
        <div className="card-title">
          {icon && <span className="grid h-6 w-6 place-items-center rounded-md bg-secondary-soft text-secondary-fg">{icon}</span>}
          <span className="min-w-0 flex-1 truncate">{title}</span>
          {right}
        </div>
      )}
      {children}
    </section>
  )
}

export function Field({ label, help, children, className = '' }: { label: string; help?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={className}>
      <label className="label">{label}</label>
      {children}
      {help && <p className="help">{help}</p>}
    </div>
  )
}

export function Segmented<T extends string>({ value, onChange, options, ariaLabel }: { value: T; onChange: (v: T) => void; options: { value: T; label: ReactNode }[]; ariaLabel: string }) {
  return (
    <div className="segmented" role="group" aria-label={ariaLabel}>
      {options.map((o) => (
        <button key={o.value} type="button" aria-pressed={value === o.value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  )
}

/* ---------- Feedback ---------- */
export function ProgressBar({ value, label, status }: { value: number; label?: string; status?: JobStatus }) {
  const pct = Math.round((value ?? 0) * 100)
  const color = status === 'error' ? 'bg-danger' : status === 'cancelled' ? 'bg-fg-subtle' : status === 'done' ? 'bg-success' : 'bg-primary'
  return (
    <div role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={label}>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-surface-3">
        <div className={`h-full ${color} transition-[width] duration-300`} style={{ width: `${pct}%` }} />
      </div>
      {label !== undefined && (
        <div className="mt-1 flex justify-between gap-3 text-[11px] text-fg-muted">
          <span className="truncate">{label}</span>
          <span className="tabular-nums">{pct}%</span>
        </div>
      )}
    </div>
  )
}

export function StatusTag({ status }: { status: JobStatus }) {
  const map: Record<JobStatus, [string, string]> = {
    queued: ['Chờ', 'tag-muted'],
    running: ['Đang chạy', 'tag-secondary'],
    done: ['Xong', 'tag-success'],
    error: ['Lỗi', 'tag-danger'],
    cancelled: ['Đã hủy', 'tag-muted'],
  }
  const [label, cls] = map[status]
  return <span className={`tag ${cls}`}>{label}</span>
}

export function Alert({ kind = 'info', children }: { kind?: ToastKind; children: ReactNode }) {
  const Icon = kind === 'danger' ? XCircle : kind === 'warning' ? AlertTriangle : kind === 'success' ? CheckCircle2 : Info
  return (
    <div className={`alert alert-${kind}`} role={kind === 'danger' ? 'alert' : 'status'}>
      <Icon size={14} className="mt-0.5 shrink-0" />
      <div className="min-w-0">{children}</div>
    </div>
  )
}

export function EmptyState({ icon, title, hint, action }: { icon?: ReactNode; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="grid place-items-center rounded-[var(--radius-lg)] border border-dashed border-line-strong px-6 py-10 text-center">
      {icon && <div className="mb-3 grid h-11 w-11 place-items-center rounded-full bg-surface-2 text-fg-muted">{icon}</div>}
      <div className="text-sm font-semibold">{title}</div>
      {hint && <div className="mt-1 max-w-sm text-xs text-fg-muted">{hint}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function Skeleton({ className = '' }: { className?: string }) {
  return <div className={`skeleton ${className}`} aria-hidden />
}

export function ToastHost() {
  const toasts = useUi((s) => s.toasts)
  const dismiss = useUi((s) => s.dismiss)
  if (!toasts.length) return null
  return (
    <div className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[360px] max-w-[calc(100vw-2rem)] flex-col gap-2" aria-live="polite">
      {toasts.map((t) => {
        const Icon = t.kind === 'danger' ? XCircle : t.kind === 'warning' ? AlertTriangle : t.kind === 'success' ? CheckCircle2 : Info
        const color = t.kind === 'danger' ? 'text-danger' : t.kind === 'warning' ? 'text-warning' : t.kind === 'success' ? 'text-success' : 'text-info'
        return (
          <div key={t.id} className="toast-enter pointer-events-auto flex items-start gap-2.5 rounded-[var(--radius-md)] border border-line bg-surface p-3 shadow-[var(--shadow-md)]">
            <Icon size={16} className={`mt-0.5 shrink-0 ${color}`} />
            <div className="min-w-0 flex-1">
              <div className="text-sm font-semibold">{t.title}</div>
              {t.detail && <div className="mt-0.5 break-words text-xs text-fg-muted">{t.detail}</div>}
            </div>
            <button className="btn-icon btn-icon-sm -mr-1 -mt-1" aria-label="Đóng" onClick={() => dismiss(t.id)}>
              <X size={14} />
            </button>
          </div>
        )
      })}
    </div>
  )
}

/* ---------- Controls ---------- */
export function Slider({ label, value, min, max, step, format, onChange }: { label: string; value: number; min: number; max: number; step: number; format?: (v: number) => string; onChange: (v: number) => void }) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="font-semibold text-fg-muted">{label}</span>
        <span className="font-mono tabular-nums text-fg">{format ? format(value) : value}</span>
      </div>
      <input type="range" className="h-8 w-full" aria-label={label} min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
    </div>
  )
}

/* ---------- Domain visuals ---------- */
const LANG_LABEL: Record<string, string> = { vi: 'VI', en: 'EN', zh: 'ZH', ja: 'JA', ko: 'KO', th: 'TH', fr: 'FR', de: 'DE', es: 'ES', pt: 'PT', ru: 'RU', id: 'ID', it: 'IT', hi: 'HI', ar: 'AR' }
export function LangBadge({ lang, className = '' }: { lang: string; className?: string }) {
  return <span className={`tag tag-muted font-mono ${className}`}>{LANG_LABEL[lang] ?? (lang || '??').toUpperCase().slice(0, 3)}</span>
}

export function VoiceAvatar({ gender, provider, name, size = 32 }: { gender: string; provider: string; name: string; size?: number }) {
  const bg = provider === 'clone' ? 'bg-primary-soft text-primary' : gender === 'male' ? 'bg-secondary-soft text-secondary-fg' : 'bg-info-soft text-info'
  return (
    <div className={`grid shrink-0 place-items-center rounded-lg text-[12px] font-bold ${bg}`} style={{ width: size, height: size }} aria-hidden>
      {provider === 'clone' ? <Mic size={size * 0.5} /> : name?.trim()?.[0]?.toUpperCase() || <User size={size * 0.5} />}
    </div>
  )
}

/* ---------- Formatters ---------- */
export function fmtTime(sec: number): string {
  if (!isFinite(sec)) return '0:00'
  const s = Math.floor(sec % 60)
  const m = Math.floor((sec / 60) % 60)
  const h = Math.floor(sec / 3600)
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`
}
export function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1 << 20) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1 << 30) return `${(n / (1 << 20)).toFixed(1)} MB`
  return `${(n / (1 << 30)).toFixed(2)} GB`
}
export const fmtNum = (n: number) => n.toLocaleString('vi-VN')
