import { useCallback, useEffect, useState } from 'react'
import { PanelLeftOpen } from 'lucide-react'
import { api, ApiError, LOGIN_URL, type Repo, type User } from '@/api'
import AppSidebar, { type Page } from '@/components/app-sidebar'
import Overview from '@/components/overview'
import ImpactPage from '@/components/impact-page'
import GraphPage from '@/components/graph-page'
import AskPage from '@/components/ask-page'
import ContributionSkyline from '@/components/ui/contribution-skyline'
import ErrorPage, { ERRORS } from '@/components/error-page'

function GithubMark() {
  return (
    <svg viewBox="0 0 16 16" width="18" height="18" fill="currentColor" aria-hidden="true">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  )
}

const AUTH_MESSAGES: Record<string, string> = {
  denied: 'You declined the GitHub permission, so we could not sign you in. Authorize to continue.',
  expired: 'The sign-in attempt expired. Please try again.',
  failed: 'GitHub sign-in failed. Please try again.',
}

function LoginScreen() {
  // Read once, then clean the URL so a refresh doesn't show the message again
  const [message] = useState(() => {
    const code = new URLSearchParams(window.location.search).get('auth_error')
    return code ? AUTH_MESSAGES[code] ?? AUTH_MESSAGES.failed : null
  })
  useEffect(() => {
    if (window.location.search) window.history.replaceState({}, '', window.location.pathname)
  }, [])

  return (
    <main className="grid h-full overflow-hidden lg:grid-cols-[1.2fr_1fr]">
      {/* Left: brand + skyline */}
      <section
        className="relative hidden h-full flex-col gap-6 overflow-hidden border-r border-border p-8 lg:flex"
        style={{
          background:
            'radial-gradient(ellipse 70% 50% at 50% 55%, rgba(46,160,67,0.16), transparent 70%), #010409',
        }}
      >
        <div className="flex items-center gap-2">
          <div className="grid h-8 w-8 place-items-center rounded-md border border-border bg-muted font-mono text-xs font-semibold">
            CA
          </div>
          <span className="text-sm font-semibold">CodeAtlas</span>
        </div>

        <div className="flex min-h-0 flex-1 items-center">
          <div className="w-full">
            <ContributionSkyline
              seed={11}
              heightScale={1.6}
              footer="Sample data. Sign in to see your own repositories."
              className="bg-transparent"
            />
          </div>
        </div>

        <div>
          <h2 className="text-2xl font-semibold leading-tight tracking-tight">
            Know what breaks before you change it.
          </h2>
          <p className="mt-2 max-w-md text-sm text-muted-foreground">
            Dependency graph, affected tests and routes, and a risk score for any change,
            with the evidence behind every claim.
          </p>
        </div>
      </section>

      {/* Right: sign in */}
      <section className="flex h-full items-center justify-center overflow-y-auto px-6 py-8">
        <div className="w-full max-w-sm">
          <div className="mb-6 flex items-center gap-2 lg:hidden">
            <div className="grid h-8 w-8 place-items-center rounded-md border border-border bg-muted font-mono text-xs font-semibold">
              CA
            </div>
            <span className="text-sm font-semibold">CodeAtlas</span>
          </div>

          <h1 className="text-2xl font-semibold">Welcome to CodeAtlas</h1>
          <p className="mb-6 mt-1 text-sm text-muted-foreground">
            Sign in with GitHub to analyse your repositories.
          </p>

          {message && (
            <p className="mb-4 rounded-md border border-warning/40 bg-warning/10 px-3 py-2 text-xs text-warning">
              {message}
            </p>
          )}

          <a
            href={LOGIN_URL}
            className="flex w-full items-center justify-center gap-2.5 rounded-lg border border-white/10 bg-[#238636] py-2.5 text-sm font-medium text-white transition-colors hover:bg-[#2ea043]"
          >
            <GithubMark />
            Continue with GitHub
          </a>

          <ul className="mt-6 space-y-2 text-xs text-muted-foreground">
            <li>• Reads your public repositories and their commit history</li>
            <li>• Never writes to your code or changes anything on GitHub</li>
            <li>• You can revoke access any time in GitHub settings</li>
          </ul>
        </div>
      </section>
    </main>
  )
}

function Workspace({ user, onLogout }: { user: User; onLogout: () => void }) {
  const [repos, setRepos] = useState<Repo[]>([])
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [page, setPage] = useState<Page>('overview')
  const [open, setOpen] = useState(true)
  const [fatal, setFatal] = useState<{ code: number; detail?: string } | null>(null)

  const load = useCallback(async () => {
    try {
      setRepos(await api.repos())
      setFatal(null)
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onLogout()
      else if (e instanceof ApiError && e.status >= 500) setFatal({ code: e.status, detail: e.message })
      else if (!(e instanceof ApiError)) setFatal({ code: 503 })
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

  if (fatal) {
    return <ErrorPage code={fatal.code} detail={fatal.detail} onRetry={() => { setFatal(null); load() }} />
  }

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
          {!repo ? (
            <p className="mx-auto mt-24 max-w-sm text-center text-sm text-muted-foreground">
              Connect a repository from the sidebar to get started.
            </p>
          ) : repo.status === 'ready' && page === 'impact' ? (
            <ImpactPage key={repo.id} repo={repo} />
          ) : repo.status === 'ready' && page === 'graph' ? (
            <GraphPage key={repo.id} repo={repo} />
          ) : repo.status === 'ready' && page === 'ask' ? (
            <AskPage key={repo.id} repo={repo} />
          ) : (
            <Overview key={repo.id} repo={repo} />
          )}
        </main>
      </div>
    </div>
  )
}

function AuthGate() {
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

export default function App() {
  const path = window.location.pathname.replace(/\/+$/, '') || '/'
  const preview = /^\/error\/(\d{3})$/.exec(path) // /error/422 etc. to preview a page
  if (preview && ERRORS[Number(preview[1])]) return <ErrorPage code={Number(preview[1])} />
  if (path !== '/') return <ErrorPage code={404} />
  return <AuthGate />
}