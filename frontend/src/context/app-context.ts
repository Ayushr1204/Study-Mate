import { createContext, useContext } from 'react'
import type { Health, LlmStatus } from '../types'

export interface AppState {
  userId: string
  setUser: (id: string) => void
  budget: number | null
  setBudget: (value: number | null) => void
  health: Health | null
  llm: LlmStatus | null
  refreshLlm: () => void
}

export const AppContext = createContext<AppState | null>(null)

export function useApp(): AppState {
  const ctx = useContext(AppContext)
  if (!ctx) throw new Error('useApp must be used inside <AppProvider>')
  return ctx
}
