/**
 * The provider engines the app knows about, mirroring `ENGINES` in
 * core/constants.py. Kept in one place so the filter sidebar, the
 * convert-to-engine actions and the session detail panel can't drift apart.
 */
export const ENGINE_LABELS: Record<string, string> = {
  claude: 'Claude',
  gemini: 'Gemini',
  opencode: 'OpenCode',
  codex: 'Codex',
};

export const ALL_ENGINES = Object.keys(ENGINE_LABELS);

export function engineLabel(engine: string): string {
  return ENGINE_LABELS[engine] ?? engine;
}
