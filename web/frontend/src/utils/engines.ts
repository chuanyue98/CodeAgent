/**
 * The provider engines the app knows about, mirroring `ENGINES` in
 * core/constants.py. Kept in one place so the filter sidebar, the
 * convert-to-engine actions and the session detail panel can't drift apart.
 * freebuff 只有交互式历史/恢复（免费版 CLI 无 headless 通道），所以它出现在
 * 过滤与展示里，但不会被当作 Chat/任务的可用引擎。
 */
export const ENGINE_LABELS: Record<string, string> = {
  claude: 'Claude',
  opencode: 'OpenCode',
  codex: 'Codex',
  codebuddy: 'CodeBuddy',
  freebuff: 'Freebuff',
};

/**
 * Engines that only contribute read-only session history (no CLI adapter to
 * convert *into* -- freebuff 免费版 CLI 没有 headless 通道，转换写入它目前
 * 明确失败，见 core/session_history/writers/freebuff_writer.py). They show up
 * as filter options but must NOT appear as "convert this session into
 * <engine>" targets. CodeBuddy is now a full engine, so it is intentionally
 * absent from this set.
 */
export const READ_ONLY_ENGINES: ReadonlySet<string> = new Set(['freebuff']);

export const ALL_ENGINES = Object.keys(ENGINE_LABELS);

export function engineLabel(engine: string): string {
  return ENGINE_LABELS[engine] ?? engine;
}
