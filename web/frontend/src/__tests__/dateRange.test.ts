import { describe, expect, test } from 'vitest';
import { isWithinLocalDayRange, localDayEndISO, localDayStartISO } from '../utils/dateRange';

/**
 * A `<input type="date">` value means a calendar day in the *viewer's*
 * timezone, so the instants it spans move with the UTC offset. The bug these
 * helpers fix was sending the bare day to an API that parsed it as UTC
 * midnight, shifting the window by the offset.
 *
 * The assertions below are written against local date components rather than
 * literal ISO strings so they hold in any runner timezone. They only
 * distinguish the old behaviour from the new one when the runner sits off
 * UTC — which is exactly where the bug was observable.
 */
describe('localDayStartISO / localDayEndISO', () => {
  test('anchors the start bound to local midnight of that day', () => {
    const start = new Date(localDayStartISO('2026-08-21')!);
    expect(start.getFullYear()).toBe(2026);
    expect(start.getMonth()).toBe(7);
    expect(start.getDate()).toBe(21);
    expect(start.getHours()).toBe(0);
    expect(start.getMinutes()).toBe(0);
    expect(start.getSeconds()).toBe(0);
  });

  test('anchors the end bound to the last local millisecond of that day', () => {
    const end = new Date(localDayEndISO('2026-08-21')!);
    expect(end.getDate()).toBe(21);
    expect(end.getHours()).toBe(23);
    expect(end.getMinutes()).toBe(59);
    expect(end.getSeconds()).toBe(59);
    expect(end.getMilliseconds()).toBe(999);
  });

  test('the two bounds span exactly one day', () => {
    const start = new Date(localDayStartISO('2026-08-21')!).getTime();
    const end = new Date(localDayEndISO('2026-08-21')!).getTime();
    expect(end - start).toBe(86_400_000 - 1);
  });

  test('returns a UTC ISO string the API can parse', () => {
    expect(localDayStartISO('2026-08-21')).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
    expect(localDayEndISO('2026-08-21')).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/);
  });

  test('rejects empty and malformed input instead of inventing a bound', () => {
    expect(localDayStartISO('')).toBeUndefined();
    expect(localDayEndISO('')).toBeUndefined();
    expect(localDayStartISO('2026-8-1')).toBeUndefined();
    expect(localDayStartISO('not-a-date')).toBeUndefined();
  });
});

describe('isWithinLocalDayRange', () => {
  const noon = new Date(2026, 7, 21, 12, 0, 0).toISOString();
  const dayBefore = new Date(2026, 7, 20, 23, 30, 0).toISOString();
  const dayAfter = new Date(2026, 7, 22, 0, 30, 0).toISOString();

  test('passes everything when neither bound is set', () => {
    expect(isWithinLocalDayRange(noon, '', '')).toBe(true);
    expect(isWithinLocalDayRange('nonsense', '', '')).toBe(true);
  });

  test('includes both edges of the selected day', () => {
    const firstInstant = new Date(2026, 7, 21, 0, 0, 0, 0).toISOString();
    const lastInstant = new Date(2026, 7, 21, 23, 59, 59, 999).toISOString();

    expect(isWithinLocalDayRange(firstInstant, '2026-08-21', '2026-08-21')).toBe(true);
    expect(isWithinLocalDayRange(lastInstant, '2026-08-21', '2026-08-21')).toBe(true);
    expect(isWithinLocalDayRange(noon, '2026-08-21', '2026-08-21')).toBe(true);
  });

  test('excludes the neighbouring days', () => {
    expect(isWithinLocalDayRange(dayBefore, '2026-08-21', '2026-08-21')).toBe(false);
    expect(isWithinLocalDayRange(dayAfter, '2026-08-21', '2026-08-21')).toBe(false);
  });

  test('honours an open-ended range', () => {
    expect(isWithinLocalDayRange(dayAfter, '2026-08-21', '')).toBe(true);
    expect(isWithinLocalDayRange(dayBefore, '2026-08-21', '')).toBe(false);
    expect(isWithinLocalDayRange(dayBefore, '', '2026-08-21')).toBe(true);
    expect(isWithinLocalDayRange(dayAfter, '', '2026-08-21')).toBe(false);
  });

  test('drops unparseable timestamps once a bound is set', () => {
    expect(isWithinLocalDayRange('', '2026-08-21', '')).toBe(false);
    expect(isWithinLocalDayRange('nonsense', '', '2026-08-21')).toBe(false);
  });
});
