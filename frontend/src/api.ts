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
}

// Login must be a full-page redirect to the backend (GitHub OAuth)
export const LOGIN_URL = 'http://localhost:8000/auth/github/login'