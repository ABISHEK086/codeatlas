import { useState, type ElementType, type FormEvent } from 'react'
import {
  FolderGit2, Gauge, LayoutDashboard, LogOut, MessageSquare, Network, PanelLeftClose,
} from 'lucide-react'
import type { Repo, User } from '@/api'

export type Page = 'overview' | 'impact' | 'graph' | 'ask'

const PAGES: { id: Page; title: string; icon: ElementType; soon?: boolean }[] = [
  { id: 'overview', title: 'Overview', icon: LayoutDashboard },
  { id: 'impact', title: 'Impact analysis', icon: Gauge },
  { id: 'graph', title: 'Dependency graph', icon: Network },
  { id: 'ask', title: 'Ask CodeAtlas', icon: MessageSquare },
]
const DOT: Record<Repo['status'], string> = {
  ready: 'bg-success',
  indexing: 'bg-warning animate-pulse',
  pending: 'bg-muted-foreground',
  failed: 'bg-danger',
}

type Props = {
  user: User
  repos: Repo[]
  activeRepoId: number | null
  page: Page
  onPage: (p: Page) => void
  onSelectRepo: (id: number) => void
  onConnect: (fullName: string) => Promise<void>
  onLogout: () => void
  onCollapse: () => void
}

export default function AppSidebar(p: Props) {
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (!name.trim()) return
    setBusy(true)
    setError(null)
    try {
      await p.onConnect(name.trim())
      setName('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not connect')
    } finally {
      setBusy(false)
    }
  }

  return (
    <aside className="flex h-full w-[260px] flex-col border-r border-border bg-background p-3">
      <div className="mb-5 flex items-center justify-between px-1.5">
        <div className="flex items-center gap-2">
          <div className="grid h-7 w-7 place-items-center rounded-md border border-border bg-muted font-mono text-[11px] font-semibold">
            CA
          </div>
          <span className="text-sm font-semibold">CodeAtlas</span>
        </div>
        <button
          onClick={p.onCollapse}
          aria-label="Collapse sidebar"
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <PanelLeftClose className="h-[18px] w-[18px]" strokeWidth={1.5} />
        </button>
      </div>

      <div className="flex-1 space-y-6 overflow-y-auto">
        {p.activeRepoId !== null && (
          <nav className="space-y-0.5">
            {PAGES.map((it) => {
              const active = p.page === it.id
              return (
                <button
                  key={it.id}
                  disabled={it.soon}
                  onClick={() => p.onPage(it.id)}
                  className={`relative flex w-full items-center justify-between rounded-md px-2.5 py-[7px] text-left text-[13px] transition-colors
                    ${active ? 'bg-muted font-medium text-foreground' : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'}
                    ${it.soon ? 'cursor-not-allowed opacity-50 hover:bg-transparent hover:text-muted-foreground' : ''}`}
                >
                  {active && <span className="absolute -left-3 top-1.5 bottom-1.5 w-[3px] rounded-full bg-primary" />}
                  <span className="flex items-center gap-2.5">
                    <it.icon className="h-4 w-4" strokeWidth={1.5} />
                    {it.title}
                  </span>
                  {it.soon && <span className="font-mono text-[10px]">soon</span>}
                </button>
              )
            })}
          </nav>
        )}

        <div>
          <h2 className="mb-1.5 px-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground/70">
            Repositories
          </h2>
          <ul className="space-y-0.5">
            {p.repos.map((r) => (
              <li key={r.id}>
                <button
                  onClick={() => p.onSelectRepo(r.id)}
                  className={`flex w-full items-center gap-2.5 rounded-md px-2.5 py-[7px] text-left text-[13px] transition-colors
                    ${r.id === p.activeRepoId ? 'text-foreground' : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'}`}
                >
                  <FolderGit2 className="h-4 w-4 shrink-0" strokeWidth={1.5} />
                  <span className="min-w-0 flex-1 truncate">{r.full_name}</span>
                  <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[r.status]}`} title={r.status} />
                </button>
              </li>
            ))}
          </ul>

          <form onSubmit={submit} className="mt-2 px-1">
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="owner/repository"
              disabled={busy}
              className="w-full rounded-md border border-border bg-card px-2.5 py-1.5 font-mono text-xs outline-none placeholder:text-muted-foreground/60 focus:border-primary focus:ring-1 focus:ring-primary"
            />
            <p className="mt-1.5 text-[11px] text-muted-foreground">
              {busy ? 'Connecting…' : 'Press Enter to connect a repository'}
            </p>
            {error && <p className="mt-1 text-[11px] text-danger">{error}</p>}
          </form>
        </div>
      </div>

      <div className="mt-3 flex items-center gap-2.5 border-t border-border px-1.5 pt-3">
        {p.user.avatar_url && <img src={p.user.avatar_url} alt="" className="h-7 w-7 rounded-full border border-border" />}
        <span className="min-w-0 flex-1 truncate text-[13px]">{p.user.login}</span>
        <button
          onClick={p.onLogout}
          aria-label="Log out"
          className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <LogOut className="h-4 w-4" strokeWidth={1.5} />
        </button>
      </div>
    </aside>
  )
}