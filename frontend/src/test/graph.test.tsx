import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { GraphView } from '../components/GraphView'
import { activeEdgeKeys, layoutGraph, nodeStates } from '../lib/graphLayout'
import type { ChatResponse, GraphInfo } from '../types'
import chatFixture from './fixtures/chat.json'
import graphFixture from './fixtures/graph.json'

// Fixtures are real responses captured from the FastAPI app (GET /api/graph, POST /api/chat).
const graph = graphFixture as unknown as GraphInfo
const chat = chatFixture as unknown as ChatResponse

describe('graph layout from API data', () => {
  it('places exactly the nodes the backend reports', () => {
    const { nodes } = layoutGraph(graph)
    expect([...nodes.keys()].sort()).toEqual(graph.nodes.map((n) => n.id).sort())
  })

  it('ranks start above router above the intent nodes above end', () => {
    const { nodes } = layoutGraph(graph)
    const y = (id: string) => nodes.get(id)!.y
    expect(y('__start__')).toBeLessThan(y('load_memory_node'))
    expect(y('load_memory_node')).toBeLessThan(y('router_node'))
    expect(y('router_node')).toBeLessThan(y('explanation_node'))
    expect(y('response_node')).toBeLessThan(y('memory_update_node'))
    expect(y('memory_update_node')).toBeLessThan(y('__end__'))
  })

  it('exposes conditional edges from the router', () => {
    const cond = graph.edges.filter((e) => e.conditional)
    expect(cond.length).toBeGreaterThan(0)
    expect(cond.every((e) => e.source === 'router_node')).toBe(true)
  })
})

describe('execution overlay', () => {
  it('marks only visited nodes ok and others skipped', () => {
    const states = nodeStates(graph, chat.execution)
    for (const id of chat.execution.path) expect(states.get(id)).toBe('ok')
    expect(states.get('quiz_node')).toBe('skipped')
    expect(states.get('summarization_node')).toBe('skipped')
  })

  it('highlights consecutive edges along the path', () => {
    const keys = activeEdgeKeys(graph, chat.execution)
    expect(keys.has('router_node>explanation_node')).toBe(true)
    expect(keys.has('router_node>quiz_node')).toBe(false)
  })

  it('marks the failing node as error when a run failed', () => {
    const failed = { ...chat.execution, status: 'error' as const, error: { message: 'boom', code: 'llm_error', node: 'explanation_node' }, path: ['load_memory_node', 'router_node', 'explanation_node'] }
    const states = nodeStates(graph, failed)
    expect(states.get('explanation_node')).toBe('error')
    expect(states.get('__end__')).toBe('skipped')
  })

  it('is all idle without an execution', () => {
    expect([...nodeStates(graph, null).values()].every((s) => s === 'idle')).toBe(true)
  })
})

describe('<GraphView>', () => {
  it('renders a labelled element per graph node', () => {
    render(<GraphView graph={graph} execution={chat.execution} />)
    for (const n of graph.nodes.filter((x) => x.type === 'node')) {
      expect(screen.getAllByText(new RegExp(n.title ?? n.name, 'i')).length).toBeGreaterThan(0)
    }
  })
})
