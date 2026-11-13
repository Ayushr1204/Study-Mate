import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { RefreshCw } from 'lucide-react'
import { Button, Card, Chip, ErrorBanner, Label, Page, PageHeader } from '../components/ui'
import { inputClass } from '../components/styles'
import { useApp } from '../context/app-context'
import { api } from '../services/api'

const USER_RE = /^[A-Za-z0-9_.-]{1,64}$/

export function SettingsPage() {
  const { userId, setUser, budget, setBudget, health, llm, refreshLlm } = useApp()
  const navigate = useNavigate()
  const [userDraft, setUserDraft] = useState(userId)
  const [budgetDraft, setBudgetDraft] = useState(budget ? String(budget) : '')
  const [confirm, setConfirm] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const userValid = USER_RE.test(userDraft)
  const budgetNum = budgetDraft.trim() === '' ? null : Number(budgetDraft)
  const budgetValid = budgetNum === null || (Number.isInteger(budgetNum) && budgetNum >= 200 && budgetNum <= 200000)

  const wipe = async () => {
    setBusy(true)
    setError(null)
    try {
      const r = await api.deleteAllData()
      setNotice(`Deleted ${r.deleted_threads} conversation(s), quizzes, and the learning profile for “${userId}”.`)
      setConfirm(false)
    } catch (e) {
      setError(e)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Page>
      <PageHeader title="Settings" description="Identity, context budget and model status. Preferences are stored in this browser; data lives in the backend database." />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Student identity" description="Each user id has its own conversations and its own long-term memory namespace.">
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (userValid && userDraft !== userId) { setUser(userDraft); navigate('/') } }}>
            <div>
              <Label htmlFor="user-id">User id</Label>
              <input id="user-id" className={inputClass} value={userDraft} onChange={(e) => setUserDraft(e.target.value)} aria-invalid={!userValid} />
              {!userValid && <p className="mt-1 text-xs text-danger">Use 1–64 letters, digits, dot, dash or underscore.</p>}
            </div>
            <Button type="submit" variant="primary" disabled={!userValid || userDraft === userId}>Switch user</Button>
          </form>
        </Card>

        <Card title="Context token budget" description={`Server default: ${health?.context_token_budget?.toLocaleString() ?? '…'} tokens. Lower it to watch trimming happen.`}>
          <form className="space-y-3" onSubmit={(e) => { e.preventDefault(); if (budgetValid) setBudget(budgetNum) }}>
            <div>
              <Label htmlFor="budget">Override (tokens)</Label>
              <input id="budget" inputMode="numeric" className={inputClass} value={budgetDraft} onChange={(e) => setBudgetDraft(e.target.value)} placeholder="Use server default" aria-invalid={!budgetValid} />
              {!budgetValid && <p className="mt-1 text-xs text-danger">Enter a whole number between 200 and 200000, or leave empty.</p>}
            </div>
            <div className="flex gap-2">
              <Button type="submit" variant="primary" disabled={!budgetValid}>Apply</Button>
              <Button type="button" onClick={() => { setBudgetDraft(''); setBudget(null) }}>Reset</Button>
            </div>
            <p className="text-xs text-faint">Token counter: <span className="font-mono">{health?.token_counter ?? '…'}</span></p>
          </form>
        </Card>

        <Card title="Language model" action={<Button size="sm" onClick={refreshLlm}><RefreshCw className="size-3.5" /> Refresh</Button>} className="lg:col-span-2">
          {!llm && <p className="text-sm text-muted">Checking…</p>}
          {llm && (
            <div className="space-y-3 text-sm">
              <div className="flex flex-wrap gap-1.5">
                <Chip tone="info">{llm.provider} · {llm.model}</Chip>
                <Chip tone={llm.reachable ? 'ok' : 'danger'}>{llm.reachable ? 'reachable' : 'unreachable'}</Chip>
                {llm.reachable && <Chip tone={llm.model_available ? 'ok' : 'warn'}>{llm.model_available ? 'model available' : 'model not installed'}</Chip>}
                <Chip tone={llm.active === 'offline' ? 'warn' : 'neutral'}>active: {llm.active ?? 'primary'}</Chip>
                {llm.fallback && <Chip>fallback: {llm.fallback}</Chip>}
              </div>
              {llm.base_url && <p className="text-xs text-muted">Endpoint: <span className="font-mono">{llm.base_url}</span></p>}
              {llm.error && <p className="text-xs text-warn">{llm.error}</p>}
              {llm.hint && <p className="font-mono text-xs text-muted">{llm.hint}</p>}
              {llm.installed_models && llm.installed_models.length > 0 && <p className="text-xs text-muted">Installed: {llm.installed_models.join(', ')}</p>}
            </div>
          )}
        </Card>

        <Card title="Danger zone" description={`Delete everything stored for “${userId}”: conversations, checkpoints, quizzes and the long-term profile.`} className="lg:col-span-2">
          {!!error && <ErrorBanner error={error} className="mb-3" />}
          {notice && <p role="status" className="mb-3 rounded-md border border-ok/40 bg-ok/10 px-3 py-2 text-sm text-ok">{notice}</p>}
          {!confirm ? (
            <Button variant="danger" onClick={() => { setConfirm(true); setNotice(null) }}>Delete all my data…</Button>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm">This cannot be undone.</span>
              <Button variant="danger" loading={busy} onClick={() => void wipe()}>Yes, delete everything</Button>
              <Button variant="ghost" onClick={() => setConfirm(false)}>Cancel</Button>
            </div>
          )}
        </Card>
      </div>
    </Page>
  )
}
