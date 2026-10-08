import { Component, type ErrorInfo, type ReactNode } from 'react'
import ErrorPage from '@/components/error-page'

export default class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null }

  static getDerivedStateFromError(error: Error) {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error(error, info.componentStack)
  }

  render() {
    if (this.state.error) {
      return <ErrorPage code={500} detail={this.state.error.message} onRetry={() => window.location.reload()} />
    }
    return this.props.children
  }
}