import type { ReactNode } from 'react'
import type { JobStatus } from '../lib/api'

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="mb-5 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-2xl font-extrabold tracking-tight">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-muted">{subtitle}</p>}
      </div>
      {right}
    </div>
  )
}

export function ProgressBar({ value, label, status }: { value: number; label?: string; status?: JobStatus }) {
  const pct = Math.round((value ?? 0) * 100)
  const color =
    status === 'error' ? 'bg-err' : status === 'cancelled' ? 'bg-muted' : status === 'done' ? 'bg-ok' : 'bg-accent'
  return (
    <div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-line">
        <div className={`h-full ${color} transition-all`} style={{ width: `${pct}%` }} />
      </div>
      {label !== undefined && (
        <div className="mt-1 flex justify-between text-[11px] text-muted">
          <span className="truncate">{label}</span>
          <span>{pct}%</span>
        </div>
      )}
    </div>
  )
}

export function StatusTag({ status }: { status: JobStatus }) {
  const map: Record<JobStatus, [string, string]> = {
    queued: ['Chờ', 'bg-line text-muted'],
    running: ['Đang chạy', 'bg-accent/20 text-accent'],
    done: ['Xong', 'bg-ok/15 text-ok'],
    error: ['Lỗi', 'bg-err/15 text-err'],
    cancelled: ['Đã hủy', 'bg-line text-muted'],
  }
  const [label, cls] = map[status]
  return <span className={`tag ${cls}`}>{label}</span>
}

export function Slider({
  label,
  value,
  min,
  max,
  step,
  format,
  onChange,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  format?: (v: number) => string
  onChange: (v: number) => void
}) {
  return (
    <div>
      <div className="mb-1 flex justify-between text-xs">
        <span className="font-semibold uppercase tracking-wide text-muted">{label}</span>
        <span className="font-mono">{format ? format(value) : value}</span>
      </div>
      <input
        type="range"
        className="w-full"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  )
}

export function Empty({ children }: { children: ReactNode }) {
  return <div className="rounded-xl border border-dashed border-line p-8 text-center text-sm text-muted">{children}</div>
}

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
