import { Outlet, Link, useNavigate, useParams } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { useDocStore } from '../store/docStore'
import { useEffect } from 'react'
import { FileText, Mic, Video, LogOut, Plus, Brain, Loader2, AlertCircle } from 'lucide-react'
import { formatBytes, formatDate } from '../utils/format'
import clsx from 'clsx'

export default function Layout() {
  const { user, logout } = useAuthStore()
  const { documents, fetchDocuments, selected, selectDocument } = useDocStore()
  const navigate = useNavigate()
  const params = useParams()

  useEffect(() => { fetchDocuments() }, [])

  const handleLogout = () => { logout(); navigate('/login') }

  const icon = (type: string) => {
    if (type === 'pdf') return <FileText size={16} className="text-rose-400" />
    if (type === 'audio') return <Mic size={16} className="text-violet-400" />
    return <Video size={16} className="text-sky-400" />
  }

  const statusBadge = (status: string) => {
    const cls: Record<string, string> = {
      done: 'bg-emerald-500/20 text-emerald-300',
      processing: 'bg-amber-500/20 text-amber-300',
      pending: 'bg-zinc-500/20 text-zinc-400',
      failed: 'bg-red-500/20 text-red-400',
    }
    const icons: Record<string, JSX.Element> = {
      processing: <Loader2 size={10} className="animate-spin" />,
      failed: <AlertCircle size={10} />,
    }
    return (
      <span className={clsx('flex items-center gap-1 text-[10px] px-1.5 py-0.5 rounded font-medium', cls[status])}>
        {icons[status]} {status}
      </span>
    )
  }

  return (
    <div className="flex h-screen bg-zinc-950 text-zinc-100 overflow-hidden font-sans">
      {/* ── Sidebar ── */}
      <aside className="w-72 flex flex-col border-r border-zinc-800 bg-zinc-900">
        {/* Logo */}
        <div className="px-5 py-4 border-b border-zinc-800 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-violet-500 to-rose-500 flex items-center justify-center">
            <Brain size={18} />
          </div>
          <div>
            <p className="text-sm font-semibold tracking-tight">DocMind AI</p>
            <p className="text-[11px] text-zinc-500">{user?.username}</p>
          </div>
        </div>

        {/* Upload CTA */}
        <div className="px-4 pt-4">
          <Link
            to="/"
            className="flex items-center justify-center gap-2 w-full py-2 rounded-lg bg-violet-600 hover:bg-violet-500 text-sm font-medium transition-colors"
          >
            <Plus size={16} /> Upload File
          </Link>
        </div>

        {/* Document list */}
        <div className="flex-1 overflow-y-auto mt-3 px-2 space-y-1 pb-4">
          {documents.length === 0 && (
            <p className="text-xs text-zinc-600 text-center mt-8 px-4">
              Upload a PDF, audio, or video to get started
            </p>
          )}
          {documents.map((doc) => {
            const active = params.docId === String(doc.id)
            return (
              <button
                key={doc.id}
                onClick={() => { selectDocument(doc); navigate(`/chat/${doc.id}`) }}
                className={clsx(
                  'w-full text-left px-3 py-2.5 rounded-lg transition-colors group',
                  active ? 'bg-zinc-800' : 'hover:bg-zinc-800/50'
                )}
              >
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 shrink-0">{icon(doc.file_type)}</span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs font-medium truncate text-zinc-200">
                      {doc.original_name}
                    </p>
                    <p className="text-[10px] text-zinc-500 mt-0.5">
                      {formatBytes(doc.file_size_bytes)} · {formatDate(doc.created_at).split(',')[0]}
                    </p>
                    <div className="mt-1">{statusBadge(doc.status)}</div>
                  </div>
                </div>
              </button>
            )
          })}
        </div>

        {/* Footer */}
        <div className="px-4 py-3 border-t border-zinc-800">
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
          >
            <LogOut size={14} /> Sign out
          </button>
        </div>
      </aside>

      {/* ── Main content ── */}
      <main className="flex-1 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
