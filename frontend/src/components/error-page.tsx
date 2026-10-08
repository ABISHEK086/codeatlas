import { ArrowLeft } from 'lucide-react'

export const ERRORS: Record<number, { title: string; text: string }> = {
  401: { title: 'Sign in required', text: 'Your session expired, or you are not signed in yet.' },
  403: { title: 'Access denied', text: 'Your GitHub account does not have access to this resource.' },
  404: { title: 'Page not found', text: 'This page does not exist, or it has moved. Check the URL, or head back to your workspace.' },
  422: { title: 'Invalid request', text: 'The server understood the request, but the data in it was not valid. Check what you entered and try again.' },
  500: { title: 'Something broke on our side', text: 'An unexpected error occurred. It is not you. Try again in a moment.' },
  503: { title: 'Cannot reach the server', text: 'The CodeAtlas API is not responding. Make sure the backend is running, then retry.' },
}

type Props = { code: number; detail?: string; onRetry?: () => void }

export default function ErrorPage({ code, detail, onRetry }: Props) {
  const info = ERRORS[code] ?? ERRORS[500]
  const btn =
    'inline-flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors'

  return (
    <main className="relative grid h-full place-items-center overflow-hidden px-6 text-center">
      <span
        aria-hidden="true"
        className="pointer-events-none absolute select-none text-[length:min(55vw,30rem)] font-bold leading-none text-foreground/[0.04]"
      >
        {code}
      </span>

      <div className="relative max-w-md">
        <h1 className="text-4xl font-semibold tracking-tight sm:text-5xl">{info.title}</h1>
        <p className="mt-3 text-sm text-muted-foreground">{info.text}</p>

        {detail && (
          <p className="mt-4 break-words rounded-md border border-border bg-card px-3 py-2 font-mono text-xs text-muted-foreground">
            {detail}
          </p>
        )}

        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <button
            onClick={() => window.history.back()}
            className={`${btn} border border-border bg-muted text-foreground hover:border-muted-foreground`}
          >
            <ArrowLeft className="h-4 w-4" strokeWidth={1.5} />
            Go back
          </button>
          {onRetry && (
            <button
              onClick={onRetry}
              className={`${btn} border border-border bg-muted text-foreground hover:border-muted-foreground`}
            >
              Try again
            </button>
          )}
          <button
            onClick={() => window.location.assign('/')}
            className={`${btn} bg-foreground text-background hover:opacity-90`}
          >
            {code === 401 ? 'Sign in' : 'Take me home'}
          </button>
        </div>
      </div>
    </main>
  )
}