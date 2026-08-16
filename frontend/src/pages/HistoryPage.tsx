import { FolderOpen, Trash2, XCircle } from 'lucide-react'
import { api, type Job } from '../lib/api'
import { useJobs, selectAllJobs } from '../store/jobs'
import { Empty, PageHeader, ProgressBar, StatusTag } from '../components/ui'

const KIND_LABEL: Record<string, string> = {
  tts: 'Tạo giọng nói',
  transcript: 'Transcript',
  clone_preview: 'Clone preview',
  clone_install: 'Cài clone',
  ffmpeg_install: 'Cài FFmpeg',
  asr_model: 'Tải model ASR',
  gpu_install: 'Cài CUDA libs',
}

interface TtsResult {
  outputs?: { path: string; name: string; duration?: number }[]
  out_dir?: string
  zip?: string | null
}

export default function HistoryPage() {
  const jobs = useJobs(selectAllJobs)
  const remove = useJobs((s) => s.remove)
  const cancel = useJobs((s) => s.cancel)

  return (
    <div className="mx-auto max-w-5xl p-6">
      <PageHeader title="Lịch sử" subtitle="Tất cả job đã chạy, đang chạy và kết quả" />
      {jobs.length === 0 ? (
        <Empty>Chưa có job nào.</Empty>
      ) : (
        <div className="flex flex-col gap-3">
          {jobs.map((j) => (
            <JobRow key={j.id} job={j} onRemove={() => remove(j.id)} onCancel={() => cancel(j.id)} />
          ))}
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
    <div className="card">
      <div className="flex items-start gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="tag bg-panel2 text-muted">{KIND_LABEL[job.kind] ?? job.kind}</span>
            <span className="truncate font-semibold">{title}</span>
            <StatusTag status={job.status} />
          </div>
          <div className="mt-1 text-[11px] text-muted">
            {new Date(job.created_at).toLocaleString('vi-VN')} · #{job.id}
          </div>
          {(active || job.status === 'error') && (
            <div className="mt-2">
              <ProgressBar value={job.progress} label={job.message} status={job.status} />
            </div>
          )}
          {job.status === 'done' && res.outputs && (
            <div className="mt-2 flex flex-wrap gap-2">
              {res.outputs.slice(0, 12).map((o) => (
                <a
                  key={o.path}
                  className="chip"
                  href={api.fileUrl(o.path)}
                  target="_blank"
                  rel="noreferrer"
                  title={o.path}
                >
                  {o.name}
                </a>
              ))}
              {res.outputs.length > 12 && <span className="chip">+{res.outputs.length - 12}</span>}
            </div>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-1">
          {res.out_dir && (
            <button className="btn-ghost !px-2" title="Mở thư mục" onClick={() => api.openPath(res.out_dir!)}>
              <FolderOpen size={16} />
            </button>
          )}
          {active ? (
            <button className="btn-danger !px-2" title="Hủy" onClick={onCancel}>
              <XCircle size={16} />
            </button>
          ) : (
            <button className="btn-ghost !px-2" title="Xóa khỏi lịch sử" onClick={onRemove}>
              <Trash2 size={16} />
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
