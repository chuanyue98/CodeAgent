export type TerminalEventType = 'waiting_input' | 'completed' | 'rate_limit';

/**
 * Strips ANSI escape codes from a terminal string chunk.
 */
export function stripAnsi(str: string): string {
  if (!str || typeof str !== 'string') return '';
  return str.replace(
    // eslint-disable-next-line no-control-regex
    /[\u001b\u009b](?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~]|\].*?(?:\x07|\x1b\\))/g,
    ''
  );
}

// Patterns matching rate limit / quota exhaustion errors from LLM engines
const RATE_LIMIT_REGEX =
  /(?:\b(?:(?:status(?:\s+code)?|code|http|error)\s*[:=]?\s*429|429\s+(?:too\s+many\s+requests|rate\s*limit|quota|error|status|code|client\s+error))\b|\[(?:error|err)\]\s*429\b|rate[\s_-]*limit|quota[\s_-]*exceeded|insufficient[\s_-]*quota|resource[\s_-]*exhausted|resource\s+has\s+been\s+exhausted|too[\s_-]*many[\s_-]*requests)/i;

// Patterns matching prompts waiting for user input / confirmation
const WAITING_INPUT_REGEX =
  /(?:\[\s*(?:y\s*\/\s*n|n\s*\/\s*y)(?:\s*\/\s*[a-zA-Z])*\s*\]|\(\s*(?:y\s*\/\s*n|n\s*\/\s*y)(?:\s*\/\s*[a-zA-Z])*\s*\)|\[\s*(?:yes\/no|no\/yes)\s*\]|\(\s*(?:yes\/no|no\/yes)\s*\)|press\s+(?:enter|return|any\s+key)|do\s+you\s+want\s+to\s+proceed|are\s+you\s+sure\b)/i;

// Patterns matching task completion
const COMPLETED_REGEX =
  /(?:(?:done|finished|completed|passed)\s+in\s+\d+(?:\.\d+)?\s*(?:ms|min(?:ute)?s?|sec(?:ond)?s?|[smh])\b|task\s+completed|task\s+finished|prompt\s+returned|execution\s+completed)/i;

/**
 * Analyzes a chunk of terminal output to detect noteworthy events:
 * - 'rate_limit': when LLM quota or API limit is exceeded (e.g. 429)
 * - 'waiting_input': when an agent or CLI tool is blocked waiting for interactive user response
 * - 'completed': when a background task or run has finished execution
 */
export function detectTerminalEvent(chunk: string): TerminalEventType | null {
  if (!chunk || typeof chunk !== 'string') {
    return null;
  }

  const clean = stripAnsi(chunk);
  if (!clean.trim()) {
    return null;
  }

  if (RATE_LIMIT_REGEX.test(clean)) {
    return 'rate_limit';
  }

  if (WAITING_INPUT_REGEX.test(clean)) {
    return 'waiting_input';
  }

  if (COMPLETED_REGEX.test(clean)) {
    return 'completed';
  }

  return null;
}
