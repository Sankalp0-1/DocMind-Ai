import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useDocStore, Document } from '../store/docStore'
import ReactMarkdown from 'react-markdown'
import api from '../utils/api'
import {
  Send, Loader2, Play, Pause, SkipForward, Clock,
  BookOpen, ChevronDown, ChevronUp, Trash2, AlertTriangle
} from 'lucide-react'
import { formatDuration, formatDate } from '../utils/format'
import clsx from 'clsx'

// ── Types ────────────────────────────────────────────────────────────────────
interface ChatSource {
  chunk_text: string
  page_or_timestamp: string | null
  score: number
}

interface Message {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: ChatSource[]
  timestamp_hint?: number | null
  isStreaming?: boolean
}

interface TimestampEntry {
  topic: string
  start_seconds: number
  end_seconds: number | null
  text_snippet: string
}

// ── Main Component ────────────────────────────────────────────────────────────
export default function ChatPage() {
  const { docId } = useParams<{ docId: string }>()
  const navigate = useNavigate()
  const { documents, selectDocument, deleteDocument } = useDocStore()

  const doc = documents.find((d) => d.id === Number(docId))

  const [messages, setMessages] = useState<Message[]>([])
  const [input, setInput] = useState('')
  const [isSending, setIsSending] = useState(false)
  const [summary, setSummary] = useState('')
  const [keyTopics, setKeyTopics] = useState<string[]>([])
  const [summaryOpen, setSummaryOpen] = useState(false)
  const [timestamps, setTimestamps] = useState<TimestampEntry[]>([])
  const [tsOpen, setTsOpen] = useState(false)
  const [streamEnabled, setStreamEnabled] = useState(true)

  // Media player
  const audioRef = useRef<HTMLAudioElement | HTMLVideoElement | null>(null)
  const [isPlaying, setIsPlaying] = useState(false)
  const [currentTime, setCurrentTime] = useState(0)
  const [duration, setDuration] = useState(0)

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // ── Init ──────────────────────────────────────────────────────────────────
  useEffect(() => {
    if (doc) {
      selectDocument(doc)
      if (doc.status === 'done') {
        fetchSummary()
        if (doc.file_type !== 'pdf') fetchTimestamps()
      }
    }
  }, [docId, doc?.status])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  // ── API calls ─────────────────────────────────────────────────────────────
  const fetchSummary = async () => {
    try {
      const { data } = await api.get(`/summary/${docId}`)
      setSummary(data.summary)
      setKeyTopics(data.key_topics)
    } catch { }
  }

  const fetchTimestamps = async (topic = '') => {
    try {
      const { data } = await api.get(`/chat/${docId}/timestamps`, {
        params: topic ? { topic } : {},
      })
      setTimestamps(data.timestamps)
    } catch { }
  }

  // ── Send message ──────────────────────────────────────────────────────────
  const sendMessage = useCallback(async () => {
    if (!input.trim() || isSending || !doc) return
    const question = input.trim()
    setInput('')
    setIsSending(true)

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: question,
    }

    const assistantId = crypto.randomUUID()
    const assistantMsg: Message = {
      id: assistantId,
      role: 'assistant',
      content: '',
      isStreaming: true,
    }

    setMessages((m) => [...m, userMsg, assistantMsg])

    try {
      if (streamEnabled) {
        await streamAnswer(question, assistantId)
      } else {
        await batchAnswer(question, assistantId)
      }
    } catch (err: any) {
      setMessages((m) =>
        m.map((msg) =>
          msg.id === assistantId
            ? { ...msg, content: 'Error: ' + (err.message || 'Something went wrong'), isStreaming: false }
            : msg
        )
      )
    } finally {
      setIsSending(false)
    }
  }, [input, isSending, doc, streamEnabled])

  const batchAnswer = async (question: string, assistantId: string) => {
    const { data } = await api.post('/chat/', {
      document_id: Number(docId),
      question,
      stream: false,
    })
    setMessages((m) =>
      m.map((msg) =>
        msg.id === assistantId
          ? { ...msg, content: data.answer, sources: data.sources, timestamp_hint: data.timestamp_hint, isStreaming: false }
          : msg
      )
    )
  }

  const streamAnswer = async (question: string, assistantId: string) => {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 180000)

    const response = await fetch('/api/chat/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: (() => {
  try {
    const raw = localStorage.getItem('auth-storage')
    if (raw) {
      const { state } = JSON.parse(raw)
      return state?.token ? `Bearer ${state.token}` : ''
    }
  } catch { }
  return ''
})(),
      },
      body: JSON.stringify({ document_id: Number(docId), question, stream: true }),
      signal: controller.signal,
    })

    clearTimeout(timeoutId)

    const reader = response.body?.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (reader) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })

      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()
        if (payload === '[DONE]') break

        try {
          const parsed = JSON.parse(payload)
          if (parsed.token) {
            setMessages((m) =>
              m.map((msg) =>
                msg.id === assistantId
                  ? { ...msg, content: msg.content + parsed.token }
                  : msg
              )
            )
          } else if (parsed.meta) {
            setMessages((m) =>
              m.map((msg) =>
                msg.id === assistantId
                  ? {
                      ...msg,
                      sources: parsed.meta.sources,
                      timestamp_hint: parsed.meta.timestamp_hint,
                      isStreaming: false,
                    }
                  : msg
              )
            )
          }
        } catch { }
      }
    }

    setMessages((m) =>
      m.map((msg) =>
        msg.id === assistantId ? { ...msg, isStreaming: false } : msg
      )
    )
  }

  // ── Media player ──────────────────────────────────────────────────────────
  const jumpTo = (seconds: number) => {
    if (audioRef.current) {
      audioRef.current.currentTime = seconds
      audioRef.current.play()
      setIsPlaying(true)
    }
  }

  const togglePlay = () => {
    if (!audioRef.current) return
    if (isPlaying) { audioRef.current.pause(); setIsPlaying(false) }
    else { audioRef.current.play(); setIsPlaying(true) }
  }

  // ── Handle not found ──────────────────────────────────────────────────────
  if (!doc) {
    return (
      <div className="h-full flex items-center justify-center text-zinc-500">
        <p className="text-sm">Document not found.</p>
      </div>
    )
  }

  const isMedia = doc.file_type !== 'pdf'
  const isReady = doc.status === 'done'

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="h-full flex flex-col bg-zinc-950">

      {/* ── Header ── */}
      <div className="px-6 py-3 border-b border-zinc-800 flex items-center justify-between bg-zinc-900">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-white truncate">{doc.original_name}</h2>
          <p className="text-xs text-zinc-500">{formatDate(doc.created_at)} · {doc.status}</p>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-4">
          <button
            onClick={() => setSummaryOpen((o) => !o)}
            disabled={!isReady}
            className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white disabled:opacity-40 transition-colors px-3 py-1.5 rounded-lg hover:bg-zinc-800"
          >
            <BookOpen size={14} /> Summary
          </button>
          {isMedia && (
            <button
              onClick={() => setTsOpen((o) => !o)}
              disabled={!isReady}
              className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-white disabled:opacity-40 transition-colors px-3 py-1.5 rounded-lg hover:bg-zinc-800"
            >
              <Clock size={14} /> Timestamps
            </button>
          )}
          <button
            onClick={async () => { await deleteDocument(doc.id); navigate('/') }}
            className="p-1.5 text-zinc-600 hover:text-red-400 transition-colors rounded-lg hover:bg-zinc-800"
          >
            <Trash2 size={15} />
          </button>
        </div>
      </div>

      {/* ── Summary panel ── */}
      {summaryOpen && summary && (
        <div className="px-6 py-4 border-b border-zinc-800 bg-zinc-900/50">
          <div className="max-w-3xl">
            <h3 className="text-xs font-semibold text-zinc-400 uppercase tracking-wide mb-2">Summary</h3>
            <p className="text-sm text-zinc-300 leading-relaxed">{summary}</p>
            {keyTopics.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-3">
                {keyTopics.map((t) => (
                  <span key={t} className="text-xs bg-violet-500/15 text-violet-300 px-2 py-0.5 rounded-full">
                    {t}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Timestamps panel ── */}
      {tsOpen && isMedia && timestamps.length > 0 && (
        <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/30">
          <div className="flex gap-3 overflow-x-auto pb-1">
            {timestamps.slice(0, 10).map((ts, i) => (
              <button
                key={i}
                onClick={() => jumpTo(ts.start_seconds)}
                className="shrink-0 text-left bg-zinc-800 hover:bg-zinc-700 rounded-xl px-4 py-2.5 transition-colors"
              >
                <p className="text-xs font-mono text-violet-400 mb-0.5">{formatDuration(ts.start_seconds)}</p>
                <p className="text-xs text-zinc-300 max-w-[180px] line-clamp-2">{ts.text_snippet}</p>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* ── Media player ── */}
      {isMedia && isReady && (
        <div className="px-6 py-3 border-b border-zinc-800 bg-zinc-900/20">
          {doc.file_type === 'video' ? (
            <video
              ref={audioRef as React.RefObject<HTMLVideoElement>}
              src={`/api/upload/${doc.id}/stream`}
              className="w-full max-h-40 rounded-lg bg-black"
              onTimeUpdate={(e) => setCurrentTime((e.target as HTMLVideoElement).currentTime)}
              onLoadedMetadata={(e) => setDuration((e.target as HTMLVideoElement).duration)}
              onPlay={() => setIsPlaying(true)}
              onPause={() => setIsPlaying(false)}
              controls
            />
          ) : (
            <div className="flex items-center gap-3">
              <button
                onClick={togglePlay}
                className="w-8 h-8 flex items-center justify-center rounded-full bg-violet-600 hover:bg-violet-500 transition-colors"
              >
                {isPlaying ? <Pause size={14} /> : <Play size={14} />}
              </button>
              <div className="flex-1 h-1.5 bg-zinc-800 rounded-full overflow-hidden cursor-pointer"
                onClick={(e) => {
                  const rect = e.currentTarget.getBoundingClientRect()
                  const pct = (e.clientX - rect.left) / rect.width
                  jumpTo(pct * duration)
                }}
              >
                <div
                  className="h-full bg-violet-500 transition-all"
                  style={{ width: duration ? `${(currentTime / duration) * 100}%` : '0%' }}
                />
              </div>
              <span className="text-xs font-mono text-zinc-500">
                {formatDuration(currentTime)} / {formatDuration(duration)}
              </span>
              <audio
                ref={audioRef as React.RefObject<HTMLAudioElement>}
                src={`/api/upload/${doc.id}/stream`}
                onTimeUpdate={(e) => setCurrentTime((e.target as HTMLAudioElement).currentTime)}
                onLoadedMetadata={(e) => setDuration((e.target as HTMLAudioElement).duration)}
                onPlay={() => setIsPlaying(true)}
                onPause={() => setIsPlaying(false)}
              />
            </div>
          )}
        </div>
      )}

      {/* ── Status banner ── */}
      {!isReady && (
        <div className={clsx(
          'px-6 py-3 flex items-center gap-2 text-sm',
          doc.status === 'failed'
            ? 'bg-red-500/10 text-red-400'
            : 'bg-amber-500/10 text-amber-400'
        )}>
          {doc.status === 'failed'
            ? <><AlertTriangle size={16} /> Processing failed. Please re-upload the file.</>
            : <><Loader2 size={16} className="animate-spin" /> Processing your file — this may take a moment…</>
          }
        </div>
      )}

      {/* ── Messages ── */}
      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {messages.length === 0 && isReady && (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <div className="w-12 h-12 rounded-2xl bg-zinc-800 flex items-center justify-center mb-4">
              <Send size={20} className="text-zinc-500" />
            </div>
            <p className="text-sm font-medium text-zinc-400">Ask anything about this document</p>
            <p className="text-xs text-zinc-600 mt-1">The AI will answer based only on its content</p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={clsx('flex', msg.role === 'user' ? 'justify-end' : 'justify-start')}>
            <div className={clsx(
              'max-w-[80%] rounded-2xl px-4 py-3 text-sm',
              msg.role === 'user'
                ? 'bg-violet-600 text-white rounded-br-sm'
                : 'bg-zinc-800 text-zinc-100 rounded-bl-sm'
            )}>
              {msg.role === 'assistant' ? (
                <>
                  <div className="prose prose-invert prose-sm max-w-none">
                    <ReactMarkdown>{msg.content || ' '}</ReactMarkdown>
                  </div>
                  {msg.isStreaming && (
                    <span className="inline-block w-1.5 h-4 bg-violet-400 animate-pulse rounded-sm ml-0.5" />
                  )}

                  {msg.timestamp_hint != null && (
                    <button
                      onClick={() => jumpTo(msg.timestamp_hint!)}
                      className="mt-2 flex items-center gap-1.5 text-xs text-violet-400 hover:text-violet-300 transition-colors"
                    >
                      <Play size={12} /> Jump to {formatDuration(msg.timestamp_hint)}
                    </button>
                  )}

                  {msg.sources && msg.sources.length > 0 && (
                    <details className="mt-3 group">
                      <summary className="text-xs text-zinc-500 cursor-pointer hover:text-zinc-400 flex items-center gap-1 list-none">
                        <ChevronDown size={12} className="group-open:rotate-180 transition-transform" />
                        {msg.sources.length} source{msg.sources.length > 1 ? 's' : ''}
                      </summary>
                      <div className="mt-2 space-y-1.5">
                        {msg.sources.map((src, i) => (
                          <div key={i} className="bg-zinc-900 rounded-lg px-3 py-2 text-xs text-zinc-400">
                            {src.page_or_timestamp && (
                              <span className="text-violet-400 font-mono text-[10px] mr-2">{src.page_or_timestamp}</span>
                            )}
                            {src.chunk_text}
                          </div>
                        ))}
                      </div>
                    </details>
                  )}
                </>
              ) : (
                msg.content
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* ── Input ── */}
      <div className="px-6 py-4 border-t border-zinc-800 bg-zinc-900">
        <div className="flex items-end gap-3">
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  sendMessage()
                }
              }}
              disabled={!isReady || isSending}
              placeholder={isReady ? 'Ask a question… (Enter to send)' : 'Waiting for processing…'}
              rows={1}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm text-white placeholder-zinc-600 focus:outline-none focus:border-violet-500 transition-colors resize-none"
              style={{ minHeight: '44px', maxHeight: '120px' }}
            />
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setStreamEnabled((s) => !s)}
              className={clsx(
                'text-xs px-3 py-2 rounded-lg transition-colors font-medium',
                streamEnabled
                  ? 'bg-violet-500/20 text-violet-300'
                  : 'bg-zinc-800 text-zinc-500 hover:text-zinc-300'
              )}
              title="Toggle streaming"
            >
              {streamEnabled ? 'Stream' : 'Batch'}
            </button>
            <button
              onClick={sendMessage}
              disabled={!isReady || isSending || !input.trim()}
              className="w-10 h-10 flex items-center justify-center rounded-xl bg-violet-600 hover:bg-violet-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              {isSending ? <Loader2 size={16} className="animate-spin" /> : <Send size={16} />}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
