import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'
import { api } from './lib/api'

// Uncaught UI errors → per-session error log on the backend (logs/errors/session-*.log)
window.addEventListener('error', (ev) => {
  api.reportClientError({ message: ev.message || String(ev.error), stack: ev.error?.stack ?? `${ev.filename}:${ev.lineno}:${ev.colno}`, source: 'window.onerror', url: location.hash || location.pathname })
})
window.addEventListener('unhandledrejection', (ev) => {
  const r = ev.reason
  api.reportClientError({ message: r instanceof Error ? r.message : String(r), stack: r instanceof Error ? r.stack ?? '' : '', source: 'unhandledrejection', url: location.hash || location.pathname })
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
