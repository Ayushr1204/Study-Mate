import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Check, MessageSquarePlus, PanelRight, Pencil, SendHorizontal, Sparkles, Trash2, X } from 'lucide-react'
import { Markdown } from '../components/Markdown'
import { RunPanel } from '../components/RunPanel'
import { Button, Chip, EmptyState, ErrorBanner, Spinner } from '../components/ui'
import { cx } from '../components/styles'
import { useApp } from '../context/app-context'
import { useAsync } from '../hooks/useAsync'
import { formatTime, relativeTime } from '../lib/format'
import { api } from '../services/api'
import type { ChatMessage, Thread } from '../types'

const SUGGESTIONS = [
  'Explain CPU scheduling.',
  'I prefer explanations using real-world analogies.',
  'Quiz me on deadlock with 3 questions',
  'Explain binary search with a code example',
]

function ThreadItem({ thread, active, onChanged, onDeleted }: { thread: Thread; active: boolean; onChanged: () => void; onDeleted: () => void }) {
  const [editing, setEditing] = useState(false)
  const [title, setTitle] = useState(thread.title)
  const [confirming, setConfirming] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const save = async () => {
    const next = title.trim()
    if (!next || next === thread.title) {
      setEditing(false)
      setTitle(thread.title)
      return
    }
    try {
      await api.renameThread(thread.id, next)
      setEditing(false)
      onChanged()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Rename failed')
    }
  }
  const remove = async () => {
    try {
      await api.deleteThread(thread.id)
      onDeleted()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed')
      setConfirming(false)
    }
  }

  if (editing) {
    return (
      <li className="px-2 py-1">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void save()
          }}
          className="flex items-center gap-1"
        >
          <input
            autoFocus
            value={title}
            maxLength={80}
            onChange={(e) => setTitle(e.target.value)}
            onKeyDown={(e) => e.key === 'Escape' && (setEditing(false), setTitle(thread.title))}
            aria-label="Conversation title"
            className="min-w-0 flex-1 rounded border border-line-strong bg-canvas px-2 py-1 text-sm"
          />
          <button type="submit" aria-label="Save title" className="rounded p-1 text-ok hover:bg-hover"><Check className="size-4" /></button>
          <button type="button" aria-label="Cancel" onClick={() => (setEditing(false), setTitle(thread.title))} className="rounded p-1 text-muted hover:bg-hover"><X className="size-4" /></button>
        </form>
        {error && <p className="mt-1 text-xs text-danger">{error}</p>}
      </li>
    )
  }

  return (
    <li className="group relative">
      <Link
        to={`/chat/${thread.id}`}
        aria-current={active ? 'page' : undefined}
        className={cx('block rounded-md px-3 py-2 pr-16 transition-colors', active ? 'bg-hover text-fg' : 'text-muted hover:bg-hover/60 hover:text-fg')}
      >
        <span className="block truncate text-sm">{thread.title}</span>
        <span className="block text-[11px] text-faint">{relativeTime(thread.updated_at)}</span>
      </Link>
      <div className={cx('absolute top-1.5 right-1.5 flex items-center gap-0.5', confirming ? '' : 'opacity-0 group-focus-within:opacity-100 group-hover:opacity-100')}>
        {confirming ? (
          <>
            <button onClick={() => void remove()} className="rounded bg-danger/15 px-1.5 py-1 text-[11px] font-medium text-danger hover:bg-danger/25">Delete?</button>
            <button onClick={() => setConfirming(false)} aria-label="Cancel delete" className="rounded p-1 text-muted hover:bg-hover"><X className="size-3.5" /></button>
          </>
        ) : (
          <>
            <button onClick={() => setEditing(true)} aria-label={`Rename ${thread.title}`} className="rounded p-1 text-muted hover:bg-line hover:text-fg"><Pencil className="size-3.5" /></button>
            <button onClick={() => setConfirming(true)} aria-label={`Delete ${thread.title}`} className="rounded p-1 text-muted hover:bg-line hover:text-danger"><Trash2 className="size-3.5" /></button>
          </>
        )}
      </div>
      {error && <p className="px-3 pb-1 text-xs text-danger">{error}</p>}
    </li>
  )
}

function Bubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === 'user'
  const meta = message.meta
  return (
    <div className={cx('fade-in flex', isUser ? 'justify-end' : 'justify-start')}>
      <div className={cx('max-w-[min(46rem,100%)] min-w-0', isUser ? 'items-end' : 'w-full')}>
        <div className={cx('rounded-xl px-4 py-3 text-sm', isUser ? 'rounded-br-sm bg-accent-soft text-fg' : 'rounded-bl-sm border border-line bg-surface')}>
          {isUser ? <p className="break-words whitespace-pre-wrap">{message.content}</p> : <Markdown>{message.content}</Markdown>}
        </div>
        <div className={cx('mt-1 flex flex-wrap items-center gap-1.5 px-1 text-[11px] text-faint', isUser && 'justify-end')}>
          <time dateTime={message.created_at ?? undefined}>{formatTime(message.created_at)}</time>
          {!isUser && meta.intent && <Chip tone="info">{meta.intent}</Chip>}
          {!isUser && meta.provider === 'offline' && <Chip tone="warn" title={meta.fallback_reason ?? 'Answered without a language model'}>offline fallback</Chip>}
          {!isUser && (meta.memory_fields_used?.length ?? 0) > 0 && (
            <Chip tone="accent" title={`Used long-term memory: ${meta.memory_fields_used?.join(', ')}`}>memory × {meta.memory_fields_used?.length}</Chip>
          )}
        </div>
      </div>
    </div>
  )
}

function Typing() {
  return (
    <div className="flex" role="status" aria-label="StudyMate is thinking">
      <div className="flex items-center gap-1.5 rounded-xl rounded-bl-sm border border-line bg-surface px-4 py-3.5">
        {[0, 1, 2].map((i) => (
          <span key={i} className="typing-dot size-1.5 rounded-full bg-muted" style={{ animationDelay: `${i * 0.18}s` }} />
        ))}
      </div>
    </div>
  )
}

export function ChatPage() {
  const { threadId } = useParams()
  const navigate = useNavigate()
  const { userId } = useApp()
  const threads = useAsync(() => api.listThreads(), [userId])
  const detail = useAsync(() => (threadId ? api.getThread(threadId) : Promise.resolve(null)), [threadId, userId])
  // useAsync keeps the previous result while reloading, so only trust data that belongs to the open thread.
  const current = detail.data && detail.data.id === threadId ? detail.data : null
  const execution = current?.last_execution ?? null
  const memory = useAsync(() => api.memory(), [userId, execution?.request_id])

  const [draft, setDraft] = useState('')
  const [pending, setPending] = useState<string | null>(null)
  const [sendError, setSendError] = useState<unknown>(null)
  const [lastText, setLastText] = useState('')
  const [showRun, setShowRun] = useState(true)
  const endRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)

  const messages = useMemo(() => current?.messages ?? [], [current])
  const activeThread = threads.data?.find((t) => t.id === threadId)

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [messages.length, pending])

  useEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 200)}px`
  }, [draft])

  const send = async (text: string) => {
    const content = text.trim()
    if (!content || pending) return
    setPending(content)
    setLastText(content)
    setSendError(null)
    setDraft('')
    try {
      const res = await api.chat(threadId ?? null, content)
      if (!threadId) navigate(`/chat/${res.thread_id}`)
      else detail.reload()
      threads.reload()
    } catch (e) {
      setSendError(e)
      detail.reload() // the checkpoint may already hold the user's turn - show the truth
      threads.reload()
    } finally {
      setPending(null)
    }
  }

  const newChat = () => {
    setSendError(null)
    navigate('/chat')
    taRef.current?.focus()
  }

  const showEmpty = messages.length === 0 && !pending

  return (
    <div className="flex h-full min-h-0">
      {/* Conversations */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-line bg-surface lg:flex" aria-label="Conversations">
        <div className="p-3">
          <Button variant="secondary" className="w-full justify-start" onClick={newChat}>
            <MessageSquarePlus className="size-4" /> New conversation
          </Button>
        </div>
        <ul className="min-h-0 flex-1 space-y-0.5 overflow-y-auto px-2 pb-3">
          {threads.loading && !threads.data && <li className="px-3 py-2"><Spinner label="Loading…" /></li>}
          {threads.data?.length === 0 && <li className="px-3 py-6 text-center text-xs text-faint">No conversations yet. Each one gets its own LangGraph thread and checkpoint history.</li>}
          {threads.data?.map((t) => (
            <ThreadItem
              key={t.id}
              thread={t}
              active={t.id === threadId}
              onChanged={() => (threads.reload(), detail.reload())}
              onDeleted={() => {
                threads.reload()
                if (t.id === threadId) navigate('/chat')
              }}
            />
          ))}
        </ul>
        {threads.error && <div className="p-3"><ErrorBanner error={threads.error} onRetry={threads.reload} /></div>}
      </aside>

      {/* Conversation */}
      <section className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center justify-between gap-3 border-b border-line px-4">
          <div className="flex min-w-0 items-center gap-3">
            <select
              aria-label="Switch conversation"
              value={threadId ?? ''}
              onChange={(e) => navigate(e.target.value ? `/chat/${e.target.value}` : '/chat')}
              className="max-w-40 rounded border border-line bg-surface px-2 py-1 text-xs lg:hidden"
            >
              <option value="">New conversation</option>
              {threads.data?.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
            </select>
            <h1 className="truncate text-sm font-medium">{activeThread?.title ?? (threadId ? 'Conversation' : 'New conversation')}</h1>
            {threadId && <span className="hidden font-mono text-[11px] text-faint sm:inline" title="LangGraph thread_id">thread {threadId.slice(0, 8)}</span>}
          </div>
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" className="lg:hidden" onClick={newChat}><MessageSquarePlus className="size-4" /></Button>
            {threadId && <Link to={`/inspector?thread=${threadId}`} className="rounded px-2 py-1 text-xs text-muted hover:bg-hover hover:text-fg">Inspect state</Link>}
            <Button size="sm" variant="ghost" onClick={() => setShowRun((v) => !v)} aria-pressed={showRun} aria-label="Toggle run details" className="hidden xl:inline-flex">
              <PanelRight className="size-4" />
            </Button>
          </div>
        </header>

        <div className="min-h-0 flex-1 overflow-y-auto">
          <div className="mx-auto flex max-w-3xl flex-col gap-4 px-4 py-6">
            {detail.loading && threadId && !current && <Spinner label="Restoring conversation from its checkpoint…" />}
            {detail.error && <ErrorBanner error={detail.error} onRetry={detail.reload} />}
            {showEmpty && !(threadId && !current) && !detail.error && (
              <EmptyState
                icon={<Sparkles className="size-7" />}
                title="What do you want to study?"
                action={
                  <div className="flex max-w-xl flex-wrap justify-center gap-2">
                    {SUGGESTIONS.map((s) => (
                      <button key={s} onClick={() => { setDraft(s); taRef.current?.focus() }} className="rounded-full border border-line bg-surface px-3 py-1.5 text-xs text-muted transition-colors hover:border-line-strong hover:text-fg">
                        {s}
                      </button>
                    ))}
                  </div>
                }
              >
                Ask for an explanation, a quiz, or paste notes to summarize. Tell me how you like to learn and I will remember it across conversations.
              </EmptyState>
            )}
            {messages.map((m, i) => <Bubble key={m.id ?? i} message={m} />)}
            {pending && (
              <>
                <Bubble message={{ id: null, index: null, role: 'user', content: pending, created_at: new Date().toISOString(), meta: {} }} />
                <Typing />
              </>
            )}
            {!!sendError && (
              <div className="space-y-2">
                <ErrorBanner error={sendError} />
                <Button size="sm" onClick={() => void send(lastText)}>Retry last message</Button>
              </div>
            )}
            <div ref={endRef} />
          </div>
        </div>

        <form
          className="shrink-0 border-t border-line bg-surface px-4 py-3"
          onSubmit={(e) => {
            e.preventDefault()
            void send(draft)
          }}
        >
          <div className="mx-auto flex max-w-3xl items-end gap-2">
            <textarea
              ref={taRef}
              value={draft}
              rows={1}
              maxLength={30000}
              disabled={!!pending}
              placeholder="Ask a question, request a quiz, or paste notes to summarize…"
              aria-label="Message"
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault()
                  void send(draft)
                }
              }}
              className="max-h-52 min-h-10 flex-1 resize-none rounded-md border border-line bg-canvas px-3 py-2.5 text-sm placeholder:text-faint focus:border-accent focus:outline-none disabled:opacity-60"
            />
            <Button type="submit" variant="primary" className="h-10 w-10 px-0" disabled={!draft.trim()} loading={!!pending} aria-label="Send message">
              {!pending && <SendHorizontal className="size-4" />}
            </Button>
          </div>
          <p className="mx-auto mt-1.5 max-w-3xl text-[11px] text-faint">Enter to send · Shift+Enter for a new line</p>
        </form>
      </section>

      {/* Run details */}
      {showRun && (
        <aside className="hidden w-80 shrink-0 overflow-y-auto border-l border-line bg-surface p-4 xl:block" aria-label="Run details">
          <h2 className="mb-3 text-sm font-semibold">Latest run</h2>
          <RunPanel execution={execution} profile={memory.data?.profile} />
          {execution && (
            <div className="mt-4 flex gap-2">
              <Link to="/graph" className="text-xs text-info hover:underline">View in Graph Explorer</Link>
              <span className="text-faint">·</span>
              <Link to={`/inspector?thread=${execution.thread_id}`} className="text-xs text-info hover:underline">Context & state</Link>
            </div>
          )}
        </aside>
      )}
    </div>
  )
}
