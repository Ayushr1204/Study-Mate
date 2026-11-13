import type {
  ChatResponse,
  DashboardData,
  DocumentExtract,
  Execution,
  GraphInfo,
  Health,
  LlmStatus,
  MemoryInfo,
  QuizHistoryItem,
  QuizResponse,
  QuizResult,
  SummaryResponse,
  Thread,
  ThreadDetail,
  ThreadState,
} from '../types'

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? ''
const USER_KEY = 'studymate.user'
const BUDGET_KEY = 'studymate.budget'
export const DEFAULT_USER = 'demo-student'

function read(key: string): string | null {
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}
function write(key: string, value: string | null): void {
  try {
    if (value === null) localStorage.removeItem(key)
    else localStorage.setItem(key, value)
  } catch {
    /* storage unavailable: the setting simply lasts for this page view */
  }
}

let memoryUser: string | null = null
let memoryBudget: number | null = null

export function getUserId(): string {
  return memoryUser ?? read(USER_KEY) ?? DEFAULT_USER
}
export function setUserId(id: string): void {
  memoryUser = id
  write(USER_KEY, id)
}
export function getBudgetOverride(): number | null {
  if (memoryBudget !== null) return memoryBudget
  const raw = read(BUDGET_KEY)
  const n = raw ? Number(raw) : NaN
  return Number.isFinite(n) && n >= 200 ? n : null
}
export function setBudgetOverride(value: number | null): void {
  memoryBudget = value
  write(BUDGET_KEY, value === null ? null : String(value))
}

export class ApiError extends Error {
  status: number
  code: string
  hint: string | null
  node: string | null
  constructor(message: string, status: number, code = 'error', hint: string | null = null, node: string | null = null) {
    super(message)
    this.status = status
    this.code = code
    this.hint = hint
    this.node = node
  }
}

interface Options {
  method?: string
  body?: unknown
  form?: FormData
  signal?: AbortSignal
}

async function request<T>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = { 'X-User-Id': getUserId() }
  let body: BodyInit | undefined
  if (opts.form) body = opts.form
  else if (opts.body !== undefined) {
    headers['Content-Type'] = 'application/json'
    body = JSON.stringify(opts.body)
  }
  let res: Response
  try {
    res = await fetch(`${BASE}/api${path}`, { method: opts.method ?? 'GET', headers, body, signal: opts.signal })
  } catch (e) {
    if (e instanceof DOMException && e.name === 'AbortError') throw e
    throw new ApiError(
      'Cannot reach the StudyMate backend.',
      0,
      'network',
      'Start it with: cd backend && uvicorn app.main:app_factory --factory --port 8000',
    )
  }
  if (res.status === 204) return undefined as T
  const text = await res.text()
  let data: unknown = null
  try {
    data = text ? JSON.parse(text) : null
  } catch {
    /* non-JSON error body (e.g. a proxy error page) */
  }
  if (!res.ok) {
    const err = (data as { error?: { message?: string; code?: string; hint?: string | null; node?: string | null } } | null)?.error
    if (err) throw new ApiError(err.message ?? 'Request failed', res.status, err.code, err.hint ?? null, err.node ?? null)
    const detail = (data as { detail?: unknown } | null)?.detail
    throw new ApiError(typeof detail === 'string' ? detail : `Request failed (HTTP ${res.status})`, res.status)
  }
  return data as T
}

export const api = {
  health: () => request<Health>('/health'),
  llmStatus: () => request<LlmStatus>('/llm/status'),
  graph: () => request<GraphInfo>('/graph'),
  dashboard: () => request<DashboardData>('/dashboard'),

  listThreads: () => request<Thread[]>('/threads'),
  createThread: (title?: string) => request<Thread>('/threads', { method: 'POST', body: { title: title ?? null } }),
  getThread: (id: string) => request<ThreadDetail>(`/threads/${id}`),
  renameThread: (id: string, title: string) => request<Thread>(`/threads/${id}`, { method: 'PATCH', body: { title } }),
  deleteThread: (id: string) => request<void>(`/threads/${id}`, { method: 'DELETE' }),
  threadState: (id: string) => request<ThreadState>(`/threads/${id}/state`),
  latestExecution: (threadId?: string) =>
    request<{ execution: Execution | null }>(`/executions/latest${threadId ? `?thread_id=${encodeURIComponent(threadId)}` : ''}`),
  chat: (threadId: string | null, message: string, signal?: AbortSignal) => {
    const budget = getBudgetOverride()
    return request<ChatResponse>('/chat', {
      method: 'POST',
      body: { thread_id: threadId, message, ...(budget ? { context_budget: budget } : {}) },
      signal,
    })
  },

  generateQuiz: (topic: string, difficulty: string, numQuestions: number) => {
    const budget = getBudgetOverride()
    return request<QuizResponse>('/quiz/generate', {
      method: 'POST',
      body: { topic, difficulty, num_questions: numQuestions, ...(budget ? { context_budget: budget } : {}) },
    })
  },
  submitQuiz: (id: string, answers: (number | null)[]) =>
    request<QuizResult>(`/quizzes/${id}/submit`, { method: 'POST', body: { answers } }),
  quizzes: () => request<QuizHistoryItem[]>('/quizzes'),

  summarize: (text: string, include: string[], length: string) => {
    const budget = getBudgetOverride()
    return request<SummaryResponse>('/summarize', {
      method: 'POST',
      body: { text, include, length, ...(budget ? { context_budget: budget } : {}) },
    })
  },
  extractDocument: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<DocumentExtract>('/documents/extract', { method: 'POST', form })
  },

  memory: () => request<MemoryInfo>('/memory'),
  patchMemory: (fields: Record<string, unknown>) => request<MemoryInfo>('/memory', { method: 'PATCH', body: fields }),
  deleteMemoryField: (field: string, value?: string) =>
    request<MemoryInfo>(`/memory/${field}${value !== undefined ? `?value=${encodeURIComponent(value)}` : ''}`, { method: 'DELETE' }),
  clearMemory: () => request<void>('/memory', { method: 'DELETE' }),
  deleteAllData: () => request<{ deleted_threads: number }>('/user/data', { method: 'DELETE' }),
}
