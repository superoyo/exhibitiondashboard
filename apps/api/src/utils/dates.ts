/**
 * Timestamp serialisation, byte-identical to the Python app.
 *
 * This is subtler than it looks. Postgres renders `timestamptz` in the SESSION
 * timezone, and the Python service runs as `TZ=Asia/Bangkok`, so SQLAlchemy gets
 * an offset-aware datetime and `.isoformat()` prints:
 *
 *     2026-07-30T15:59:32.344588+07:00
 *
 * Two things would go wrong if we round-tripped through a JS `Date`:
 *
 *   1. `toISOString()` re-renders the same instant in UTC
 *      (`2026-07-30T08:59:32.344Z`). Semantically identical, but any consumer
 *      that slices the date out of the string, or renders it without applying
 *      the offset, silently shifts by 7 hours — enough to report the wrong DAY
 *      for anything near midnight. `/api/campaigns/summary` feeds an external
 *      system (Agency Intelligence) whose parser we do not control.
 *   2. `Date` has millisecond precision, so `.344588` would become `.344000`.
 *
 * So the timestamp columns are declared `mode: 'string'` and Postgres's own text
 * is reused verbatim. Only the separator and the offset spelling need adjusting:
 * Postgres writes `... 15:59:32.344588+07`, Python writes `...T15:59:32.344588+07:00`.
 *
 * Keeping these strings identical is also what makes the rest of the migration
 * verifiable by diffing Express responses against Python's.
 */

/** `YYYY-MM-DD HH:MM:SS[.ffffff]±HH[[:]MM]` as emitted by Postgres. */
const PG_TIMESTAMPTZ =
  /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2}(?:\.\d+)?)([+-]\d{2})(?::?(\d{2}))?$/;

/**
 * Postgres timestamptz text -> Python `datetime.isoformat()` spelling.
 * Returns null for null input, matching Python's `or None` pattern.
 */
export function toIsoLocal(value: string | Date | null | undefined): string | null {
  if (value == null) return null;

  // Defensive: a Date can only arrive if a column is left in the default mode.
  // Preserve the instant rather than silently emitting a wrong local time.
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value.toISOString();
  }

  const match = PG_TIMESTAMPTZ.exec(value.trim());
  // Unrecognised shape: pass it through rather than corrupting it.
  if (!match) return value;

  const [, datePart, clock = '', offsetHours, offsetMinutes = '00'] = match;

  // Postgres trims trailing zeros from the fraction ('.1524'); Python always
  // pads microseconds to six digits ('.152400'). Pad to match.
  const [seconds = '', fraction] = clock.split('.');
  const padded =
    fraction === undefined ? seconds : `${seconds}.${fraction.padEnd(6, '0').slice(0, 6)}`;

  return `${datePart}T${padded}${offsetHours}:${offsetMinutes}`;
}

/**
 * `YYYY-MM-DD` for a Postgres DATE column.
 *
 * node-postgres already yields `YYYY-MM-DD` for DATE, so this is a slice — NOT a
 * timezone conversion, which would be wrong for a date that has no time at all.
 */
export function toIsoDate(value: string | Date | null | undefined): string | null {
  if (value == null) return null;
  if (typeof value === 'string') return value.slice(0, 10);
  return Number.isNaN(value.getTime()) ? null : value.toISOString().slice(0, 10);
}
