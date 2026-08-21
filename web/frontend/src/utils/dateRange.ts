/**
 * Helpers for turning a `<input type="date">` value (a bare `YYYY-MM-DD`
 * calendar day, always meaning a day in the *viewer's* timezone) into the
 * absolute instants the API and client-side filters need.
 *
 * Passing the bare day straight through treats it as UTC midnight, which
 * shifts the window by the viewer's UTC offset: in UTC+8, picking "Aug 21"
 * used to select Aug 21 08:00 through Aug 22 08:00 local — dropping the
 * first eight hours of the day and picking up eight hours of the next one.
 */

const DAY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Parses `YYYY-MM-DD` as local midnight, or null if it isn't a valid day. */
function parseLocalDay(day: string): Date | null {
  const match = DAY_PATTERN.exec(day);
  if (!match) return null;
  const [, year, month, date] = match;
  const parsed = new Date(Number(year), Number(month) - 1, Number(date));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

/**
 * Formats a Date as a local `YYYY-MM-DD` calendar day.
 *
 * `toISOString().slice(0, 10)` is the tempting one-liner and is wrong for the
 * same reason the helpers below exist: it reports the UTC day, which is
 * yesterday's date for much of the evening east of Greenwich.
 */
export function toLocalDayString(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${date.getFullYear()}-${month}-${day}`;
}

/** The local `YYYY-MM-DD` day `days` before today (0 → today). */
export function localDayOffset(days: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  return toLocalDayString(date);
}

/** First instant of the local day, as a UTC ISO string. Empty input → undefined. */
export function localDayStartISO(day: string): string | undefined {
  const parsed = parseLocalDay(day);
  return parsed ? parsed.toISOString() : undefined;
}

/** Last instant of the local day (inclusive), as a UTC ISO string. */
export function localDayEndISO(day: string): string | undefined {
  const parsed = parseLocalDay(day);
  if (!parsed) return undefined;
  parsed.setHours(23, 59, 59, 999);
  return parsed.toISOString();
}

/**
 * Whether `timestamp` falls inside the local-day range [start, end], where
 * either bound may be an empty string meaning "unbounded". A timestamp that
 * can't be parsed passes only when no bound is set, since there is no way to
 * place it inside a range the user explicitly asked for.
 */
export function isWithinLocalDayRange(
  timestamp: string,
  start: string,
  end: string,
): boolean {
  const from = localDayStartISO(start);
  const to = localDayEndISO(end);
  if (!from && !to) return true;

  const at = new Date(timestamp).getTime();
  if (Number.isNaN(at)) return false;

  if (from && at < new Date(from).getTime()) return false;
  if (to && at > new Date(to).getTime()) return false;
  return true;
}
