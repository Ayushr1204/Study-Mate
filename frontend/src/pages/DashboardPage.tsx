import { Link } from 'react-router-dom'
import { BookOpenCheck, FileText, MessageSquare, Workflow } from 'lucide-react'
import { Bar, Card, Chip, EmptyState, ErrorBanner, Page, PageHeader, Stat } from '../components/ui'
import { useApp } from '../context/app-context'
import { useAsync } from '../hooks/useAsync'
import { FIELD_LABELS, plural, relativeTime } from '../lib/format'
import { api } from '../services/api'

const ACTIONS = [
  { to: '/chat', label: 'Ask a question', icon: MessageSquare },
  { to: '/quiz', label: 'Generate a quiz', icon: BookOpenCheck },
  { to: '/summarize', label: 'Summarize notes', icon: FileText },
  { to: '/graph', label: 'Explore the graph', icon: Workflow },
]

export function DashboardPage() {
  const { userId } = useApp()
  const dash = useAsync(() => api.dashboard(), [userId])
  const d = dash.data
  const profile = d?.profile.profile
  const intents = Object.entries(d?.runs_by_intent ?? {}).sort((a, b) => b[1] - a[1])
  const maxRuns = Math.max(...intents.map(([, n]) => n), 1)
  const totalRuns = intents.reduce((s, [, n]) => s + n, 0)

  return (
    <Page>
      <PageHeader title="Dashboard" description={<>Study activity for <span className="font-mono">{userId}</span>. Every number here is read from the database.</>} />
      {dash.error && <ErrorBanner error={dash.error} onRetry={dash.reload} className="mb-4" />}
      {!d && !dash.error && <p className="text-sm text-muted" role="status">Loading…</p>}
      {d && (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Stat label="Conversations" value={d.thread_count} />
            <Stat label="Graph runs" value={totalRuns} />
            <Stat label="Quizzes generated" value={d.quiz.quizzes_generated} hint={plural(d.quiz.attempts, 'attempt')} />
            <Stat label="Average quiz score" value={d.quiz.average_percent === null ? '—' : `${d.quiz.average_percent}%`} hint={d.quiz.attempts === 0 ? 'No attempts yet' : undefined} />
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {ACTIONS.map(({ to, label, icon: Icon }) => (
              <Link key={to} to={to} className="flex items-center gap-3 rounded-lg border border-line bg-surface px-4 py-3 text-sm transition-colors hover:border-line-strong hover:bg-hover">
                <Icon className="size-4 text-accent" aria-hidden /> {label}
              </Link>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card title="Recent conversations" padded={false}>
              {d.recent_threads.length === 0 && <EmptyState icon={<MessageSquare className="size-6" />} title="No conversations yet">Start one in Study Chat.</EmptyState>}
              <ul className="divide-y divide-line">
                {d.recent_threads.map((t) => (
                  <li key={t.id}>
                    <Link to={`/chat/${t.id}`} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm hover:bg-hover">
                      <span className="truncate">{t.title}</span>
                      <span className="shrink-0 text-xs text-faint">{relativeTime(t.updated_at)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title="Recent topics" description="From your long-term learning profile">
              {d.recent_topics.length === 0 && <p className="text-sm text-muted">Topics appear here after you ask explanation questions.</p>}
              <div className="flex flex-wrap gap-1.5">
                {d.recent_topics.map((t) => <Chip key={t.topic} tone="accent" title={`Last studied ${relativeTime(t.last_studied)}`}>{t.topic}{t.count > 1 ? ` ×${t.count}` : ''}</Chip>)}
              </div>
            </Card>

            <Card title="Quiz activity" padded={false}>
              {d.quiz.recent_attempts.length === 0 && <EmptyState icon={<BookOpenCheck className="size-6" />} title="No attempts yet">Take a quiz to see scores here.</EmptyState>}
              <ul className="divide-y divide-line">
                {d.quiz.recent_attempts.map((a) => (
                  <li key={a.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
                    <span className="truncate">{a.topic}</span>
                    <span className="flex shrink-0 items-center gap-2">
                      <Chip tone={a.score / a.total >= 0.7 ? 'ok' : 'warn'}>{a.score}/{a.total}</Chip>
                      <span className="text-xs text-faint">{relativeTime(a.created_at)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            </Card>

            <Card title="Learning profile" action={<Link to="/inspector?tab=long" className="text-xs text-accent hover:underline">Inspect</Link>}>
              {!d.profile.found && <p className="text-sm text-muted">Nothing stored yet. Tell the assistant how you like to learn, e.g. “I prefer explanations using real-world analogies”.</p>}
              {d.profile.found && profile && (
                <dl className="space-y-2 text-sm">
                  {(['preferred_explanation_style', 'preferred_programming_language'] as const).map((f) => profile[f] && (
                    <div key={f}><dt className="text-xs text-muted">{FIELD_LABELS[f]}</dt><dd>{profile[f]}</dd></div>
                  ))}
                  {profile.revision_areas.length > 0 && (
                    <div><dt className="text-xs text-muted">{FIELD_LABELS.revision_areas}</dt><dd className="mt-1 flex flex-wrap gap-1.5">{profile.revision_areas.map((r) => <Chip key={r} tone="warn">{r}</Chip>)}</dd></div>
                  )}
                </dl>
              )}
            </Card>
          </div>

          <Card title="Graph runs by intent" description="How the router has classified your requests">
            {intents.length === 0 && <p className="text-sm text-muted">No runs recorded yet.</p>}
            <ul className="space-y-2">
              {intents.map(([intent, n]) => (
                <li key={intent} className="grid grid-cols-[8rem_1fr_2rem] items-center gap-3 text-sm">
                  <span className="text-muted">{intent}</span>
                  <Bar value={n} max={maxRuns} label={`${intent}: ${n} runs`} />
                  <span className="text-right tabular-nums">{n}</span>
                </li>
              ))}
            </ul>
          </Card>
        </div>
      )}
    </Page>
  )
}
