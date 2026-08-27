/**
 * Deep links that auto-open one session's detail view.
 *
 * One parameter shape is shared by every surface that links into a session
 * (Sessions page inline panel, Timeline drawer, Home's recent list, the
 * Agent sidebar): `session` = id, plus namespaced `sessionEngine`/
 * `sessionProject` hints. The hints are namespaced because they identify one
 * row to open, which is a different thing from the `engines`/`project`
 * params that describe how a list is filtered.
 */
function buildSessionParams(engine: string, sessionId: string, projectPath: string): string {
  const params = new URLSearchParams({
    session: sessionId,
    sessionEngine: engine,
    sessionProject: projectPath,
  });
  return `?${params.toString()}`;
}

/** Opens the session's detail panel on the Sessions page (the object view). */
export function buildSessionLink(engine: string, sessionId: string, projectPath: string): string {
  return `/activity/sessions${buildSessionParams(engine, sessionId, projectPath)}`;
}


/**
 * Opens the session in a terminal tab, handed back to its own engine CLI.
 *
 * The counterpart to buildSessionLink: that one goes to the object view --
 * what this session is, what it cost, convert it, delete it. This one is the
 * verb. Home's "continue where you left off" used to point at the object
 * view, which is a reasonable place to arrive but not what the label said,
 * and left two more clicks between the user and the conversation.
 */
export function buildResumeLink(engine: string, sessionId: string, projectPath: string): string {
  const params = new URLSearchParams({
    engine,
    cwd: projectPath,
    session: sessionId,
  });
  return `/agent/terminal?${params.toString()}`;
}
