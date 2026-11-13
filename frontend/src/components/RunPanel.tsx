import { BrainCircuit, CheckCircle2, CircleAlert, DatabaseZap } from 'lucide-react'
import { FIELD_LABELS, nodeLabel } from '../lib/format'
import type { Execution, Profile } from '../types'
import { Bar, Chip } from './ui'

function profileValue(profile: Profile | undefined, field: string): string {
  if (!profile) return ''
  const v = (profile as unknown as Record<string, unknown>)[field]
  if (Array.isArray(v)) return v.map((x) => (typeof x === 'string' ? x : (x as { topic: string }).topic)).join(', ')
  return typeof v === 'string' ? v : ''
}

/** Everything in this panel comes from the execution record returned by the backend for the latest run. */
export function RunPanel({ execution, profile }: { execution: Execution | null | undefined; profile?: Profile }) {
  if (!execution) {
    return <p className="px-1 py-6 text-center text-sm text-muted">No run yet. Send a message to see how the graph handled it.</p>
  }
  const ctx = execution.context
  const mem = execution.retrieved_memory
  const failed = execution.status === 'error'
  const maxMs = Math.max(...execution.trace.map((t) => t.duration_ms), 1)
  return (
    <div className="space-y-5 text-sm">
      <div className="flex flex-wrap items-center gap-1.5">
        {failed ? <Chip tone="danger"><CircleAlert className="size-3" /> failed</Chip> : <Chip tone="ok"><CheckCircle2 className="size-3" /> completed</Chip>}
        <Chip tone="info">intent: {execution.intent ?? '—'}</Chip>
        <Chip>{execution.duration_ms} ms</Chip>
        {execution.llm.provider && (
          <Chip tone={execution.llm.provider === 'offline' ? 'warn' : 'neutral'} title={execution.llm.fallback_reason ?? undefined}>
            {execution.llm.provider}
            {execution.llm.model ? ` · ${execution.llm.model}` : ''}
          </Chip>
        )}
      </div>
      {execution.llm.provider === 'offline' && (
        <p className="rounded-md border border-warn/30 bg-warn/10 px-3 py-2 text-xs text-warn">
          Answered by the offline fallback (no language model reachable){execution.llm.fallback_reason ? `: ${execution.llm.fallback_reason}` : '.'}
        </p>
      )}
      {failed && execution.error && <p className="rounded-md border border-danger/30 bg-danger/10 px-3 py-2 text-xs text-danger">{execution.error.message}</p>}

      <div>
        <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Execution path</h3>
        <ol className="space-y-1.5">
          {execution.path.map((node, i) => {
            const t = execution.trace.find((x) => x.node === node)
            const isErr = failed && execution.error?.node === node
            return (
              <li key={`${node}-${i}`} className="rounded-md border border-line bg-canvas px-2.5 py-1.5">
                <div className="flex items-center justify-between gap-2">
                  <span className={`font-mono text-xs ${isErr ? 'text-danger' : 'text-fg'}`}>
                    {i + 1}. {nodeLabel(node)}
                  </span>
                  {t && <span className="font-mono text-[11px] text-faint">{t.duration_ms} ms</span>}
                </div>
                {t && <div className="mt-1"><Bar value={t.duration_ms} max={maxMs} tone="info" label={`${node} duration`} /></div>}
                {node === 'router_node' && execution.route.reason && (
                  <p className="mt-1 text-[11px] text-muted">
                    <span className="text-warn">{execution.route.method}</span> → {execution.route.intent}: {execution.route.reason}
                  </p>
                )}
              </li>
            )
          })}
        </ol>
      </div>

      <div>
        <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted uppercase">
          <BrainCircuit className="size-3.5" /> Long-term memory retrieved
        </h3>
        {mem.found && mem.fields && mem.fields.length > 0 ? (
          <dl className="space-y-1.5">
            {mem.fields.map((f) => (
              <div key={f} className="rounded-md border border-accent/25 bg-accent-soft/50 px-2.5 py-1.5">
                <dt className="text-[11px] text-muted">{FIELD_LABELS[f] ?? f}</dt>
                <dd className="text-xs text-fg">{profileValue(profile, f) || '—'}</dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="text-xs text-muted">Nothing stored for this user yet.</p>
        )}
        {mem.namespace && <p className="mt-1.5 font-mono text-[11px] break-all text-faint">store namespace: {mem.namespace.join(' / ')}</p>}
      </div>

      {execution.memory_changes.length > 0 && (
        <div>
          <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold tracking-wide text-muted uppercase">
            <DatabaseZap className="size-3.5" /> Saved to long-term memory
          </h3>
          <ul className="space-y-1">
            {execution.memory_changes.map((c, i) => (
              <li key={i} className="rounded-md border border-ok/25 bg-ok/10 px-2.5 py-1.5 text-xs text-fg">
                <span className="text-muted">{FIELD_LABELS[c.field] ?? c.field}:</span> {c.new}
              </li>
            ))}
          </ul>
        </div>
      )}

      {ctx.token_budget !== undefined && (
        <div>
          <h3 className="mb-2 text-xs font-semibold tracking-wide text-muted uppercase">Context sent to the model</h3>
          <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
            <dt className="text-muted">Messages kept</dt>
            <dd className="text-right font-mono">{ctx.retained_messages} / {ctx.total_messages}</dd>
            <dt className="text-muted">Tokens before → after</dt>
            <dd className="text-right font-mono">{ctx.tokens_before} → {ctx.tokens_after}</dd>
            <dt className="text-muted">Budget</dt>
            <dd className="text-right font-mono">{ctx.token_budget}</dd>
          </dl>
        </div>
      )}
    </div>
  )
}
