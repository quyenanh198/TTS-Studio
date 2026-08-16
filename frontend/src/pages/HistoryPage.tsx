import { useMemo, useState } from 'react'
import { FolderOpen, History as HistoryIcon, Trash2, XCircle } from 'lucide-react'
import { api, safeCall, type Job } from '../lib/api'
import { useJobs, selectAllJobs } from '../store/jobs'
import { EmptyState, PageHeader, ProgressBar, StatusTag, fmtTime } from '../components/ui'

const KIND_LABEL: Record<string, string> = {
  tts: 'Tạo giọng nói',
  transcript: 'Transcript',
  clone_preview: 'Clone preview',
  clone_install: 'Cài clone',
  ffmpeg_install: 'Cài FFmpeg',
  asr_model: 'Tải model ASR',
  gpu_install: 'Cài CUDA libs',
}
type Filter = 'all' | 'active' | 'done' | 'error'

interface TtsResult {
  outputs?: { path: string; name: string; duration?: number }[]
  out_dir?: string
  zip?: string | null
  duration?: number
}

export default function HistoryPage() {
  const jobs = useJobs(selectAllJobs)
  const remove = useJobs((s) => s.remove)
  const cancel = useJobs((s) => s.cancel)
  const [filter, setFilter] = useState<Filter>('all')

  const shown = useMemo(() => jobs.filter((j) => {
    if (filter === 'active') return j.status === 'queued' || j.status === 'running'
    if (filter === 'done') return j.status === 'done'
    if (filter === 'error') return j.status === 'error' || j.status === 'cancelled'
    return true
  }), [jobs, filter])

  const clearFinished = async () => {
    const finished = jobs.filter((j) => j.status !== 'queued' && j.status !== 'running')
    if (!finished.length || !confirm(`Xóa ${finished.length} job đã kết thúc khỏi lịch sử? (không xóa file đã xuất)`)) return
    for (const j of finished) await remove(j.id)
  }

  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader
        title="Lịch sử"
        subtitle="Tất cả job đã chạy, đang chạy và kết quả"
        right={<button className="btn-ghost btn-sm" onClick={clearFinished} disabled={!jobs.some((j) => j.status !== 'queued' && j.status !== 'running')}><Trash2 size={13} /> Dọn job đã xong</button>}
      />
      <div className="mb-4 flex flex-wrap gap-1.5" role="group" aria-label="Lọc">
        {([['all', 'Tất cả'], ['active', 'Đang chạy'], ['done', 'Xong'], ['error', 'Lỗi / hủy']] as [Filter, string][]).map(([v, l]) => (
          <button key={v} className={`chip ${filter === v ? 'chip-active' : ''}`} aria-pressed={filter === v} onClick={() => setFilter(v)}>{l}</button>
        ))}
      </div>
      {shown.length === 0 ? (
        <EmptyState icon={<HistoryIcon size={20} />} title={jobs.length ? 'Không có job phù hợp bộ lọc' : 'Chưa có job nào'} hint={jobs.length ? undefined : 'Mọi tác vụ (tạo giọng, transcript, tải model…) sẽ hiện ở đây kèm tiến độ và kết quả.'} />
      ) : (
        <div className="flex flex-col gap-2.5">
          {shown.map((j) => <JobRow key={j.id} job={j} onRemove={() => remove(j.id)} onCancel={() => cancel(j.id)} />)}
        </div>
      )}
    </div>
  )
}

function JobRow({ job, onRemove, onCancel }: { job: Job; onRemove: () => void; onCancel: () => void }) {
  const active = job.status === 'queued' || job.status === 'running'
  const res = (job.result ?? {}) as TtsResult
  const title = (job.params?.title as string) || KIND_LABEL[job.kind] || job.kind
  return (
    <div className="card !p-4">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="tag tag-muted">{KIND_LABEL[job.kind] ?? job.kind}</span>
            <span className="truncate text-[13px] font-semibold">{title}</span>
            <StatusTag status={job.status} />
            {typeof res.duration === 'number' && res.duration > 0 && <span className="text-[11px] text-fg-muted tabular-nums">{fmtTime(res.duration)}</span>}
          </div>
          <div className="mt-1 text-[11px] text-fg-subtle tabular-nums">{new Date(job.created_at).toLocaleString('vi-VN')} · #{job.id}</div>
          {(active || job.status === 'error') && <div className="mt-2"><ProgressBar value={job.progress} label={job.message} status={job.status} /></div>}
          {job.status === 'done' && res.outputs && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {res.outputs.slice(0, 12).map((o) => <a key={o.path} className="chip" href={api.fileUrl(o.path)} target="_blank" rel="noreferrer" title={o.path}>{o.name}</a>)}
              {res.outputs.length > 12 && <span className="chip">+{res.outputs.length - 12}</span>}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {res.out_dir && <button className="btn-icon" aria-label="Mở thư mục kết quả" title="Mở thư mục" onClick={() => safeCall(api.openPath(res.out_dir!), 'Không mở được thư mục')}><FolderOpen size={16} /></button>}
          {active ? (
            <button className="btn-icon hover:text-danger" aria-label="Hủy job" title="Hủy" onClick={onCancel}><XCircle size={16} /></button>
          ) : (
            <button className="btn-icon hover:text-danger" aria-label="Xóa khỏi lịch sử" title="Xóa khỏi lịch sử" onClick={onRemove}><Trash2 size={16} /></button>
          )}
        </div>
      </div>
    </div>
  )
}
