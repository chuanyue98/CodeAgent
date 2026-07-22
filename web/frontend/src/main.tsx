import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import './index.css'
import App from './App.tsx'
import { ProjectProvider } from './context/ProjectContext.tsx'

// Each route now owns its own ErrorBoundary + Suspense pair (see App.tsx),
// so a render error in one lazy-loaded page no longer blanks the entire
// app (nav/sidebar/other pages stay usable). No app-wide boundary here.
createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <ProjectProvider>
        <App />
      </ProjectProvider>
    </BrowserRouter>
  </StrictMode>,
)
