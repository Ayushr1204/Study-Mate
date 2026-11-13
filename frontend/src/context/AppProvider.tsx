import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, getBudgetOverride, getUserId, setBudgetOverride, setUserId } from '../services/api'
import type { Health, LlmStatus } from '../types'
import { AppContext } from './app-context'

export function AppProvider({ children }: { children: ReactNode }) {
  const [userId, setUserState] = useState(getUserId())
  const [budget, setBudgetState] = useState<number | null>(getBudgetOverride())
  const [health, setHealth] = useState<Health | null>(null)
  const [llm, setLlm] = useState<LlmStatus | null>(null)
  const [llmTick, setLlmTick] = useState(0)

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null))
  }, [])
  useEffect(() => {
    let cancelled = false
    api
      .llmStatus()
      .then((s) => !cancelled && setLlm(s))
      .catch(() => !cancelled && setLlm(null))
    return () => {
      cancelled = true
    }
  }, [llmTick])

  const setUser = useCallback((id: string) => {
    setUserId(id)
    setUserState(id)
  }, [])
  const setBudget = useCallback((value: number | null) => {
    setBudgetOverride(value)
    setBudgetState(value)
  }, [])
  const refreshLlm = useCallback(() => setLlmTick((t) => t + 1), [])

  const value = useMemo(
    () => ({ userId, setUser, budget, setBudget, health, llm, refreshLlm }),
    [userId, setUser, budget, setBudget, health, llm, refreshLlm],
  )
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}
