export function formatTime(iso: string | null | undefined): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

export function relativeTime(iso: string | null | undefined, now: number = Date.now()): string {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const s = Math.max(0, Math.round((now - t) / 1000))
  if (s < 45) return 'just now'
  if (s < 3600) return `${Math.round(s / 60)} min ago`
  if (s < 86400) return `${Math.round(s / 3600)} h ago`
  if (s < 86400 * 7) return `${Math.round(s / 86400)} d ago`
  return new Date(iso).toLocaleDateString([], { month: 'short', day: 'numeric' })
}

export const FIELD_LABELS: Record<string, string> = {
  preferred_explanation_style: 'Explanation style',
  preferred_programming_language: 'Programming language',
  current_subjects: 'Current subjects',
  learning_preferences: 'Learning preferences',
  topics_studied: 'Topics studied',
  revision_areas: 'Needs revision',
}

export function nodeLabel(id: string): string {
  return id.replace(/_node$/, '').replace(/^__(\w+)__$/, '$1').replace(/_/g, ' ')
}

export function plural(n: number, one: string, many = `${one}s`): string {
  return `${n} ${n === 1 ? one : many}`
}
