import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { AppProvider } from '../context/AppProvider'
import { ChatPage } from '../pages/ChatPage'
import { QuizPage } from '../pages/QuizPage'
import { SettingsPage } from '../pages/SettingsPage'
import { ApiError, api } from '../services/api'
import type { ChatResponse } from '../types'
import chatFixture from './fixtures/chat.json'
import graphFixture from './fixtures/graph.json'

const chat = chatFixture as unknown as ChatResponse
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))

type Handler = (url: string, init?: RequestInit) => Promise<Response> | undefined
let calls: { url: string; init?: RequestInit }[] = []

function mockFetch(extra: Handler) {
  calls = []
  vi.stubGlobal('fetch', vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    calls.push({ url, init })
    const r = extra(url, init)
    if (r) return r
    if (url.endsWith('/api/health')) return json({ status: 'ok', version: '1.0.0', llm: { provider: 'offline', model: 'x', fallback: 'offline' }, token_counter: 'approx:chars/4', context_token_budget: 3000, default_user_id: 'demo-student' })
    if (url.endsWith('/api/llm/status')) return json({ provider: 'ollama', model: 'llama3.2', reachable: false, model_available: false, active: 'offline', error: 'connection refused' })
    if (url.endsWith('/api/graph')) return json(graphFixture)
    if (url.includes('/api/executions/latest')) return json({ execution: null })
    if (url.endsWith('/api/threads')) return json([])
    if (url.endsWith('/api/memory')) return json({ user_id: 'demo-student', namespace: ['users', 'demo-student', 'profile'], key: 'profile', found: false, created_at: null, updated_at: null, profile: { preferred_explanation_style: null, preferred_programming_language: null, current_subjects: [], learning_preferences: [], topics_studied: [], revision_areas: [], updated_at: null } })
    return json({ error: { code: 'not_found', message: `unmocked ${url}` } }, 404)
  }))
}

const wrap = (ui: React.ReactNode, path = '/') => (
  <AppProvider>
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/chat/:threadId?" element={ui} />
        <Route path="*" element={ui} />
      </Routes>
    </MemoryRouter>
  </AppProvider>
)

beforeEach(() => { localStorage.clear() })
afterEach(() => { vi.unstubAllGlobals() })

describe('api client', () => {
  it('sends the user id header and parses structured errors', async () => {
    mockFetch((url) => (url.endsWith('/api/threads') ? json({ error: { code: 'llm_unavailable', message: 'No model', hint: 'ollama serve', node: 'explanation_node' } }, 503) : undefined))
    const err = await api.listThreads().catch((e: unknown) => e)
    expect(err).toBeInstanceOf(ApiError)
    expect((err as ApiError).message).toBe('No model')
    expect((err as ApiError).hint).toBe('ollama serve')
    expect((err as ApiError).node).toBe('explanation_node')
    expect(new Headers(calls[0].init?.headers).get('X-User-Id')).toBe('demo-student')
  })
})

describe('chat workflow', () => {
  it('sends a message and shows the reply, execution path and intent from the API', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/chat') && init?.method === 'POST') return json(chat)
      if (url.includes(`/api/threads/${chat.thread_id}`)) return json({ id: chat.thread_id, title: chat.title, created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z', messages: [{ id: 'u1', index: 0, role: 'user', content: 'Explain CPU scheduling', created_at: null, meta: {} }, chat.message], last_execution: chat.execution })
      return undefined
    })
    const user = userEvent.setup()
    render(wrap(<ChatPage />, '/chat'))
    const box = await screen.findByRole('textbox')
    await user.type(box, 'Explain CPU scheduling')
    await user.click(screen.getByRole('button', { name: /send/i }))
    await waitFor(() => expect(calls.some((c) => c.url.endsWith('/api/chat'))).toBe(true))
    const body = JSON.parse(String(calls.find((c) => c.url.endsWith('/api/chat'))!.init!.body))
    expect(body.message).toBe('Explain CPU scheduling')
    expect(await screen.findByText(/intent: explanation/i)).toBeInTheDocument()
    expect(screen.getAllByText(/explanation/i).length).toBeGreaterThan(0)
  })

  it('shows the API error when a run fails', async () => {
    mockFetch((url, init) => (url.endsWith('/api/chat') && init?.method === 'POST' ? json({ error: { code: 'llm_unavailable', message: 'Model is down', hint: null, node: 'explanation_node' } }, 503) : undefined))
    const user = userEvent.setup()
    render(wrap(<ChatPage />, '/chat'))
    await user.type(await screen.findByRole('textbox'), 'hello there')
    await user.click(screen.getByRole('button', { name: /send/i }))
    expect(await screen.findByText(/model is down/i)).toBeInTheDocument()
  })
})

describe('quiz workflow', () => {
  it('generates, answers and scores a quiz using server-side grading', async () => {
    mockFetch((url, init) => {
      if (url.endsWith('/api/quizzes') && !init?.method) return json([])
      if (url.endsWith('/api/quiz/generate')) {
        return json({ quiz_id: 'q1', topic: 'Deadlock', difficulty: 'medium', requested: 1, warnings: [], execution: chat.execution, questions: [{ question: 'What is deadlock?', options: ['A', 'B', 'C', 'D'] }] })
      }
      if (url.endsWith('/api/quizzes/q1/submit')) {
        return json({ quiz_id: 'q1', topic: 'Deadlock', score: 0, total: 1, percent: 0, needs_revision: true, results: [{ question: 'What is deadlock?', options: ['A', 'B', 'C', 'D'], selected: 0, correct: 2, is_correct: false, explanation: 'Circular wait.' }] })
      }
      return undefined
    })
    const user = userEvent.setup()
    render(wrap(<QuizPage />, '/quiz'))
    await user.type(await screen.findByLabelText(/subject or topic/i), 'Deadlock')
    await user.click(screen.getByRole('button', { name: /generate quiz/i }))
    expect(await screen.findByText('What is deadlock?')).toBeInTheDocument()
    await user.click(screen.getAllByRole('radio', { hidden: true })[0])
    await user.click(screen.getByRole('button', { name: /submit answers/i }))
    expect(await screen.findByText('Circular wait.')).toBeInTheDocument()
    expect(screen.getByText(/needs revision/i)).toBeInTheDocument()
    const submitted = JSON.parse(String(calls.find((c) => c.url.endsWith('/submit'))!.init!.body))
    expect(submitted.answers).toEqual([0])
  })
})

describe('settings', () => {
  it('validates the context budget before applying it', async () => {
    mockFetch(() => undefined)
    const user = userEvent.setup()
    render(wrap(<SettingsPage />, '/settings'))
    const input = await screen.findByLabelText(/override/i)
    await user.type(input, '50')
    expect(screen.getByText(/between 200 and 200000/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /apply/i })).toBeDisabled()
    await user.clear(input)
    await user.type(input, '1500')
    await user.click(screen.getByRole('button', { name: /apply/i }))
    expect(localStorage.getItem('studymate.budget')).toBe('1500')
  })

  it('reports an unreachable model from the status endpoint', async () => {
    mockFetch(() => undefined)
    render(wrap(<SettingsPage />, '/settings'))
    expect(await screen.findByText('unreachable')).toBeInTheDocument()
    expect(screen.getByText(/active: offline/i)).toBeInTheDocument()
  })
})
