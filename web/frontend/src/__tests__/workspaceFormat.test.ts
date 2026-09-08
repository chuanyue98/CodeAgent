import { describe, expect, test } from 'vitest';
import { formatWorkspaceLabel } from '../utils/workspaceFormat';

describe('formatWorkspaceLabel', () => {
  test('formats workspace path with group when group is not common', () => {
    expect(formatWorkspaceLabel('/home/cy/github/chuanyue98/CodeAgent', 'codeagent')).toBe(
      'CodeAgent (codeagent)',
    );
  });

  test('formats workspace path without group suffix when group is common or omitted', () => {
    expect(formatWorkspaceLabel('/home/cy/github/chuanyue98/CodeAgent', 'common')).toBe('CodeAgent');
    expect(formatWorkspaceLabel('/home/cy/github/chuanyue98/CodeAgent')).toBe('CodeAgent');
  });

  test('handles root path', () => {
    expect(formatWorkspaceLabel('/')).toBe('/');
  });

  test('handles empty string', () => {
    expect(formatWorkspaceLabel('')).toBe('');
  });
});
