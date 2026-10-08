import { useEffect, useState, type FormEvent } from 'react'
import { api, type AskResult, type Evidence, type FileItem, type Repo } from '@/api'

const LEVEL_COLOR = { low: '#3fb950', medium: '#d29922', high: '#db6d28', critical: '#f85149' }

const SUGGESTIONS = [
  'What could break if I change this file, and what should I check first?',
  'Which tests should I run before merging a change here?',
  'How does authentication work in this project?',
]

function EvidenceItem({ ev }: { ev: Evidence }) {
  const lines = ev.start_line ? `:${ev.start_line}${ev.end_line && ev.end_line !== ev.start_line ? `-${ev.end_line}` : ''}` : ''
  return (
    <li className="rounded border border-border bg-background">
      <div className="flex items-center gap-2 px-2.5 py-1.5">
        <span
          className={`grid h-4 w-4 shrink-0 place-items-center rounded-full text-[10px] font-bold text-white ${ev.verified ? 'bg-success' : 'bg-danger'}`}
          title={ev.verified ? 'Verified: file and lines exist' : 'Unverified: not found in the repository'}
        >
          {ev.verified ? '✓' : '!'}
        </span>
        <span className="truncate font-mono text-xs">{ev.path}{lines}</span>
      </div>
      {ev.note && <p className="px-2.5 pb-1.5 text-xs text-muted-foreground">{ev.note}</p>}
      {ev.snippet && (
        <pre className="overflow-x-auto border-t border-border px-2.5 py-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
          {ev.snippet}
        </pre>
      )}
    </li>
  )
}

function Result({ r }: { r: AskResult }) {
  const { answer, grounding } = r
  return (
    <div className="mt-6 space-y-4">
      <section className="rounded-md border border-border bg-card p-5">
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          {r.risk && (
            <span
              className="rounded-full border px-2 py-0.5 font-medium"
              style={{ borderColor: LEVEL_COLOR[r.risk.level], color: LEVEL_COLOR[r.risk.level] }}
            >
              risk {r.risk.score} · {r.risk.level}
            </span>
          )}
          <span className="rounded-full border border-border px-2 py-0.5 text-muted-foreground">
            confidence: {answer.confidence}
          </span>
          <span className="rounded-full border border-border px-2 py-0.5 text-muted-foreground">
            {grounding.evidence_verified}/{grounding.evidence_total} citations verified
          </span>
        </div>
        <p className="text-sm leading-relaxed">{answer.summary}</p>
      </section>

      {answer.findings.map((f, i) => (
        <section key={i} className="rounded-md border border-border bg-card p-4">
          <p className="mb-2 text-sm font-medium">{f.claim}</p>
          <ul className="space-y-1.5">
            {f.evidence.map((ev, j) => <EvidenceItem key={j} ev={ev} />)}
          </ul>
        </section>
      ))}

      <div className="grid gap-4 md:grid-cols-2">
        {answer.tests_to_run.length > 0 && (
          <section className="rounded-md border border-border bg-card p-4">
            <h3 className="mb-2 text-sm font-semibold">Tests to run</h3>
            <ul className="space-y-1">
              {answer.tests_to_run.map((t) => <li key={t} className="truncate font-mono text-xs text-success">{t}</li>)}
            </ul>
          </section>
        )}
        {answer.checklist.length > 0 && (
          <section className="rounded-md border border-border bg-card p-4">
            <h3 className="mb-2 text-sm font-semibold">Safe-change checklist</h3>
            <ul className="space-y-1.5 text-sm">
              {answer.checklist.map((c) => (
                <li key={c} className="flex gap-2"><span className="text-muted-foreground">☐</span>{c}</li>
              ))}
            </ul>
          </section>
        )}
      </div>

      <section className="rounded-md border border-border bg-card p-4">
        <h3 className="mb-2 text-sm font-semibold">How it got here</h3>
        <div className="flex flex-wrap gap-1.5">
          {r.trace.map((t, i) => (
            <span key={i} className="rounded border border-border bg-background px-2 py-0.5 font-mono text-[11px] text-muted-foreground">
              {t.tool}({Object.values(t.args).map((v) => JSON.stringify(v)).join(', ')})
            </span>
          ))}
          {r.trace.length === 0 && <span className="text-xs text-muted-foreground">No tools were called.</span>}
        </div>
        <p className="mt-2 text-[11px] text-muted-foreground">
          The risk score is computed by code. The model only explains it. Model: {r.model}
        </p>
      </section>
    </div>
  )
}

export default function AskPage({ repo }: { repo: Repo }) {
  const [files, setFiles] = useState<FileItem[]>([])
  const [question, setQuestion] = useState('')
  const [filePath, setFilePath] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<AskResult | null>(null)

  useEffect(() => {
    let live = true
    api.files(repo.id).then((f) => { if (live) setFiles(f) }).catch(() => {})
    return () => { live = false }
  }, [repo.id])

  const submit = async (e: FormEvent) => {
    e.preventDefault()
    if (question.trim().length < 3 || busy) return
    setBusy(true)
    setError(null)
    try {
      setResult(await api.ask(repo.id, question.trim(), filePath.trim() || undefined))
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-[860px] px-4 py-8 sm:px-8">
      <h1 className="mb-1 text-xl font-semibold">Ask CodeAtlas</h1>
      <p className="mb-5 text-sm text-muted-foreground">
        Answers are built from tool results, and every citation is checked against the repository.
        For semantic search, build the search index on the Overview page first.
      </p>

      <form onSubmit={submit} className="space-y-3">
        <input
          list="repo-files"
          value={filePath}
          onChange={(e) => setFilePath(e.target.value)}
          placeholder="File you plan to change (optional), e.g. backend/app/models.py"
          className="w-full rounded-md border border-border bg-card px-3 py-2 font-mono text-xs outline-none placeholder:text-muted-foreground/60 focus:border-primary focus:ring-1 focus:ring-primary"
        />
        <datalist id="repo-files">
          {files.filter((f) => f.kind === 'source' || f.kind === 'test').map((f) => <option key={f.id} value={f.path} />)}
        </datalist>

        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          rows={3}
          placeholder="Ask about a change, a file, or how something works…"
          className="w-full resize-none rounded-md border border-border bg-card px-3 py-2 text-sm outline-none placeholder:text-muted-foreground/60 focus:border-primary focus:ring-1 focus:ring-primary"
        />

        <div className="flex flex-wrap items-center gap-2">
          <button
            disabled={busy || question.trim().length < 3}
            className="rounded-md border border-white/10 bg-[#238636] px-4 py-1.5 text-sm font-medium text-white transition-colors hover:bg-[#2ea043] disabled:opacity-50"
          >
            {busy ? 'Investigating…' : 'Ask'}
          </button>
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => setQuestion(s)}
              className="max-w-[260px] truncate rounded-full border border-border px-3 py-1 text-xs text-muted-foreground transition-colors hover:border-muted-foreground hover:text-foreground"
            >
              {s}
            </button>
          ))}
        </div>
      </form>

      {busy && <p className="mt-4 animate-pulse text-sm text-muted-foreground">The agent is calling tools. This can take 10 to 30 seconds.</p>}
      {error && <p className="mt-4 rounded-md border border-danger/40 bg-danger/10 p-3 text-sm text-danger">{error}</p>}
      {result && !busy && <Result r={result} />}
    </div>
  )
}