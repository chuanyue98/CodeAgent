# Web UI/UX Optimization Design Spec

* **Date**: 2026-07-14
* **Author**: Antigravity
* **Status**: Proposed

This specification details the complete implementation plan for optimizing the CodeAgent web experience (both frontend and backend).

---

## 1. Objectives & Scope

Improve the usability, performance, and robustness of the CodeAgent web platform by implementing the following features:

### Frontend (React SPA)
1. **Markdown Chat Bubbles**: Render AI responses in `ChatPage.tsx` using `ReactMarkdown` with a clean `prose prose-slate` styling.
2. **Copy Code Action**: Add a floating "Copy" button to the top-right of code blocks rendered in Markdown.
3. **Workspace Selector**: Add a Project selection dropdown in the chat sidebar when starting a new session, allowing the user to select which workspace directory the chat engine should operate in.
4. **Auto-Sizing Input Textarea**: Replace the fixed height textarea with an auto-resizing one that expands dynamically up to a maximum height.
5. **Session Deletion UI**: Add a trash icon next to session entries in the sidebar to delete them.
6. **Unsaved Warnings in ConfigHub**: Warn users if they attempt to navigate away with unsaved changes in `ConfigHub.tsx`.
7. **Premium Empty States**: Replace generic "no items" text with clean visual cards for empty states in various panels.

### Backend (FastAPI)
1. **Delete Session Endpoint**: Expose `DELETE /api/history/{engine}/{session_id}` to delete the session log file from the local storage.
2. **Graceful Subprocess Cleanup**: Kill any orphaned background processes spawned by `TaskRunner` on server shutdown.

---

## 2. Technical Details & Architecture

### Backend: Delete Session Endpoint
Add a route `DELETE /api/history/{engine}/{session_id}` in `core/web/routers/history.py`.
* **Logic**: Locate the target session file in the engine's log directory and remove it from the filesystem.
* **Response**: Returns `{"status": "deleted", "session_id": session_id}`.

### Backend: Graceful Subprocess Cleanup
In `core/web/server.py` lifespan manager, call a new `cleanup()` or `kill_all()` method on `_runner` and `_task_runner` upon FastAPI application shutdown.
* **Logic**: Retrieve all running processes in the `TaskRunner` dict and send them `SIGTERM`/`SIGKILL` signals (or call `terminate()` / `kill()` on Python `subprocess.Popen`).

### Frontend: Markdown & Code Copy
In `ChatPage.tsx`, import `ReactMarkdown`. Define a custom renderer for `code` and `pre` tags.
* The `pre` tag custom renderer will contain a relative container with a button in the top-right corner.
* When clicked, the button copies `children` text to the clipboard and changes state to "Copied!" for 2 seconds.

### Frontend: Project Selector in Chat
In the `ChatPage.tsx` sidebar, display a Project Workspace selection dropdown next to "New Session".
* Load the projects list from `useProject()` (`projects`).
* Set `activeProjectPath` state to the chosen project directory.
* When starting a turn, pass this `activeProjectPath` to `startChatTurn`.

### Frontend: Auto-Sizing Input
Use a custom auto-sizing textarea logic (using React `useRef` to set `element.style.height = 'auto'` then `element.scrollHeight`) to dynamically expand the input textarea.

### Frontend: Unsaved Config Warning
In `ConfigHub.tsx`, track `isDirty` state comparing `localConfig` / `localProjects` / `localProxies` against original `config` / `projects` / `proxy`.
* Hook into window `beforeunload` event to warn if navigating away or closing tab.

---

## 3. Review & Approval

Please review this specification. Once approved, we will proceed to write the detailed implementation plan.
