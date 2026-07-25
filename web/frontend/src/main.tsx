import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'
import './index.css'
import App from './App.tsx'
import { ProjectProvider } from './context/ProjectContext.tsx'
import ErrorBoundary from './components/shared/ErrorBoundary.tsx'

// App-wide boundary: each route already owns its own ErrorBoundary +
// Suspense pair (see App.tsx), which isolates lazy-loaded page errors.
// This outer boundary is the last-resort guard for the shell itself
// (nav, header, ProjectProvider) so a render error there shows a
// recoverable error page instead of a blank white screen.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ErrorBoundary>
        <ProjectProvider>
          <App />
        </ProjectProvider>
      </ErrorBoundary>
    </BrowserRouter>
  </StrictMode>,
)
