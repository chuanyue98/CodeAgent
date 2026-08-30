import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import { QueryClientProvider } from '@tanstack/react-query'
import './index.css'
import App from './App.tsx'
import { ProjectProvider } from './context/ProjectContext.tsx'
import { SystemMetricsProvider } from './context/SystemMetricsContext.tsx'
import { LanguageProvider } from './i18n/LanguageProvider.tsx'
import LanguageSync from './i18n/LanguageSync.tsx'
import ErrorBoundary from './components/shared/ErrorBoundary.tsx'
import { bootstrapToken } from './utils/token.ts'
import { queryClient } from './utils/queryClient.ts'

// Must run before the first API call: lifts ?ca_token=... out of the URL
// the launcher opened and into sessionStorage. See utils/token.ts.
bootstrapToken()

// App-wide boundary: each route already owns its own ErrorBoundary +
// Suspense pair (see App.tsx), which isolates lazy-loaded page errors.
// This outer boundary is the last-resort guard for the shell itself
// (nav, header, ProjectProvider) so a render error there shows a
// recoverable error page instead of a blank white screen.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ErrorBoundary>
          <ProjectProvider>
            <LanguageProvider>
              {/* Reconciles the painted language with config.json's `language`
                  once it loads -- the provider's first guess comes from the
                  cache/browser so there is no flash of the wrong language. */}
              <LanguageSync />
              <SystemMetricsProvider>
                <App />
              </SystemMetricsProvider>
            </LanguageProvider>
          </ProjectProvider>
        </ErrorBoundary>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
)
