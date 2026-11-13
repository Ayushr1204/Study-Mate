import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../services/api'

interface Result<T> {
  key: string
  data?: T
  error?: ApiError
}

/**
 * Loads data when `deps` change (or `reload()` is called). Keeps showing the previous data while a
 * refresh is in flight (`loading` is derived, so there is no synchronous setState inside the effect).
 */
export function useAsync<T>(fn: () => Promise<T>, deps: readonly unknown[]) {
  const [tick, setTick] = useState(0)
  const [result, setResult] = useState<Result<T> | null>(null)
  const fnRef = useRef(fn)
  useEffect(() => {
    fnRef.current = fn
  })
  const key = `${tick}|${JSON.stringify(deps)}`

  useEffect(() => {
    let cancelled = false
    fnRef
      .current()
      .then((data) => {
        if (!cancelled) setResult({ key, data })
      })
      .catch((e: unknown) => {
        if (!cancelled) setResult({ key, error: e instanceof ApiError ? e : new ApiError(String(e), 0) })
      })
    return () => {
      cancelled = true
    }
  }, [key])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const settled = result?.key === key
  return {
    data: result?.data,
    error: settled ? result?.error : undefined,
    loading: !settled,
    reload,
  }
}
