import { describe, expect, test, vi, beforeEach, afterEach } from 'vitest';
import { formatWorkspaceLabel, formatRelativeCountdown } from '../utils/workspaceFormat';

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

describe('formatRelativeCountdown', () => {
  const baseTime = 1725796800; // 2024-09-08 12:00:00 UTC

  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(baseTime * 1000));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  test('returns empty string when target time is 0, negative, or in the past', () => {
    expect(formatRelativeCountdown(0)).toBe('');
    expect(formatRelativeCountdown(-10)).toBe('');
    expect(formatRelativeCountdown(baseTime - 10)).toBe('');
    expect(formatRelativeCountdown(baseTime)).toBe('');
  });

  test('formats target time within 60 seconds (< 1m / 即将执行)', () => {
    expect(formatRelativeCountdown(baseTime + 30, 'en')).toBe('< 1m');
    expect(formatRelativeCountdown(baseTime + 30, 'zh')).toBe('即将执行');
    expect(formatRelativeCountdown(baseTime + 10, 'zh-CN')).toBe('即将执行');
  });

  test('formats target time in minutes (e.g. 15m)', () => {
    expect(formatRelativeCountdown(baseTime + 15 * 60, 'en')).toBe('in 15m');
    expect(formatRelativeCountdown(baseTime + 15 * 60, 'zh')).toBe('15分钟后');
  });

  test('formats target time in hours (e.g. 3h)', () => {
    expect(formatRelativeCountdown(baseTime + 3 * 3600, 'en')).toBe('in 3h');
    expect(formatRelativeCountdown(baseTime + 3 * 3600, 'zh')).toBe('3小时后');
  });

  test('formats target time in days (e.g. 2d)', () => {
    expect(formatRelativeCountdown(baseTime + 2 * 86400, 'en')).toBe('in 2d');
    expect(formatRelativeCountdown(baseTime + 2 * 86400, 'zh')).toBe('2天后');
  });
});

