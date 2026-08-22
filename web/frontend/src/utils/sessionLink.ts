/**
 * Builds a deep link to the Activity/Events page that auto-opens a given
 * session's detail drawer.
 *
 * The params are namespaced (`sessionEngine`/`sessionProject`) because they
 * identify one row to open, which is a different thing from the `engines` and
 * `project` params that describe how the list is filtered. Events still reads
 * the old unprefixed names so existing links keep working.
 */
export function buildTimelineLink(engine: string, sessionId: string, projectPath: string): string {
  const params = new URLSearchParams({
    session: sessionId,
    sessionEngine: engine,
    sessionProject: projectPath,
  });
  return `/activity/timeline?${params.toString()}`;
}
