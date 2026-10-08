import { useCallback, useEffect, useState } from 'react'
import { PanelLeftOpen } from 'lucide-react'
import { api, ApiError, LOGIN_URL, type Repo, type User } from '@/api'
import AppSidebar, { type Page } from '@/components/app-sidebar'
import Overview from '@/components/overview'
import ContributionSkyline from '@/components/ui/contribution-skyline'

function LoginScreen() {
  return (
    <main className="mx-auto flex min-h-full w-full max-w-[980px] flex-col justify-center px-4 py-12 sm:px-8">
      <div className="mb-10 max-w-xl">
        <p className="mb-3 font-mono text-xs text-primary">codeatlas</p>
        <h1 className="text-4xl font-semibold tracking-tight">Know what breaks before you change it.</h1>
        <p className="mt-3 text-muted-foreground">
          Connect a GitHub repository to see its dependency graph, affected tests and API routes,
          and a risk score for any change, with the evidence behind every claim.
        </p>
        <a
          href={LOGIN_URL}
          className="mt-6 inline-flex rounded-md border border-white/10 bg-[#238636] px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-[#2ea043]"
        >
          Sign in with GitHub
        </a>
      </div>
      <ContributionSkyline seed={11} footer="Sample data. Sign in to see your own repositories." />
    </main>
  )
}

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [repos, setRepos] = useState<Repo[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [page, setPage] = useState<Page>('overview')
  const [open, setOpen] = useState(true)

  const load = useCallback(async () => {
    try {
      setRepos(await api.repos())
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onLogout()
    }
  }, [onLogout])

  useEffect(() => { load() }, [load])

  const working = repos.some((r) => r.status === 'pending' || r.status === 'indexing')
  useEffect(() => {
    if (!working) return
    const t = setInterval(load, 3000)
    return () => clearInterval(t)
  }, [working, load])

  const connect = async (fullName: string) => {
    const repo = await api.connect(fullName)
    setSelectedId(repo.id)
    await load()
  }

  const repo = repos.find((r) => r.id === selectedId) ?? repos[0] ?? null

  return (
    <div className="flex h-full">
      <div className={`shrink-0 overflow-hidden transition-[width] duration-200 ${open ? 'w-[260px]' : 'w-0'}`}>
        <AppSidebar
          user={user}
          repos={repos}
          activeRepoId={repo?.id ?? null}
          page={page}
          onPage={setPage}
          onSelectRepo={setSelectedId}
          onConnect={connect}
          onLogout={onLogout}
          onCollapse={() => setOpen(false)}
        />
      </div>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-12 shrink-0 items-center gap-3 border-b border-border px-4">
          {!open && (
            <button
              onClick={() => setOpen(true)}
              aria-label="Open sidebar"
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <PanelLeftOpen className="h-[18px] w-[18px]" strokeWidth={1.5} />
            </button>
          )}
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="truncate">{repo?.full_name ?? 'No repository'}</span>
            <span>/</span>
            <span className="font-medium capitalize text-foreground">{page}</span>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          {repo ? (
            <Overview key={repo.id} repo={repo} />
          ) : (
            <p className="mx-auto mt-24 max-w-sm text-center text-sm text-muted-foreground">
              Connect a repository from the sidebar to get started.
            </p>
          )}
        </main>
      </div>
    </div>
  )
}

export default function App() {
  const [user, setUser] = useState<User | null | undefined>(undefined)

  useEffect(() => {
    api.me().then(setUser).catch(() => setUser(null))
  }, [])

  const logout = useCallback(async () => {
    await api.logout().catch(() => {})
    setUser(null)
  }, [])

  if (user === undefined) {
    return <div className="grid h-full place-items-center text-muted-foreground">Loading…</div>
  }
  return user ? <Workspace user={user} onLogout={logout} /> : <LoginScreen />
}