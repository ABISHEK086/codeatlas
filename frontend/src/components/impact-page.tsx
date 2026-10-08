import { useEffect, useMemo, useState } from 'react'
import { Search } from 'lucide-react'
import { api, type FileItem, type Impact, type PathRow, type Repo } from '@/api'

const LEVEL_COLOR: Record<Impact['risk']['level'], string> = {
  low: '#3fb950',
  medium: '#d29922',
  high: '#db6d28',
  critical: '#f85149',
}

function RiskGauge({ score, level }: { score: number; level: Impact['risk']['level'] }) {
  const [shown, setShown] = useState(0)

  useEffect(() => {
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / 900)
      setShown(Math.round(score * (1 - Math.pow(1 - t, 3))))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [score])

  const r = 60
  const c = 2 * Math.PI * r
  const color = LEVEL_COLOR[level]
  return (
    <div className="relative h-[150px] w-[150px] shrink-0">
      <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--color-muted)" strokeWidth="10" />
        <circle
          cx="70" cy="70" r={r} fill="none" stroke={color} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={c} strokeDashoffset={c * (1 - shown / 100)}
        />
      </svg>
      <div className="absolute inset-0 grid place-items-center text-center">
        <div>
          <div className="text-4xl font-semibold tabular-nums">{shown}</div>
          <div className="text-xs font-medium uppercase tracking-wider" style={{ color }}>{level}</div>
        </div>
      </div>
    </div>
  )
}

function Card({ title, count, children }: { title: string; count?: number; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-border bg-card">
      <h3 className="flex items-center justify-between border-b border-border px-4 py-2.5 text-sm font-semibold">
        {title}
        {count !== undefined && (
          <span className="rounded-full bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground">{count}</span>
        )}
      </h3>
      <div className="p-2">{children}</div>
    </section>
  )
}

const Empty = ({ text }: { text: string }) => (
  <p className="px-2 py-3 text-xs text-muted-foreground">{text}</p>
)

function PathList({ rows, onOpen, empty }: { rows: PathRow[]; onOpen: (p: string) => void; empty: string }) {
  if (!rows.length) return <Empty text={empty} />
  return (
    <ul className="max-h-60 overflow-y-auto">
      {rows.map((r) => (
        <li key={r.path}>
          <button
            onClick={() => onOpen(r.path)}
            className="flex w-full items-center justify-between gap-3 rounded px-2 py-1.5 text-left hover:bg-muted"
          >
            <span className="truncate font-mono text-xs text-primary">{r.path}</span>
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground">
              {r.distance > 1 ? `via ${r.distance} hops` : 'direct'}
            </span>
          </button>
        </li>
      ))}
    </ul>
  )
}

function FilePicker({ files, value, onPick }: { files: FileItem[]; value: string | null; onPick: (p: string) => void }) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)

  const matches = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return files
      .filter((f) => (f.kind === 'source' || f.kind === 'test') && f.path.toLowerCase().includes(needle))
      .slice(0, 40)
  }, [files, q])

  return (
    <div className="relative">
      <div className="flex items-center gap-2 rounded-md border border-border bg-card px-3 py-2 focus-within:border-primary focus-within:ring-1 focus-within:ring-primary">
        <Search className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
        <input
          value={open ? q : value ?? ''}
          onFocus={() => { setQ(''); setOpen(true) }}
          onBlur={() => setTimeout(() => setOpen(false), 120)}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search for a file to analyse, e.g. models.py"
          className="w-full bg-transparent font-mono text-sm outline-none placeholder:text-muted-foreground/60"
        />
      </div>
      {open && (
        <ul className="absolute z-30 mt-1 max-h-72 w-full overflow-y-auto rounded-md border border-border bg-card py-1 shadow-xl">
          {matches.length === 0 && <li className="px-3 py-2 text-xs text-muted-foreground">No matching files</li>}
          {matches.map((f) => (
            <li key={f.id}>
              <button
                onMouseDown={() => { onPick(f.path); setOpen(false) }}
                className="flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left hover:bg-muted"
              >
                <span className="truncate font-mono text-xs">{f.path}</span>
                <span className="shrink-0 text-[10px] text-muted-foreground">{f.kind}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function ImpactPage({ repo }: { repo: Repo }) {
  const [files, setFiles] = useState<FileItem[]>([])
  const [path, setPath] = useState<string | null>(null)
  const [result, setResult] = useState<{ path: string; data: Impact } | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let live = true
    api.files(repo.id).then((f) => { if (live) setFiles(f) }).catch(() => {})
    return () => { live = false }
  }, [repo.id])

  useEffect(() => {
    if (!path) return
    let live = true
    api.impact(repo.id, path)
      .then((data) => { if (live) { setResult({ path, data }); setError(null) } })
      .catch((e) => { if (live) setError(e instanceof Error ? e.message : 'Analysis failed') })
    return () => { live = false }
  }, [repo.id, path])

  const loading = path !== null && result?.path !== path && !error
  const d = result && result.path === path ? result.data : null

  return (
    <div className="mx-auto w-full max-w-[980px] px-4 py-8 sm:px-8">
      <h1 className="mb-1 text-xl font-semibold">Impact analysis</h1>
      <p className="mb-5 text-sm text-muted-foreground">
        Pick a file to see what could break if you change it. Click any file below to follow the chain.
      </p>

      <FilePicker files={files} value={path} onPick={(p) => { setError(null); setPath(p) }} />
      {error && <p className="mt-3 text-sm text-danger">{error}</p>}
      {!path && (
        <p className="mt-10 text-center text-sm text-muted-foreground">
          Try a core file such as <span className="font-mono">models.py</span> or <span className="font-mono">deps.py</span>.
        </p>
      )}
      {loading && <div className="mt-6 h-48 animate-pulse rounded-md border border-border bg-card" />}

      {d && (
        <div className="mt-6 space-y-4">
          <section className="flex flex-col gap-6 rounded-md border border-border bg-card p-5 sm:flex-row sm:items-center">
            <RiskGauge key={d.file} score={d.risk.score} level={d.risk.level} />
            <div className="min-w-0 flex-1">
              <p className="truncate font-mono text-sm">{d.file}</p>
              <p className="mb-3 text-xs text-muted-foreground">
                Score computed by rules from the code graph and {d.history_commits_analysed} commits of history
              </p>
              {d.risk.factors.length === 0 ? (
                <p className="text-sm text-muted-foreground">No risk factors found. Nothing depends on this file.</p>
              ) : (
                <ul className="space-y-2">
                  {d.risk.factors.map((f) => (
                    <li key={f.factor} className="text-sm">
                      <div className="flex items-center justify-between">
                        <span className="font-medium">{f.factor}</span>
                        <span className="font-mono text-xs text-muted-foreground">+{f.points}</span>
                      </div>
                      <div className="mt-1 h-1 rounded-full bg-muted">
                        <div
                          className="h-1 rounded-full"
                          style={{ width: `${Math.min(100, f.points * 2.5)}%`, background: LEVEL_COLOR[d.risk.level] }}
                        />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{f.evidence}</p>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            <Card title="Direct dependents" count={d.direct_dependents.length}>
              <PathList rows={d.direct_dependents} onOpen={setPath} empty="No file imports this one." />
            </Card>
            <Card title="Indirect dependents" count={d.indirect_dependents.length}>
              <PathList rows={d.indirect_dependents} onOpen={setPath} empty="No indirect dependents." />
            </Card>
            <Card title="Affected tests" count={d.affected_tests.length}>
              <PathList rows={d.affected_tests} onOpen={setPath} empty="No test reaches this file. Changes here are unprotected." />
            </Card>
            <Card title="Depends on" count={d.depends_on.length}>
              <PathList rows={d.depends_on} onOpen={setPath} empty="This file imports nothing from the repo." />
            </Card>
            <Card title="Affected API routes" count={d.affected_routes.length}>
              {d.affected_routes.length === 0 ? (
                <Empty text="No API routes are downstream of this file." />
              ) : (
                <ul className="max-h-60 overflow-y-auto">
                  {d.affected_routes.map((r) => (
                    <li key={`${r.path}:${r.line}`} className="px-2 py-1.5">
                      <span className="font-mono text-xs">{r.route}</span>
                      <span className="block truncate font-mono text-[10px] text-muted-foreground">
                        {r.path}:{r.line}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
            <Card title="Changes together (Git history)" count={d.co_change.length}>
              {d.co_change.length === 0 ? (
                <Empty text="Not enough history for this file." />
              ) : (
                <ul className="max-h-60 overflow-y-auto">
                  {d.co_change.map((c) => (
                    <li key={c.path}>
                      <button
                        onClick={() => setPath(c.path)}
                        className="flex w-full items-center justify-between gap-3 rounded px-2 py-1.5 text-left hover:bg-muted"
                      >
                        <span className="truncate font-mono text-xs text-primary">{c.path}</span>
                        <span className="flex shrink-0 items-center gap-2 font-mono text-[10px] text-muted-foreground">
                          {c.hidden_coupling && (
                            <span className="rounded-full border border-warning/40 px-1.5 text-warning">hidden</span>
                          )}
                          {c.times_together}× · {Math.round(c.confidence * 100)}%
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <Card title="Recent commits touching this file" count={d.recent_commits.length}>
            {d.recent_commits.length === 0 ? (
              <Empty text="No commits in the analysed history." />
            ) : (
              <ul>
                {d.recent_commits.map((c) => (
                  <li key={c.sha} className="flex items-baseline gap-3 px-2 py-1.5 text-sm">
                    <span className="font-mono text-xs text-primary">{c.sha}</span>
                    <span className="min-w-0 flex-1 truncate">{c.message}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">{c.author}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      )}
    </div>
  )
}