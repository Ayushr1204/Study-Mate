import { Gauge } from 'lucide-react'
import type { ChatMessage, ContextStats } from '../types'
import { Chip, EmptyState } from './ui'

const STATUS: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'neutral' }> = {
  retained: { label: 'sent to model', tone: 'ok' },
  excluded_trimmed: { label: 'trimmed (over budget)', tone: 'warn' },
  filtered_empty: { label: 'filtered: empty', tone: 'neutral' },
  filtered_unanswered: { label: 'filtered: unanswered turn', tone: 'neutral' },
  filtered_error: { label: 'filtered: error reply', tone: 'danger' },
  filtered_system: { label: 'filtered: system', tone: 'neutral' },
}

function TokenBar({ label, value, max, budget, tone }: { label: string; value: number; max: number; budget: number; tone: string }) {
  const pct = (v: number) => `${Math.min(100, (v / max) * 100)}%`
  return (
    <div>
      <div className="mb-1 flex items-baseline justify-between text-xs">
        <span className="text-muted">{label}</span>
        <span className="font-mono text-fg tabular-nums">{value.toLocaleString()} tokens</span>
      </div>
      <div className="relative h-3 rounded bg-raised" role="img" aria-label={`${label}: ${value} tokens of a ${budget} token budget`}>
        <div className={`h-full rounded ${tone}`} style={{ width: pct(value) }} />
        <div className="absolute inset-y-[-3px] w-px bg-fg/70" style={{ left: pct(budget) }} title={`Budget: ${budget}`} />
      </div>
    </div>
  )
}

function Tile({ label, value, sub }: { label: string; value: React.ReactNode; sub?: string }) {
  return (
    <div className="rounded-md border border-line bg-canvas px-3 py-2">
      <p className="text-[11px] text-muted">{label}</p>
      <p className="mt-0.5 text-lg font-semibold text-fg tabular-nums">{value}</p>
      {sub && <p className="text-[11px] text-faint">{sub}</p>}
    </div>
  )
}

export function ContextInspector({ stats, messages, compact = false }: { stats: Partial<ContextStats> | null | undefined; messages?: ChatMessage[]; compact?: boolean }) {
  if (!stats || stats.token_budget === undefined) {
    return <EmptyState icon={<Gauge className="size-6" />} title="No context data yet">Send a message in this conversation. The statistics shown here come from the trimming step that runs before the model call.</EmptyState>
  }
  const s = stats as ContextStats
  const max = Math.max(s.tokens_before, s.token_budget, s.tokens_after, 1)
  const decisions = s.scope === 'conversation' ? s.decisions : []
  const rows = decisions.map((d, i) => ({ status: d[0], tokens: d[1], sent: d[2], truncated: d[3] === 1, message: messages?.[i] }))

  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <TokenBar label="Estimated tokens before trimming" value={s.tokens_before} max={max} budget={s.token_budget} tone="bg-line-strong" />
        <TokenBar label="Estimated tokens after trimming (sent to the model)" value={s.tokens_after} max={max} budget={s.token_budget} tone={s.within_budget ? 'bg-accent' : 'bg-danger'} />
        <p className="text-xs text-faint">
          The vertical tick marks the configured budget of <span className="font-mono text-muted">{s.token_budget.toLocaleString()}</span> tokens.
          {!s.within_budget && <span className="ml-1 text-danger">The system prompt plus the latest message alone exceed it.</span>}
        </p>
      </div>

      <div className={`grid gap-2 ${compact ? 'grid-cols-2' : 'grid-cols-2 sm:grid-cols-3 lg:grid-cols-6'}`}>
        <Tile label="Total messages" value={s.total_messages} />
        <Tile label="Retained for model" value={s.retained_messages} />
        <Tile label="Excluded" value={s.excluded_messages} sub={`${s.trimmed_messages} trimmed, ${s.filtered_messages} filtered`} />
        <Tile label="Truncated" value={s.truncated_messages} sub={`cap ${s.max_message_tokens} tok/msg`} />
        <Tile label="System prompt" value={s.system_prompt_tokens} sub="tokens" />
        <Tile label="Budget" value={s.token_budget.toLocaleString()} sub="tokens" />
      </div>

      <p className="text-xs text-muted">
        Token counter: <span className="font-mono text-fg">{s.token_counter}</span>{' '}
        {s.token_counter_exact ? <Chip tone="ok">exact</Chip> : <Chip tone="warn" title="tiktoken's vocabulary could not be loaded, so tokens are estimated as characters / 4">estimate</Chip>}
        {s.scope === 'summarization_prompt' && <span className="ml-2 text-faint">Measured on the summarization prompt, not on a conversation.</span>}
      </p>

      {!compact && rows.length > 0 && (
        <div className="overflow-x-auto rounded-md border border-line">
          <table className="w-full text-left text-xs">
            <thead className="bg-raised text-muted">
              <tr>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Role</th>
                <th className="px-3 py-2 font-medium">Message</th>
                <th className="px-3 py-2 text-right font-medium">Tokens</th>
                <th className="px-3 py-2 font-medium">What happened</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const st = STATUS[r.status] ?? { label: r.status, tone: 'neutral' as const }
                return (
                  <tr key={i} className={`border-t border-line ${r.status === 'retained' ? '' : 'opacity-60'}`}>
                    <td className="px-3 py-1.5 font-mono text-faint">{i + 1}</td>
                    <td className="px-3 py-1.5 text-muted">{r.message?.role ?? '—'}</td>
                    <td className="max-w-[28rem] truncate px-3 py-1.5 text-fg">{r.message?.content.replace(/\s+/g, ' ').slice(0, 110) ?? '—'}</td>
                    <td className="px-3 py-1.5 text-right font-mono tabular-nums">
                      {r.tokens}
                      {r.truncated && <span className="text-info"> → {r.sent}</span>}
                    </td>
                    <td className="px-3 py-1.5">
                      <span className="inline-flex gap-1">
                        <Chip tone={st.tone}>{st.label}</Chip>
                        {r.truncated && <Chip tone="info">truncated</Chip>}
                      </span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
