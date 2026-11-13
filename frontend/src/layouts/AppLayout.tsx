import { useState } from 'react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { Database, FileText, LayoutDashboard, ListChecks, Menu, MessagesSquare, Settings, Workflow, X } from 'lucide-react'
import { useApp } from '../context/app-context'
import { Logo } from '../components/Logo'
import { cx } from '../components/styles'

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/chat', label: 'Study Chat', icon: MessagesSquare },
  { to: '/quiz', label: 'Quiz Generator', icon: ListChecks },
  { to: '/summarize', label: 'Notes Summarizer', icon: FileText },
  { to: '/graph', label: 'Graph Explorer', icon: Workflow },
  { to: '/inspector', label: 'Memory & State', icon: Database },
  { to: '/settings', label: 'Settings', icon: Settings },
]

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-3">
      <Logo className="size-8 shrink-0" />
      <div className="leading-tight">
        <span className="font-display block text-[17px] font-semibold tracking-tight">StudyMate</span>
        <span className="block text-[11px] text-faint">AI study assistant</span>
      </div>
    </div>
  )
}

function LlmBadge() {
  const { llm, health } = useApp()
  let dot = 'bg-faint'
  let text = 'Checking model…'
  if (llm) {
    const offline = llm.provider === 'offline' || llm.active === 'offline'
    if (offline) {
      dot = 'bg-warn'
      text = llm.provider === 'offline' ? 'Offline mode' : 'Offline fallback'
    } else if (llm.reachable && llm.model_available) {
      dot = 'bg-ok'
      text = `${llm.provider} · ${llm.model}`
    } else {
      dot = 'bg-danger'
      text = 'Model unavailable'
    }
  } else if (health) {
    text = `${health.llm.provider} · ${health.llm.model}`
  }
  return (
    <NavLink to="/settings" className="flex items-center gap-2 rounded-md px-3 py-2 text-xs text-muted hover:bg-hover hover:text-fg" title="LLM status (Settings)">
      <span className={cx('size-2 shrink-0 rounded-full', dot)} aria-hidden />
      <span className="truncate">{text}</span>
    </NavLink>
  )
}

function SidebarContent({ onNavigate }: { onNavigate?: () => void }) {
  const { userId } = useApp()
  return (
    <div className="flex h-full flex-col gap-6 py-5">
      <Brand />
      <nav aria-label="Main" className="flex flex-1 flex-col gap-0.5 px-2">
        {NAV.map(({ to, label, icon: Icon, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            onClick={onNavigate}
            className={({ isActive }) =>
              cx(
                'flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors',
                isActive ? 'bg-accent-soft font-medium text-accent' : 'text-muted hover:bg-hover/70 hover:text-fg',
              )
            }
          >
            <Icon className="size-4 shrink-0" aria-hidden />
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="space-y-1 border-t border-line px-2 pt-3">
        <LlmBadge />
        <p className="truncate px-3 text-xs text-faint" title="Active user id (memory and conversations are scoped to it)">
          user: <span className="font-mono text-muted">{userId}</span>
        </p>
      </div>
    </div>
  )
}

export function AppLayout() {
  const [open, setOpen] = useState(false)
  const location = useLocation()
  return (
    <div className="flex h-dvh bg-canvas">
      <aside className="hidden w-60 shrink-0 border-r border-line bg-surface md:block">
        <SidebarContent />
      </aside>

      {open && (
        <div className="fixed inset-0 z-40 md:hidden" role="dialog" aria-modal="true" aria-label="Navigation">
          <button className="absolute inset-0 bg-black/60" aria-label="Close menu" onClick={() => setOpen(false)} />
          <aside className="relative h-full w-64 border-r border-line bg-surface">
            <button className="absolute top-4 right-3 rounded p-1 text-muted hover:text-fg" onClick={() => setOpen(false)} aria-label="Close menu">
              <X className="size-4" />
            </button>
            <SidebarContent onNavigate={() => setOpen(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-line bg-surface px-3 md:hidden">
          <button className="rounded p-1.5 text-muted hover:text-fg" onClick={() => setOpen(true)} aria-label="Open menu">
            <Menu className="size-5" />
          </button>
          <Brand />
        </header>
        <main className="min-h-0 flex-1" key={location.pathname.split('/')[1]}>
          <Outlet />
        </main>
      </div>
    </div>
  )
}
