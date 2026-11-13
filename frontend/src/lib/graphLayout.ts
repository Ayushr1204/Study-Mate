import type { Execution, GraphInfo, GraphNode } from '../types'

export type NodeState = 'idle' | 'ok' | 'error' | 'skipped'

export const NODE_W = 172
const NODE_H = 54
const PILL_W = 104
const PILL_H = 30
const GAP_X = 26
const GAP_Y = 70
const PAD = 24

export interface Laid {
  node: GraphNode
  x: number // centre
  y: number // centre
  w: number
  h: number
}

/** Layered top-to-bottom layout. Rank = longest path from the start node; nothing here adds or removes graph elements. */
export function layoutGraph(graph: GraphInfo): { nodes: Map<string, Laid>; width: number; height: number } {
  const rank = new Map<string, number>(graph.nodes.map((n) => [n.id, 0]))
  for (let pass = 0; pass < graph.nodes.length; pass++) {
    for (const e of graph.edges) rank.set(e.target, Math.max(rank.get(e.target) ?? 0, (rank.get(e.source) ?? 0) + 1))
  }
  const byRank = new Map<number, GraphNode[]>()
  for (const n of graph.nodes) {
    const r = rank.get(n.id) ?? 0
    byRank.set(r, [...(byRank.get(r) ?? []), n])
  }
  // keep sibling order stable and meaningful: the order the conditional edges are declared in
  const edgeOrder = (id: string) => {
    const i = graph.edges.findIndex((e) => e.target === id)
    return i === -1 ? 0 : i
  }
  const maxCols = Math.max(...[...byRank.values()].map((v) => v.length))
  const width = maxCols * NODE_W + (maxCols - 1) * GAP_X + PAD * 2
  const out = new Map<string, Laid>()
  const ranks = [...byRank.keys()].sort((a, b) => a - b)
  ranks.forEach((r, row) => {
    const items = [...(byRank.get(r) ?? [])].sort((a, b) => edgeOrder(a.id) - edgeOrder(b.id))
    const rowWidth = items.length * NODE_W + (items.length - 1) * GAP_X
    items.forEach((node, i) => {
      const terminal = node.type !== 'node'
      const w = terminal ? PILL_W : NODE_W
      const h = terminal ? PILL_H : NODE_H
      const x = (width - rowWidth) / 2 + i * (NODE_W + GAP_X) + NODE_W / 2
      const y = PAD + row * (NODE_H + GAP_Y) + NODE_H / 2
      out.set(node.id, { node, x, y, w, h })
    })
  })
  return { nodes: out, width, height: PAD * 2 + ranks.length * NODE_H + (ranks.length - 1) * GAP_Y }
}

export function nodeStates(graph: GraphInfo, execution: Execution | null | undefined): Map<string, NodeState> {
  const states = new Map<string, NodeState>()
  for (const n of graph.nodes) states.set(n.id, 'idle')
  if (!execution) return states
  const failed = execution.status === 'error' ? execution.error?.node ?? execution.path[execution.path.length - 1] : null
  for (const n of graph.nodes) states.set(n.id, 'skipped')
  for (const id of execution.path) states.set(id, 'ok')
  if (failed) states.set(failed, 'error')
  states.set('__start__', 'ok')
  states.set('__end__', execution.status === 'ok' ? 'ok' : 'skipped')
  return states
}

export function activeEdgeKeys(graph: GraphInfo, execution: Execution | null | undefined): Set<string> {
  const keys = new Set<string>()
  if (!execution || execution.path.length === 0) return keys
  const seq = ['__start__', ...execution.path, ...(execution.status === 'ok' ? ['__end__'] : [])]
  for (let i = 0; i < seq.length - 1; i++) {
    if (graph.edges.some((e) => e.source === seq[i] && e.target === seq[i + 1])) keys.add(`${seq[i]}>${seq[i + 1]}`)
  }
  return keys
}
