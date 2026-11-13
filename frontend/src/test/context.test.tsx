import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ContextInspector } from '../components/ContextInspector'
import type { ChatResponse, ContextStats } from '../types'
import chatFixture from './fixtures/chat.json'

const chat = chatFixture as unknown as ChatResponse

describe('<ContextInspector>', () => {
  it('shows an empty state without statistics', () => {
    render(<ContextInspector stats={null} />)
    expect(screen.getByText(/no context data yet/i)).toBeInTheDocument()
  })

  it('shows the token counter and budget reported by the backend', () => {
    const stats = chat.execution.context as ContextStats
    render(<ContextInspector stats={stats} />)
    expect(screen.getAllByText(new RegExp(stats.token_budget.toLocaleString())).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/approx/i).length).toBeGreaterThan(0)
  })

  it('reports trimmed messages from decisions rather than inventing them', () => {
    const stats = {
      ...(chat.execution.context as ContextStats),
      total_messages: 2,
      retained_messages: 1,
      excluded_messages: 1,
      trimmed_messages: 1,
      decisions: [['excluded_trimmed', 900, 0, 0], ['retained', 20, 20, 0]],
    } as ContextStats
    const messages = [
      { id: '1', index: 0, role: 'user' as const, content: 'old long question', created_at: null, meta: {} },
      { id: '2', index: 1, role: 'user' as const, content: 'latest question', created_at: null, meta: {} },
    ]
    render(<ContextInspector stats={stats} messages={messages} />)
    expect(screen.getByText(/trimmed \(over budget\)/i)).toBeInTheDocument()
    expect(screen.getByText(/sent to model/i)).toBeInTheDocument()
  })
})
