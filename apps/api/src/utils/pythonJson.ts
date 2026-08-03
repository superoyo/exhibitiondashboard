/**
 * JSON text written the way Python's `json.dumps(..., ensure_ascii=False)` does.
 *
 * Why this exists: `groups_json` / `subgroups_json` are TEXT columns holding
 * JSON, and during the migration BOTH services write them against the same
 * database. Python emits a space after each comma (`["A", "B"]`) while
 * `JSON.stringify` does not (`["A","B"]`).
 *
 * The two parse identically, so this is about keeping stored data uniform rather
 * than about correctness — otherwise a column's byte content would depend on
 * which service happened to write it, and diffing DB state between the two
 * services would be permanently noisy.
 *
 * `ensure_ascii=False` needs no special handling: both leave Thai characters
 * literal rather than escaping them.
 */
export function pyJsonList(values: string[]): string {
  return `[${values.map((v) => JSON.stringify(v)).join(', ')}]`;
}

/** What we ever store in a JSON text column. */
type PyJsonValue = string | number | boolean | null | PyJsonValue[] | { [k: string]: PyJsonValue };

/**
 * General `json.dumps(value, ensure_ascii=False)` equivalent.
 *
 * Python's default separators are `', '` and `': '`, so an object serialises as
 * `{"a": 1, "b": 2}` where `JSON.stringify` gives `{"a":1,"b":2}`. Needed for
 * `links_json`, which holds objects rather than the plain string lists
 * `pyJsonList` covers.
 */
export function pyJsonDumps(value: PyJsonValue): string {
  if (value === null) return 'null';
  if (typeof value === 'string') return JSON.stringify(value);
  if (typeof value === 'number') return JSON.stringify(value);
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (Array.isArray(value)) return `[${value.map(pyJsonDumps).join(', ')}]`;
  const entries = Object.entries(value).map(([k, v]) => `${JSON.stringify(k)}: ${pyJsonDumps(v)}`);
  return `{${entries.join(', ')}}`;
}

/**
 * Truncate by CODE POINTS, as Python string slicing does.
 *
 * `'🎯🎯🎯🎯🎯🎯'.slice(0, 8)` keeps only 4 emoji, because each non-BMP emoji is
 * two UTF-16 code units in JavaScript. Python counts code points, and so does
 * Postgres for `varchar(n)` — so slicing by units would both truncate more
 * aggressively than Python AND under-use the column.
 *
 * Note this can still split a multi-code-point grapheme (e.g. a ZWJ family
 * emoji); Python behaves the same way, so the port stays faithful.
 */
export function sliceCodePoints(value: string, max: number): string {
  return [...value].slice(0, max).join('');
}
