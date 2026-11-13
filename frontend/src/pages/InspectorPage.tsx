import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Brain, Database, Gauge, Trash2, X } from 'lucide-react'
import { ContextInspector } from '../components/ContextInspector'
import { Button, Card, Chip, EmptyState, ErrorBanner, Label, Page, PageHeader, Tabs } from '../components/ui'
import { inputClass } from '../components/styles'
import { useApp } from '../context/app-context'
import { useAsync } from '../hooks/useAsync'
import { FIELD_LABELS, formatDateTime, relativeTime } from '../lib/format'
import { api } from '../services/api'
import type { MemoryInfo } from '../types'

type Tab = 'short' | 'long' | 'context'

function ListEditor({ field, items, onChange, onRemove }: { field: string; items: string[]; onChange: (v: string[]) => Promise<void>; onRemove: (v: string) => Promise<void> }) {
  const [draft, setDraft] = useState('')
  return (
    <div>
      <Label htmlFor={`add-${field}`}>{FIELD_LABELS[field]}</Label>
      <div className="mb-2 flex flex-wrap gap-1.5">
        {items.length === 0 && <span className="text-xs text-faint">none</span>}
        {items.map((v) => (
          <Chip key={v} tone="accent">
            {v}
            <button type="button" aria-label={`Remove ${v}`} className="ml-1 rounded hover:text-danger" onClick={() => void onRemove(v)}><X className="size-3" /></button>
          </Chip>
        ))}
      </div>
      <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); const v = draft.trim(); if (v) { void onChange([...items, v]); setDraft('') } }}>
        <input id={`add-${field}`} className={inputClass} value={draft} maxLength={80} onChange={(e) => setDraft(e.target.value)} placeholder="Add…" />
        <Button type="submit" disabled={!draft.trim()}>Add</Button>
      </form>
    </div>
  )
}

function LongTerm({ memory, reload }: { memory: MemoryInfo; reload: () => void }) {
  const [error, setError] = useState<unknown>(null)
  const [style, setStyle] = useState<string | null>(null)
  const [lang, setLang] = useState<string | null>(null)
  const p = memory.profile

  const act = async (fn: () => Promise<unknown>) => {
    setError(null)
    try {
      await fn()
      setStyle(null)
      setLang(null)
      reload()
    } catch (e) {
      setError(e)
    }
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[1fr_320px]">
      <div className="space-y-6">
        {!!error && <ErrorBanner error={error} />}
        <Card title="Student profile" description="Edit or delete anything the assistant has learned about you.">
          <div className="space-y-5">
            {(['preferred_explanation_style', 'preferred_programming_language'] as const).map((f) => {
              const draft = f === 'preferred_explanation_style' ? style : lang
              const set = f === 'preferred_explanation_style' ? setStyle : setLang
              const value = draft ?? p[f] ?? ''
              return (
                <form key={f} onSubmit={(e) => { e.preventDefault(); void act(() => api.patchMemory({ [f]: value.trim() })) }}>
                  <Label htmlFor={f}>{FIELD_LABELS[f]}</Label>
                  <div className="flex gap-2">
                    <input id={f} className={inputClass} value={value} maxLength={60} onChange={(e) => set(e.target.value)} placeholder="Not set" />
                    <Button type="submit" disabled={!value.trim() || value.trim() === p[f]}>Save</Button>
                    <Button type="button" variant="danger" disabled={!p[f]} aria-label={`Delete ${FIELD_LABELS[f]}`} onClick={() => void act(() => api.deleteMemoryField(f))}><Trash2 className="size-4" /></Button>
                  </div>
                </form>
              )
            })}
            {(['current_subjects', 'learning_preferences', 'revision_areas'] as const).map((f) => (
              <ListEditor key={f} field={f} items={p[f]} onChange={(v) => act(() => api.patchMemory({ [f]: v }))} onRemove={(v) => act(() => api.deleteMemoryField(f, v))} />
            ))}
          </div>
        </Card>
        <Card title="Topics studied" padded={false}>
          {p.topics_studied.length === 0 && <EmptyState title="No topics yet">Topics are recorded when you ask for explanations.</EmptyState>}
          <ul className="divide-y divide-line">
            {p.topics_studied.map((t) => (
              <li key={t.topic} className="flex items-center justify-between gap-3 px-4 py-2 text-sm">
                <span>{t.topic} <span className="text-xs text-faint">×{t.count} · {relativeTime(t.last_studied)}</span></span>
                <button type="button" aria-label={`Delete topic ${t.topic}`} className="text-faint hover:text-danger" onClick={() => void act(() => api.deleteMemoryField('topics_studied', t.topic))}><Trash2 className="size-3.5" /></button>
              </li>
            ))}
          </ul>
        </Card>
      </div>
      <aside className="space-y-6">
        <Card title="Storage">
          <dl className="space-y-2 text-sm">
            <div><dt className="text-xs text-muted">Namespace</dt><dd className="font-mono text-xs break-all">({memory.namespace.map((n) => `"${n}"`).join(', ')})</dd></div>
            <div><dt className="text-xs text-muted">Key</dt><dd className="font-mono text-xs">{memory.key}</dd></div>
            <div><dt className="text-xs text-muted">Stored</dt><dd>{memory.found ? 'yes' : 'no profile yet'}</dd></div>
            <div><dt className="text-xs text-muted">Last updated</dt><dd>{formatDateTime(memory.updated_at)}</dd></div>
          </dl>
        </Card>
        <Card title="Delete profile" description="Removes the whole long-term profile for this user. Conversations are kept.">
          <Button variant="danger" disabled={!memory.found} onClick={() => void act(() => api.clearMemory())}>Delete entire profile</Button>
        </Card>
      </aside>
    </div>
  )
}

export function InspectorPage() {
  const { userId } = useApp()
  const [params, setParams] = useSearchParams()
  const tab = (['short', 'long', 'context'].includes(params.get('tab') ?? '') ? params.get('tab') : params.get('thread') ? 'short' : 'short') as Tab
  const threadParam = params.get('thread')
  const threads = useAsync(() => api.listThreads(), [userId])
  const threadId = threadParam ?? threads.data?.[0]?.id ?? null
  const state = useAsync(() => (threadId ? api.threadState(threadId) : Promise.resolve(null)), [threadId, userId])
  const detail = useAsync(() => (threadId ? api.getThread(threadId) : Promise.resolve(null)), [threadId, userId])
  const memory = useAsync(() => api.memory(), [userId])

  const setTab = (t: Tab) => setParams((p) => { const n = new URLSearchParams(p); n.set('tab', t); return n }, { replace: true })
  const setThread = (id: string) => setParams((p) => { const n = new URLSearchParams(p); n.set('thread', id); return n }, { replace: true })

  const s = state.data && state.data.thread_id === threadId ? state.data : null
  const d = detail.data && detail.data.id === threadId ? detail.data : null

  const picker = (
    <div className="mb-4 flex flex-wrap items-center gap-3">
      <Label htmlFor="thread-select">Conversation</Label>
      <select id="thread-select" className={`${inputClass} max-w-md`} value={threadId ?? ''} onChange={(e) => setThread(e.target.value)} disabled={!threads.data?.length}>
        {!threads.data?.length && <option value="">No conversations</option>}
        {threads.data?.map((t) => <option key={t.id} value={t.id}>{t.title}</option>)}
      </select>
    </div>
  )

  return (
    <Page wide>
      <PageHeader title="Memory & State Inspector" description="Short-term memory is the per-thread checkpointed graph state. Long-term memory is the persistent per-user store shared across threads." />
      <div className="mb-5">
        <Tabs<Tab> value={tab} onChange={setTab} tabs={[
          { id: 'short', label: 'Short-term (thread state)', icon: <Database className="size-4" /> },
          { id: 'long', label: 'Long-term (profile)', icon: <Brain className="size-4" /> },
          { id: 'context', label: 'Context window', icon: <Gauge className="size-4" /> },
        ]} />
      </div>

      {tab !== 'long' && picker}
      {tab !== 'long' && (state.error || detail.error) && <ErrorBanner error={state.error ?? detail.error} onRetry={() => { state.reload(); detail.reload() }} className="mb-4" />}
      {tab !== 'long' && !threadId && !threads.loading && <EmptyState icon={<Database className="size-6" />} title="No conversations yet">Start a chat; its checkpointed state will show up here.</EmptyState>}

      {tab === 'short' && s && (
        <div className="grid gap-6 xl:grid-cols-2">
          <Card title="Thread" description="Isolated by thread_id in the SQLite checkpointer">
            <dl className="grid grid-cols-[9rem_1fr] gap-y-1.5 text-sm">
              <dt className="text-muted">thread_id</dt><dd className="font-mono text-xs break-all">{s.thread_id}</dd>
              <dt className="text-muted">checkpoint</dt><dd className="font-mono text-xs break-all">{s.checkpoint_id ?? '—'}</dd>
              <dt className="text-muted">messages</dt><dd>{s.message_count}</dd>
              <dt className="text-muted">intent / topic</dt><dd>{s.values.intent ?? '—'} / {s.values.topic ?? '—'}</dd>
              <dt className="text-muted">checkpointer</dt><dd className="font-mono text-xs">{s.storage.checkpointer} · {s.storage.database}</dd>
              <dt className="text-muted">long-term store</dt><dd className="font-mono text-xs">{s.storage.long_term_store} · {s.storage.store_database}</dd>
            </dl>
          </Card>
          <Card title="Learning insights" description="Built by the merge_insights reducer: same (kind, topic) increments count instead of duplicating">
            {s.values.learning_insights.length === 0 && <p className="text-sm text-muted">No insights yet in this thread.</p>}
            {s.values.learning_insights.length > 0 && (
              <table className="w-full text-left text-sm">
                <thead className="text-xs text-muted"><tr><th className="py-1 font-medium">Kind</th><th className="font-medium">Topic</th><th className="font-medium">Count</th><th className="font-medium">Intents</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {s.values.learning_insights.map((i) => <tr key={`${i.kind}-${i.topic}`}><td className="py-1.5">{i.kind}</td><td>{i.topic}</td><td className="tabular-nums">{i.count}</td><td className="text-xs text-muted">{i.intents.join(', ')}</td></tr>)}
                </tbody>
              </table>
            )}
          </Card>
          <Card title="Checkpoints" description={s.checkpoints_truncated ? 'Most recent checkpoints (list truncated)' : 'Every saved state snapshot, newest first'} className="xl:col-span-2" padded={false}>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-line text-xs text-muted"><tr><th className="px-4 py-2 font-medium">Step</th><th className="font-medium">Source</th><th className="font-medium">Wrote</th><th className="font-medium">Messages</th><th className="font-medium">Insights</th><th className="font-medium">Next</th><th className="px-4 font-medium">Created</th></tr></thead>
                <tbody className="divide-y divide-line">
                  {s.checkpoints.map((c) => (
                    <tr key={c.checkpoint_id} className={c.checkpoint_id === s.checkpoint_id ? 'bg-accent-soft' : ''}>
                      <td className="px-4 py-1.5 tabular-nums">{c.step ?? '—'}</td><td>{c.source ?? '—'}</td>
                      <td className="font-mono text-xs">{c.writes.join(', ') || '—'}</td><td className="tabular-nums">{c.message_count}</td><td className="tabular-nums">{c.insight_count}</td>
                      <td className="font-mono text-xs">{c.next.join(', ') || '—'}</td><td className="px-4 text-xs text-muted">{formatDateTime(c.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          <Card title="State reducers" className="xl:col-span-2">
            <dl className="grid gap-3 md:grid-cols-3 text-sm">
              {Object.entries(s.reducers).map(([k, r]) => <div key={k}><dt className="font-mono text-xs text-accent">{k} <span className="text-faint">· {r.reducer}</span></dt><dd className="mt-0.5 text-muted">{r.behaviour}</dd></div>)}
            </dl>
          </Card>
        </div>
      )}

      {tab === 'long' && (
        <>
          {memory.error && <ErrorBanner error={memory.error} onRetry={memory.reload} className="mb-4" />}
          {memory.data && <LongTerm memory={memory.data} reload={memory.reload} />}
        </>
      )}

      {tab === 'context' && s && (
        <Card title="Context sent to the model" description="Calculated by the context builder on the last run; counts come from the token counter named below.">
          <ContextInspector stats={s.values.context_statistics} messages={d?.messages} />
        </Card>
      )}
    </Page>
  )
}
