import { describe, expect, it } from 'vitest';
import { detectTerminalEvent, stripAnsi } from '../utils/terminalDetector';

describe('terminalDetector', () => {
  describe('stripAnsi', () => {
    it('removes ANSI color codes', () => {
      const raw = '\u001b[31mRed Text\u001b[0m and \u001b[32mGreen Text\u001b[0m';
      expect(stripAnsi(raw)).toBe('Red Text and Green Text');
    });

    it('removes complex ANSI sequences', () => {
      const raw = '\u001b[1;33;40mBold Yellow\u001b[0m\u001b[?25h';
      expect(stripAnsi(raw)).toBe('Bold Yellow');
    });

    it('handles clean strings unchanged', () => {
      expect(stripAnsi('Just plain text')).toBe('Just plain text');
    });
  });

  describe('detectTerminalEvent', () => {
    describe('waiting_input', () => {
      it('detects [y/n] questions', () => {
        expect(detectTerminalEvent('Do you want to apply changes? [y/n]: ')).toBe('waiting_input');
        expect(detectTerminalEvent('Proceed with execution? [Y/n]')).toBe('waiting_input');
        expect(detectTerminalEvent('Overwrite file? [y/N]')).toBe('waiting_input');
      });

      it('detects (y/n) questions', () => {
        expect(detectTerminalEvent('Save session? (y/n)')).toBe('waiting_input');
        expect(detectTerminalEvent('Continue? (Y/N)')).toBe('waiting_input');
      });

      it('detects multi-option confirmations like [y/n/a/d]', () => {
        expect(detectTerminalEvent('Apply this edit? [y/n/a/d]')).toBe('waiting_input');
        expect(detectTerminalEvent('Confirm action? (y/n/c)')).toBe('waiting_input');
      });

      it('detects [yes/no] questions', () => {
        expect(detectTerminalEvent('Are you sure? [yes/no]')).toBe('waiting_input');
      });

      it('detects enter prompt', () => {
        expect(detectTerminalEvent('Press enter to continue...')).toBe('waiting_input');
        expect(detectTerminalEvent('Press ENTER to run command')).toBe('waiting_input');
        expect(detectTerminalEvent('Press any key to resume')).toBe('waiting_input');
      });

      it('detects proceed confirmation prompts', () => {
        expect(detectTerminalEvent('Do you want to proceed?')).toBe('waiting_input');
        expect(detectTerminalEvent('Are you sure you want to proceed?')).toBe('waiting_input');
      });

      it('detects waiting_input with ANSI escapes', () => {
        const colored = '\u001b[1m\u001b[33mDo you want to proceed? [y/n]\u001b[0m ';
        expect(detectTerminalEvent(colored)).toBe('waiting_input');
      });
    });

    describe('rate_limit', () => {
      it('detects HTTP 429 status', () => {
        expect(detectTerminalEvent('HTTP 429 Too Many Requests')).toBe('rate_limit');
        expect(detectTerminalEvent('Error: Request failed with status code 429')).toBe('rate_limit');
        expect(detectTerminalEvent('API error 429')).toBe('rate_limit');
      });

      it('detects rate limit messages', () => {
        expect(detectTerminalEvent('Rate limit exceeded. Please try again later.')).toBe('rate_limit');
        expect(detectTerminalEvent('rate_limit_error: Tokens per min exceeded')).toBe('rate_limit');
      });

      it('detects quota exceeded messages', () => {
        expect(detectTerminalEvent('Quota exceeded for model claude-3-5-sonnet')).toBe('rate_limit');
        expect(detectTerminalEvent('insufficient_quota')).toBe('rate_limit');
      });

      it('detects resource exhausted messages', () => {
        expect(detectTerminalEvent('RESOURCE_EXHAUSTED: quota reached')).toBe('rate_limit');
        expect(detectTerminalEvent('Resource has been exhausted')).toBe('rate_limit');
      });

      it('detects rate_limit with ANSI escapes', () => {
        const colored = '\u001b[31m[ERROR] 429 Rate limit reached for model\u001b[0m';
        expect(detectTerminalEvent(colored)).toBe('rate_limit');
      });
    });

    describe('completed', () => {
      it('detects "Done in" patterns', () => {
        expect(detectTerminalEvent('✨ Done in 1.42s')).toBe('completed');
        expect(detectTerminalEvent('Done in 320ms.')).toBe('completed');
        expect(detectTerminalEvent('done in 3m')).toBe('completed');
      });

      it('detects "Finished in" patterns', () => {
        expect(detectTerminalEvent('Finished in 0.8s')).toBe('completed');
        expect(detectTerminalEvent('Build finished in 45s')).toBe('completed');
      });

      it('detects "Completed in" patterns', () => {
        expect(detectTerminalEvent('Completed in 12.5s')).toBe('completed');
      });

      it('detects task completed and prompt returned', () => {
        expect(detectTerminalEvent('Task completed successfully.')).toBe('completed');
        expect(detectTerminalEvent('Task finished.')).toBe('completed');
        expect(detectTerminalEvent('Prompt returned.')).toBe('completed');
        expect(detectTerminalEvent('Execution completed.')).toBe('completed');
      });

      it('detects completed with ANSI escapes', () => {
        const colored = '\u001b[32m✔ Task completed in 4.2s\u001b[0m';
        expect(detectTerminalEvent(colored)).toBe('completed');
      });
    });

    describe('null / non-events', () => {
      it('returns null for normal terminal output', () => {
        expect(detectTerminalEvent('const x = 42;')).toBeNull();
        expect(detectTerminalEvent('Compiling 14 files...')).toBeNull();
        expect(detectTerminalEvent('Reading /workspace/src/app.ts')).toBeNull();
        expect(detectTerminalEvent('Line 428 in index.ts')).toBeNull();
      });

      it('returns null for empty strings or falsy values', () => {
        expect(detectTerminalEvent('')).toBeNull();
        expect(detectTerminalEvent('   \r\n   ')).toBeNull();
        // @ts-expect-error testing invalid inputs
        expect(detectTerminalEvent(null)).toBeNull();
        // @ts-expect-error testing invalid inputs
        expect(detectTerminalEvent(undefined)).toBeNull();
      });
    });
  });
});
