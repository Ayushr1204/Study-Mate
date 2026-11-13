import { useMemo } from 'react'
import type { Execution, GraphEdge, GraphInfo } from '../types'
import { activeEdgeKeys, layoutGraph, nodeStates, type Laid } from '../lib/graphLayout'

function edgePath(a: Laid, b: Laid): string {
  const x1 = a.x
  const y1 = a.y + a.h / 2
  const x2 = b.x
  const y2 = b.y - b.h / 2
  const dy = Math.max(24, (y2 - y1) / 2)
  return `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`
}

const KIND_COLOR: Record<string, string> = {
  memory: 'var(--color-info)',
  router: 'var(--color-warn)',
  processing: 'var(--color-accent)',
  response: 'var(--color-ok)',
}

export function GraphView({
  graph,
  execution,
  selected,
  onSelect,
}: {
  graph: GraphInfo
  execution?: Execution | null
  selected?: string | null
  onSelect?: (id: string) => void
}) {
  const layout = useMemo(() => layoutGraph(graph), [graph])
  const states = useMemo(() => nodeStates(graph, execution), [graph, execution])
  const active = useMemo(() => activeEdgeKeys(graph, execution), [graph, execution])
  const durations = useMemo(() => new Map((execution?.trace ?? []).map((t) => [t.node, t.duration_ms])), [execution])
  const hasRun = Boolean(execution)

  const edgeStyle = (e: GraphEdge) => {
    const isActive = active.has(`${e.source}>${e.target}`)
    if (isActive) return { stroke: 'var(--color-accent)', width: 2.2, dash: undefined, opacity: 1, marker: 'arrow-active' }
    const dim = hasRun ? 0.28 : 1
    if (e.conditional) return { stroke: 'var(--color-warn)', width: 1.4, dash: '5 4', opacity: hasRun ? 0.3 : 0.85, marker: 'arrow-cond' }
    return { stroke: 'var(--color-line-strong)', width: 1.4, dash: undefined, opacity: dim, marker: 'arrow' }
  }

  return (
    <svg
      viewBox={`0 0 ${layout.width} ${layout.height}`}
      className="mx-auto block w-full"
      style={{ maxWidth: layout.width, minWidth: Math.min(layout.width, 640) }}
      role="img"
      aria-label="StudyMate LangGraph state graph"
    >
      <defs>
        {[
          ['arrow', 'var(--color-line-strong)'],
          ['arrow-cond', 'var(--color-warn)'],
          ['arrow-active', 'var(--color-accent)'],
        ].map(([id, color]) => (
          <marker key={id} id={id} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z" fill={color} />
          </marker>
        ))}
      </defs>

      {graph.edges.map((e) => {
        const a = layout.nodes.get(e.source)
        const b = layout.nodes.get(e.target)
        if (!a || !b) return null
        const s = edgeStyle(e)
        const mx = (a.x + b.x) / 2
        const my = (a.y + a.h / 2 + b.y - b.h / 2) / 2
        return (
          <g key={`${e.source}>${e.target}`} data-edge={`${e.source}>${e.target}`} data-conditional={e.conditional} data-active={active.has(`${e.source}>${e.target}`)}>
            <path d={edgePath(a, b)} fill="none" stroke={s.stroke} strokeWidth={s.width} strokeDasharray={s.dash} opacity={s.opacity} markerEnd={`url(#${s.marker})`} />
            {e.conditional && e.label && (
              <g opacity={hasRun && !active.has(`${e.source}>${e.target}`) ? 0.4 : 1}>
                <rect x={mx - e.label.length * 3.1 - 6} y={my - 9} width={e.label.length * 6.2 + 12} height={18} rx={4} fill="var(--color-canvas)" stroke="var(--color-line)" />
                <text x={mx} y={my + 3.5} textAnchor="middle" fontSize="10" fill="var(--color-warn)" fontFamily="var(--font-mono)">
                  {e.label}
                </text>
              </g>
            )}
          </g>
        )
      })}

      {[...layout.nodes.values()].map(({ node, x, y, w, h }) => {
        const state = states.get(node.id) ?? 'idle'
        const terminal = node.type !== 'node'
        const isSel = selected === node.id
        const stroke =
          state === 'error' ? 'var(--color-danger)' : state === 'ok' && hasRun ? 'var(--color-accent)' : isSel ? 'var(--color-fg)' : 'var(--color-line-strong)'
        const opacity = state === 'skipped' ? 0.4 : 1
        const ms = durations.get(node.id)
        return (
          <g
            key={node.id}
            data-node={node.id}
            data-state={state}
            transform={`translate(${x - w / 2}, ${y - h / 2})`}
            opacity={opacity}
            role="button"
            tabIndex={0}
            aria-label={`${node.title ?? node.id}${hasRun ? `, ${state}` : ''}`}
            aria-pressed={isSel}
            className="cursor-pointer outline-none [&:focus-visible>rect:first-child]:stroke-[var(--color-accent)]"
            onClick={() => onSelect?.(node.id)}
            onKeyDown={(ev) => {
              if (ev.key === 'Enter' || ev.key === ' ') {
                ev.preventDefault()
                onSelect?.(node.id)
              }
            }}
          >
            <rect width={w} height={h} rx={terminal ? h / 2 : 8} fill={isSel ? 'var(--color-hover)' : 'var(--color-raised)'} stroke={stroke} strokeWidth={isSel || state !== 'idle' ? 1.8 : 1.2} />
            {!terminal && node.kind && <rect x={0} y={10} width={3} height={h - 20} rx={1.5} fill={KIND_COLOR[node.kind]} />}
            {terminal ? (
              <text x={w / 2} y={h / 2 + 4} textAnchor="middle" fontSize="11" fill="var(--color-muted)" fontFamily="var(--font-mono)">
                {node.id === '__start__' ? 'START' : 'END'}
              </text>
            ) : (
              <>
                <text x={14} y={22} fontSize="12.5" fontWeight="600" fill="var(--color-fg)">
                  {node.title ?? node.id}
                </text>
                <text x={14} y={40} fontSize="10" fill="var(--color-faint)" fontFamily="var(--font-mono)">
                  {node.id}
                </text>
                {state === 'ok' && ms !== undefined && (
                  <text x={w - 10} y={22} textAnchor="end" fontSize="10" fill="var(--color-accent)" fontFamily="var(--font-mono)">
                    {ms} ms
                  </text>
                )}
                {state === 'error' && (
                  <text x={w - 10} y={22} textAnchor="end" fontSize="10" fill="var(--color-danger)" fontFamily="var(--font-mono)">
                    failed
                  </text>
                )}
              </>
            )}
          </g>
        )
      })}
    </svg>
  )
}

export function GraphLegend() {
  const item = (label: string, el: React.ReactNode) => (
    <span className="inline-flex items-center gap-2 text-xs text-muted">
      {el}
      {label}
    </span>
  )
  const line = (color: string, dash?: string) => (
    <svg width="26" height="8" aria-hidden>
      <line x1="0" y1="4" x2="26" y2="4" stroke={color} strokeWidth="2" strokeDasharray={dash} />
    </svg>
  )
  const dot = (color: string) => <span className="inline-block size-2.5 rounded-sm" style={{ background: color }} />
  return (
    <div className="flex flex-wrap gap-x-5 gap-y-2" aria-label="Graph legend">
      {item('Normal edge', line('var(--color-line-strong)'))}
      {item('Conditional edge', line('var(--color-warn)', '5 4'))}
      {item('Latest execution path', line('var(--color-accent)'))}
      {item('Memory node', dot(KIND_COLOR.memory))}
      {item('Router', dot(KIND_COLOR.router))}
      {item('Processing', dot(KIND_COLOR.processing))}
      {item('Response', dot(KIND_COLOR.response))}
    </div>
  )
}
