import type { ButtonHTMLAttributes, ReactNode } from 'react'
import { AlertTriangle, Loader2, RotateCw } from 'lucide-react'
import { ApiError } from '../services/api'
import { cx } from './styles'


type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'

export function Button({
  variant = 'secondary',
  size = 'md',
  loading = false,
  className,
  children,
  disabled,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: 'sm' | 'md'; loading?: boolean }) {
  const styles: Record<Variant, string> = {
    primary: 'bg-accent text-accent-fg hover:brightness-110 font-medium',
    secondary: 'bg-raised text-fg border border-line hover:bg-hover hover:border-line-strong',
    ghost: 'text-muted hover:text-fg hover:bg-hover',
    danger: 'bg-transparent text-danger border border-danger/40 hover:bg-danger/10',
  }
  return (
    <button
      {...rest}
      disabled={disabled || loading}
      className={cx(
        'inline-flex items-center justify-center gap-2 rounded-md transition-colors disabled:opacity-50 disabled:cursor-not-allowed select-none',
        size === 'sm' ? 'h-7 px-2.5 text-xs' : 'h-9 px-3.5 text-sm',
        styles[variant],
        className,
      )}
    >
      {loading && <Loader2 className="size-4 animate-spin" aria-hidden />}
      {children}
    </button>
  )
}

export function Card({
  title,
  description,
  action,
  children,
  className,
  padded = true,
}: {
  title?: ReactNode
  description?: ReactNode
  action?: ReactNode
  children: ReactNode
  className?: string
  padded?: boolean
}) {
  return (
    <section className={cx('rounded-lg border border-line bg-surface shadow-[0_1px_2px_rgba(60,50,20,0.05)]', className)}>
      {(title || action) && (
        <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-fg">{title}</h2>
            {description && <p className="mt-0.5 text-xs text-muted">{description}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={padded ? 'p-4' : ''}>{children}</div>
    </section>
  )
}

type Tone = 'neutral' | 'accent' | 'ok' | 'warn' | 'danger' | 'info'
export function Chip({ tone = 'neutral', children, title, className }: { tone?: Tone; children: ReactNode; title?: string; className?: string }) {
  const tones: Record<Tone, string> = {
    neutral: 'bg-raised text-muted border-line',
    accent: 'bg-accent-soft text-accent border-accent/30',
    ok: 'bg-ok/10 text-ok border-ok/30',
    warn: 'bg-warn/10 text-warn border-warn/30',
    danger: 'bg-danger/10 text-danger border-danger/30',
    info: 'bg-info/10 text-info border-info/30',
  }
  return (
    <span title={title} className={cx('inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap', tones[tone], className)}>
      {children}
    </span>
  )
}

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-muted" role="status">
      <Loader2 className="size-4 animate-spin" aria-hidden />
      {label}
    </span>
  )
}

export function EmptyState({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-12 text-center">
      {icon && <div className="mb-3 text-faint">{icon}</div>}
      <p className="text-sm font-medium text-fg">{title}</p>
      {children && <p className="mt-1 max-w-sm text-sm text-muted">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export function ErrorBanner({ error, onRetry, className }: { error: unknown; onRetry?: () => void; className?: string }) {
  if (!error) return null
  const e = error instanceof ApiError ? error : null
  const message = e ? e.message : error instanceof Error ? error.message : String(error)
  return (
    <div role="alert" className={cx('flex items-start gap-3 rounded-md border border-danger/40 bg-danger/10 px-3 py-2.5 text-sm', className)}>
      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-danger" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="text-fg">{message}</p>
        {e?.hint && <p className="mt-0.5 font-mono text-xs break-words text-muted">{e.hint}</p>}
        {e?.node && <p className="mt-0.5 text-xs text-muted">Failed in graph node: <span className="font-mono">{e.node}</span></p>}
      </div>
      {onRetry && (
        <Button size="sm" variant="ghost" onClick={onRetry}>
          <RotateCw className="size-3.5" /> Retry
        </Button>
      )}
    </div>
  )
}

export function Page({ children, wide = false }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="h-full overflow-y-auto">
      <div className={cx('mx-auto px-4 py-6 sm:px-6 lg:py-8', wide ? 'max-w-[88rem]' : 'max-w-6xl')}>{children}</div>
    </div>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="font-display text-2xl font-semibold tracking-tight text-fg">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-muted">{description}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Stat({ label, value, hint }: { label: string; value: ReactNode; hint?: ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-surface shadow-[0_1px_2px_rgba(60,50,20,0.05)] px-4 py-3">
      <p className="text-xs text-muted">{label}</p>
      <p className="mt-1 text-2xl font-semibold tracking-tight text-fg tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-xs text-faint">{hint}</p>}
    </div>
  )
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; icon?: ReactNode }[]; value: T; onChange: (id: T) => void }) {
  return (
    <div role="tablist" className="mb-5 flex gap-1 border-b border-line">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx(
            '-mb-px inline-flex items-center gap-2 border-b-2 px-3 py-2 text-sm transition-colors',
            value === t.id ? 'border-accent text-fg' : 'border-transparent text-muted hover:text-fg',
          )}
        >
          {t.icon}
          {t.label}
        </button>
      ))}
    </div>
  )
}

export function Segmented<T extends string | number>({ options, value, onChange, label }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex rounded-md border border-line bg-surface p-0.5">
      {options.map((o) => (
        <button
          key={String(o.value)}
          role="radio"
          aria-checked={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx('rounded px-3 py-1.5 text-xs font-medium capitalize transition-colors', value === o.value ? 'bg-hover text-fg' : 'text-muted hover:text-fg')}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

export function Bar({ value, max, tone = 'accent', label }: { value: number; max: number; tone?: 'accent' | 'warn' | 'danger' | 'info' | 'faint'; label?: string }) {
  const pct = max > 0 ? Math.min(100, Math.max(0, (value / max) * 100)) : 0
  const color = { accent: 'bg-accent', warn: 'bg-warn', danger: 'bg-danger', info: 'bg-info', faint: 'bg-line-strong' }[tone]
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-raised" role="progressbar" aria-label={label} aria-valuenow={Math.round(value)} aria-valuemin={0} aria-valuemax={Math.round(max)}>
      <div className={cx('h-full rounded-full transition-[width] duration-300', color)} style={{ width: `${pct}%` }} />
    </div>
  )
}

export function Label({ children, htmlFor }: { children: ReactNode; htmlFor?: string }) {
  return (
    <label htmlFor={htmlFor} className="mb-1.5 block text-xs font-medium text-muted">
      {children}
    </label>
  )
}

