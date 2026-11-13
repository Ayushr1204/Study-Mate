// Types mirror the FastAPI response schemas (backend/app/models/schemas.py).

export interface Health {
  status: string
  version: string
  llm: { provider: string; model: string; fallback: string }
  token_counter: string
  context_token_budget: number
  default_user_id: string
}

export interface LlmStatus {
  provider: string
  model: string
  base_url?: string
  reachable: boolean
  model_available: boolean
  active?: 'primary' | 'offline'
  fallback?: string
  installed_models?: string[]
  error?: string | null
  hint?: string | null
}

export interface Thread {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface ChatMessage {
  id: string | null
  index: number | null
  role: 'user' | 'assistant' | 'system'
  content: string
  created_at: string | null
  meta: {
    intent?: string
    content_type?: string
    provider?: string | null
    model?: string | null
    fallback_reason?: string | null
    run_id?: string | null
    memory_fields_used?: string[]
  } & Record<string, unknown>
}

export interface TraceEntry {
  node: string
  status: string
  started_at: string
  duration_ms: number
  detail: Record<string, unknown>
}

export interface ContextStats {
  total_messages: number
  retained_messages: number
  excluded_messages: number
  filtered_messages: number
  trimmed_messages: number
  truncated_messages: number
  tokens_before: number
  tokens_after: number
  token_budget: number
  system_prompt_tokens: number
  max_message_tokens: number
  token_counter: string
  token_counter_exact: boolean
  within_budget: boolean
  scope: 'conversation' | 'summarization_prompt'
  /** Index-aligned with the thread's messages: [status, tokens, tokens_sent, truncated] */
  decisions: [string, number, number, number][]
  processing?: Record<string, unknown>
}

export interface RetrievedMemory {
  namespace: string[]
  key: string
  found: boolean
  fields: string[]
  updated_at: string | null
}

export interface MemoryChange {
  field: string
  action: string
  old?: string | null
  new: string
}

export interface Execution {
  request_id: string
  thread_id: string
  user_id: string
  kind: string
  created_at: string
  status: 'ok' | 'error'
  error: { message: string; hint?: string | null; code: string; node?: string | null } | null
  intent: string | null
  topic: string | null
  route: { intent?: string; method?: string; reason?: string; topic?: string | null }
  path: string[]
  trace: TraceEntry[]
  duration_ms: number
  context: Partial<ContextStats>
  retrieved_memory: Partial<RetrievedMemory>
  memory_changes: MemoryChange[]
  llm: { provider?: string; model?: string; fallback_reason?: string | null; latency_ms?: number }
}

export interface ThreadDetail extends Thread {
  messages: ChatMessage[]
  last_execution: Execution | null
}

export interface ChatResponse {
  thread_id: string
  title: string
  message: ChatMessage
  execution: Execution
}

export interface GraphNode {
  id: string
  name: string
  type: 'start' | 'end' | 'node'
  title?: string
  kind?: 'memory' | 'router' | 'processing' | 'response'
  description?: string
  reads?: string[]
  writes?: string[]
}

export interface GraphEdge {
  source: string
  target: string
  conditional: boolean
  label: string | null
}

export interface GraphInfo {
  name: string
  nodes: GraphNode[]
  edges: GraphEdge[]
  mermaid: string
  reducers: Record<string, { reducer: string; behaviour: string }>
  state_fields: string[]
  intents: string[]
}

export interface TopicRecord {
  topic: string
  count: number
  last_studied: string
}

export interface Profile {
  preferred_explanation_style: string | null
  preferred_programming_language: string | null
  current_subjects: string[]
  learning_preferences: string[]
  topics_studied: TopicRecord[]
  revision_areas: string[]
  updated_at: string | null
}

export interface MemoryInfo {
  user_id: string
  namespace: string[]
  key: string
  found: boolean
  created_at: string | null
  updated_at: string | null
  profile: Profile
}

export interface Insight {
  kind: string
  topic: string
  count: number
  intents: string[]
  first_seen: string
  last_seen: string
}

export interface CheckpointInfo {
  checkpoint_id: string
  step: number | null
  source: string | null
  created_at: string | null
  next: string[]
  writes: string[]
  message_count: number
  insight_count: number
}

export interface ThreadState {
  thread_id: string
  checkpoint_id: string | null
  next: string[]
  message_count: number
  storage: { checkpointer: string; database: string; long_term_store: string; store_database: string }
  values: {
    intent: string | null
    topic: string | null
    student_profile: Profile | null
    retrieved_memory: RetrievedMemory | null
    learning_insights: Insight[]
    context_statistics: ContextStats | null
    execution_metadata: { run_id?: string; trace: TraceEntry[] } | null
    generated_content_type: string | null
  }
  checkpoints: CheckpointInfo[]
  checkpoints_truncated: boolean
  reducers: Record<string, { reducer: string; behaviour: string }>
}

export interface QuizQuestionPublic {
  question: string
  options: string[]
}

export interface QuizResponse {
  quiz_id: string
  topic: string
  difficulty: string
  requested: number
  questions: QuizQuestionPublic[]
  warnings: string[]
  execution: Execution
}

export interface QuizResultItem {
  question: string
  options: string[]
  selected: number | null
  correct: number
  is_correct: boolean
  explanation: string
}

export interface QuizResult {
  quiz_id: string
  topic: string
  score: number
  total: number
  percent: number
  results: QuizResultItem[]
  needs_revision: boolean
}

export interface QuizHistoryItem {
  id: string
  topic: string
  difficulty: string
  created_at: string
  num_questions: number
  attempts: number
  best_score: number | null
}

export interface SummaryResponse {
  title: string
  summary: string
  key_concepts: string[]
  revision_notes: string[]
  key_terms: { term: string; definition: string }[]
  processing: Record<string, unknown>
  execution: Execution
}

export interface DocumentExtract {
  text: string
  info: { filename: string; extension: string; bytes: number; characters: number; pages: number | null; truncated: boolean }
}

export interface DashboardData {
  user_id: string
  recent_threads: Thread[]
  thread_count: number
  recent_topics: TopicRecord[]
  quiz: {
    quizzes_generated: number
    attempts: number
    average_percent: number | null
    recent_attempts: { id: number; score: number; total: number; created_at: string; topic: string }[]
  }
  profile: MemoryInfo
  runs_by_intent: Record<string, number>
  recent_executions: { request_id: string; thread_id: string; intent: string | null; status: string; created_at: string; duration_ms: number | null; kind: string }[]
}
