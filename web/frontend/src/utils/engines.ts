/**
 * The provider engines the app knows about, mirroring `ENGINES` in
 * core/constants.py. Kept in one place so the filter sidebar, the
 * convert-to-engine actions and the session detail panel can't drift apart.
 */
export const ENGINE_LABELS: Record<string, string> = {
  claude: 'Claude',
  opencode: 'OpenCode',
  codex: 'Codex',
  codebuddy: 'CodeBuddy',
  antigravity: 'Antigravity',
};

/**
 * Engines that only contribute read-only session history (no CLI adapter to
 * spawn/convert into). They show up as filter options but must NOT appear as
 * "convert this session into <engine>" targets. CodeBuddy is now a full
 * engine, so it is intentionally absent from this set.
 */
export const READ_ONLY_ENGINES: ReadonlySet<string> = new Set([]);

export const ALL_ENGINES = Object.keys(ENGINE_LABELS);

export function engineLabel(engine: string): string {
  return ENGINE_LABELS[engine] ?? engine;
}
