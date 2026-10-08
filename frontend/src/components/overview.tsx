import { useEffect, useState } from 'react'
import { api, type Repo } from '@/api'
import ContributionSkyline, { type ContributionDay } from '@/components/ui/contribution-skyline'

const BADGE: Record<Repo['status'], string> = {
  ready: 'border-success/40 text-success',
  indexing: 'border-warning/40 text-warning animate-pulse',
  pending: 'border-border text-muted-foreground',
  failed: 'border-danger/40 text-danger',
}

// Parent renders this with key={repo.id}, so state resets when the repo changes.
export default function Overview({ repo }: { repo: Repo }) {
  const [activity, setActivity] = useState<ContributionDay[] | null>(null)
  const [busy, setBusy] = useState(false)
  const [note, setNote] = useState<string | null>(null)

  useEffect(() => {
    if (repo.status !== 'ready') return
    let live = true
    api.activity(repo.id)
      .then((d) => { if (live) setActivity(d) })
      .catch(() => { if (live) setActivity([]) })
    return () => { live = false }
  }, [repo.id, repo.status])

  const buildIndex = async () => {
    setBusy(true)
    setNote('Building index. The first run downloads a model and can take a few minutes.')
    try {
      const r = await api.buildIndex(repo.id)
      setNote(`Indexed ${r.chunks} chunks from ${r.files_indexed} files.`)
    } catch (e) {
      setNote(e instanceof Error ? e.message : 'Indexing failed')
    } finally {
      setBusy(false)
    }
  }

  const [owner, name] = repo.full_name.split('/')
  const total = activity?.reduce((s, d) => s + d.count, 0) ?? 0
  const tiles: [string, number][] = [
    ['Files', repo.files],
    ['Source', repo.files_by_kind.source ?? 0],
    ['Tests', repo.files_by_kind.test ?? 0],
    ['Commits analysed', repo.commits],
  ]

  return (
    <div className="mx-auto w-full max-w-[980px] px-4 py-8 sm:px-8">
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <h1 className="text-xl">
          <span className="text-primary">{owner}</span>
          <span className="mx-1 text-muted-foreground">/</span>
          <span className="font-semibold">{name}</span>
        </h1>
        <span className={`rounded-full border px-2 py-0.5 text-xs font-medium ${BADGE[repo.status]}`}>
          {repo.status}
        </span>
        <span className="font-mono text-xs text-muted-foreground">{repo.default_branch}</span>
      </div>

      {repo.status === 'failed' && (
        <p className="rounded-md border border-danger/40 bg-danger/10 p-3 font-mono text-xs text-danger">
          {repo.error}
        </p>
      )}

      {(repo.status === 'pending' || repo.status === 'indexing') && (
        <p className="rounded-md border border-border bg-card p-6 text-sm text-muted-foreground">
          Downloading and analysing this repository. This page updates on its own.
        </p>
      )}

      {repo.status === 'ready' && (
        <>
          <dl className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            {tiles.map(([label, value]) => (
              <div key={label} className="rounded-md border border-border bg-card px-4 py-3">
                <dd className="text-xl font-semibold tabular-nums">{value}</dd>
                <dt className="text-xs text-muted-foreground">{label}</dt>
              </div>
            ))}
          </dl>

          {activity === null ? (
            <div className="h-[320px] animate-pulse rounded-xl border border-border bg-card" />
          ) : (
            <ContributionSkyline
              key={repo.id}
              data={activity}
              unit="file change"
              palette="github"
              title={
                <>
                  <span className="font-semibold tabular-nums">{total}</span> file changes across the last{' '}
                  {repo.commits} commits
                </>
              }
            />
          )}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button
              onClick={buildIndex}
              disabled={busy}
              className="rounded-md border border-border bg-muted px-3 py-1.5 text-sm font-medium transition-colors hover:border-muted-foreground disabled:opacity-50"
            >
              {busy ? 'Indexing…' : 'Build search index'}
            </button>
            {note && <span className="text-xs text-muted-foreground">{note}</span>}
          </div>
        </>
      )}
    </div>
  )
}