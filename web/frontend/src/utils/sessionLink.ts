/** Builds a deep link to the Activity/Events page that auto-opens a given session's detail drawer. */
export function buildEventsLink(engine: string, sessionId: string, projectPath: string): string {
  const params = new URLSearchParams({ session: sessionId, engine, project: projectPath });
  return `/activity/events?${params.toString()}`;
}
