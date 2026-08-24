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

