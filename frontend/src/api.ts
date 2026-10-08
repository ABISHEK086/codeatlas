export type User = { id: number; login: string; avatar_url: string | null }

export type Repo = {
  id: number
  full_name: string
  default_branch: string
  status: 'pending' | 'indexing' | 'ready' | 'failed'
  error: string | null
  files: number
  files_by_kind: Record<string, number>
  commits: number
}

export type FileItem = { id: number; path: string; language: string | null; kind: string }
export type PathRow = { path: string; kind: string; distance: number }
export type Impact = {
  file: string
  language: string | null
  kind: string
  risk: {
    score: number
    level: 'low' | 'medium' | 'high' | 'critical'
    factors: { factor: string; points: number; evidence: string }[]
  }
  direct_dependents: PathRow[]
  indirect_dependents: PathRow[]
  affected_tests: PathRow[]
  affected_routes: { route: string; path: string; line: number }[]
  depends_on: PathRow[]
  co_change: { path: string; times_together: number; confidence: number; hidden_coupling: boolean }[]
  recent_commits: { sha: string; message: string; author: string | null; date: string | null }[]
  history_commits_analysed: number
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function req<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init.headers ?? {}) },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = typeof body.detail === 'string' ? body.detail : res.statusText
    throw new ApiError(res.status, detail)
  }
  return res.json() as Promise<T>
}

export const api = {
  me: () => req<User>('/auth/me'),
  logout: () => req<{ ok: boolean }>('/auth/logout', { method: 'POST' }),
  repos: () => req<Repo[]>('/repos'),
  connect: (full_name: string) =>
    req<Repo>('/repos', { method: 'POST', body: JSON.stringify({ full_name }) }),
  buildIndex: (id: number) =>
    req<{ files_indexed: number; chunks: number }>(`/repos/${id}/index`, { method: 'POST' }),
  activity: (id: number) =>
    req<{ date: string; count: number }[]>(`/repos/${id}/activity`),
  files: (id: number) => req<FileItem[]>(`/repos/${id}/files`),
  impact: (id: number, path: string) =>
    req<Impact>(`/repos/${id}/impact?path=${encodeURIComponent(path)}`),
}

// Login must be a full-page redirect to the backend (GitHub OAuth)
export const LOGIN_URL = 'http://localhost:8000/auth/github/login'