import React, { Component, type ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  /**
   * Bumped on every "Try Again" click and used as the children wrapper's
   * `key`. Swapping the fallback UI back out for `children` *usually*
   * already forces a fresh mount (React reconciles by type, and the
   * fallback's element type differs from whatever `children` renders) --
   * but that's an implementation-detail coincidence, not a guarantee. The
   * key makes "Try Again" *always* remount the subtree (re-running effects,
   * re-fetching data) regardless of what the fallback or children happen to
   * render, so a transient failure (stale data, a dropped request) gets a
   * genuine second attempt instead of silently re-showing the same crash.
   */
  retryCount: number;
}

/**
 * Global error boundary to prevent white-screen crashes.
 * Catches unhandled exceptions in child component trees.
 */
class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, retryCount: 0 };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo): void {
    console.error('ErrorBoundary caught:', error, errorInfo);
  }

  handleReload = (): void => {
    this.setState(prev => ({
      hasError: false,
      error: null,
      retryCount: prev.retryCount + 1,
    }));
  };

  render(): ReactNode {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center min-h-screen gap-6 p-8">
          <div className="flex flex-col items-center gap-3 text-center">
            <AlertCircle className="w-12 h-12 text-red-400" />
            <h2 className="text-xl font-semibold text-slate-900">出错了</h2>
            <p className="text-sm text-slate-500 max-w-md">
              {this.state.error?.message || '发生意外错误，请尝试重新加载。'}
            </p>
          </div>
          <div className="flex gap-3">
            <button
              onClick={this.handleReload}
              className="flex items-center gap-2 px-4 py-2 bg-primary text-white rounded-xl hover:bg-primary/90 transition-colors text-sm font-medium"
            >
              <RefreshCw className="w-4 h-4" />
              重试
            </button>
            <button
              onClick={() => window.location.reload()}
              className="px-4 py-2 border border-slate-200 text-slate-600 rounded-xl hover:bg-slate-50 transition-colors text-sm font-medium"
            >
              重新加载页面
            </button>
          </div>
        </div>
      );
    }

    return <React.Fragment key={this.state.retryCount}>{this.props.children}</React.Fragment>;
  }
}

export default ErrorBoundary;
