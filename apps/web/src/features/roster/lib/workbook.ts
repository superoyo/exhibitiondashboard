// Types only — `import type` is erased at compile time, so SheetJS itself is
// NOT pulled into this chunk. The runtime module is loaded on demand below.
import type * as XLSX from 'xlsx';
import type { BulkKol } from '@kol/shared';

import {
  dedupeLinks,
  handleFromUrl,
  isProfileUrl,
  looksUrl,
  NONWORK_URL,
  normalizeUrl,
  platformOf,
  urlsIn,
} from './urlHelpers';

/**
 * Excel/CSV → KOL list.
 *
 * A single cell often holds several platform links, so every URL in a row is
 * collected and classified rather than assuming one link per column.
 *
 * Grouping precedence, unchanged from the legacy parser:
 *   explicit หมวด/group column  >  sheet name (multi-sheet)  >  section-header row
 */

/**
 * Stringify one spreadsheet cell.
 *
 * `sheet_to_json` yields strings, numbers, booleans or Dates. Anything else is
 * treated as empty rather than stringified — a stray object would otherwise
 * become the literal text "[object Object]" and could be mistaken for a
 * username or a group name.
 */
function cellText(v: unknown): string {
  if (v == null) return '';
  if (typeof v === 'string') return v.trim();
  if (typeof v === 'number' || typeof v === 'boolean') return String(v);
  if (v instanceof Date) return v.toISOString();
  return '';
}

const text = cellText;
const lower = (v: unknown): string => cellText(v).toLowerCase();

/** First header column whose name contains any of `keys`. */
function pickCol(headers: string[], keys: string[]): number {
  for (let i = 0; i < headers.length; i++) {
    const h = headers[i];
    if (h && keys.some((k) => h.includes(k))) return i;
  }
  return -1;
}

const COL_USERNAME = [
  'username',
  'handle',
  'ผู้ใช้',
  'บัญชี',
  'user',
  'ไอดี',
  'ชื่อบัญชี',
  'account',
  'ช่อง',
  'channel',
  'kol',
  'influencer',
  'influ',
  'อินฟลู',
  'ชื่อ',
  'name',
];
const COL_GROUP = ['หมวด', 'ประเภท', 'group', 'category', 'type', 'tier', 'กลุ่ม'];
const COL_SUBGROUP = ['ย่อย', 'subgroup', 'sub'];
const COL_FOLLOWERS = ['follow', 'ติดตาม', 'fan'];

/** Words that leak in as a "username" when a header row is mistaken for data. */
const HEADER_WORDS = new Set([
  'name',
  'ชื่อ',
  'username',
  'user',
  'kol',
  'influencer',
  'influ',
  'link',
  'ลิงก์',
  'no',
  'ลำดับ',
  'account',
  'ช่อง',
  'channel',
  'handle',
  'id',
]);

const SOCIAL = /(tiktok\.com|facebook\.com|fb\.watch|instagram\.com|youtu|x\.com|twitter\.com)/i;

/** Sheet/column words that mark a shipping-address tab rather than campaign work. */
const ADDRESS_WORDS = [
  'address',
  'addr',
  'ที่อยู่',
  'จัดส่ง',
  'ส่งของ',
  'shipping',
  'delivery',
  'ไปรษณีย์',
  'พัสดุ',
  'tracking',
  'ผู้รับ',
  'เบอร์',
  'โทร',
  'ของรางวัล',
  'เลขที่บ้าน',
];

/** The SheetJS module, passed in so it can be loaded on demand. */
type XlsxModule = typeof import('xlsx');

export interface ParsedWorkbook {
  kols: BulkKol[];
  /** Per-sheet header summary, shown when nothing could be parsed. */
  debug: string;
  /** Sheets skipped as non-work (e.g. address tabs). */
  skipped: string[];
}

/**
 * Cell hyperlinks, keyed by row index. Teams often hyperlink the KOL's *name*
 * to their profile page, so this is sometimes the only place a username appears.
 */
function collectHyperlinks(xlsx: XlsxModule, sheet: XLSX.WorkSheet): Record<number, string[]> {
  const hyper: Record<number, string[]> = {};
  try {
    const range = xlsx.utils.decode_range(sheet['!ref'] ?? 'A1');
    for (let r = range.s.r; r <= range.e.r; r++) {
      for (let c = range.s.c; c <= range.e.c; c++) {
        const cell = sheet[xlsx.utils.encode_cell({ r, c })] as XLSX.CellObject | undefined;
        const target = cell?.l?.Target;
        if (target && /^https?:/i.test(target)) {
          const key = r - range.s.r;
          (hyper[key] ??= []).push(target);
        }
      }
    }
  } catch {
    // A malformed !ref just means no hyperlink data; row text still parses.
  }
  return hyper;
}

export function parseWorkbook(xlsx: XlsxModule, wb: XLSX.WorkBook): ParsedWorkbook {
  const kols: BulkKol[] = [];
  const debug: string[] = [];
  const skipped: string[] = [];
  const multiSheet = wb.SheetNames.length > 1;

  for (const sheetName of wb.SheetNames) {
    const sheet = wb.Sheets[sheetName];
    if (!sheet) continue;

    const rows = xlsx.utils.sheet_to_json<unknown[]>(sheet, {
      header: 1,
      blankrows: true,
      defval: '',
    });
    if (!rows.length) continue;

    const hyper = collectHyperlinks(xlsx, sheet);

    // Header = the first row with any content.
    let headerIndex = 0;
    for (let i = 0; i < rows.length; i++) {
      if ((rows[i] ?? []).filter((c) => text(c)).length >= 1) {
        headerIndex = i;
        break;
      }
    }
    const headerRow = rows[headerIndex] ?? [];
    const headers = headerRow.map(lower);
    debug.push(`“${sheetName}” [${headers.filter(Boolean).join(', ')}]`);

    // Skip address-style sheets: no social link anywhere AND an address-ish name.
    const hasSocial = rows.some((r) => (r ?? []).some((c) => SOCIAL.test(text(c))));
    const meta = `${lower(sheetName)} ${headers.join(' ')}`;
    if (!hasSocial && ADDRESS_WORDS.some((k) => meta.includes(k))) {
      skipped.push(sheetName);
      continue;
    }

    const cUser = pickCol(headers, COL_USERNAME);
    const cGroup = pickCol(headers, COL_GROUP);
    const cSub = pickCol(headers, COL_SUBGROUP);
    const cFollowers = pickCol(headers, COL_FOLLOWERS);

    // A "header" row that already contains links/@handles IS data.
    const headerIsData = headerRow.some((c) => looksUrl(cellText(c)) || /^@[\w.]+$/.test(text(c)));

    let section = ''; // last-seen section-header text, for single-sheet grouping

    for (let i = headerIsData ? headerIndex : headerIndex + 1; i < rows.length; i++) {
      const row = rows[i] ?? [];
      const filled = row.filter((c) => text(c));
      if (!filled.length) continue;

      const hyperUrls = (hyper[i] ?? [])
        .map((u) => normalizeUrl(u.trim()))
        .filter((u) => !NONWORK_URL.test(u));
      const urls = [...new Set([...urlsIn(row.map(text).join('  ')), ...hyperUrls])];

      // A short text-only row with no links is a section/category header.
      if (!urls.length && !multiSheet && cGroup < 0 && filled.length <= 2) {
        const label = filled.map(text).find((v) => v && !/^\d+$/.test(v) && !/^#/.test(v));
        if (label) section = label;
        continue;
      }

      const profileUrls = urls.filter(isProfileUrl);
      const workUrls = urls.filter((u) => !isProfileUrl(u));

      // Username, in descending order of reliability.
      let username = cUser >= 0 ? text(row[cUser]).replace(/^@/, '') : '';
      if (/https?:|\//.test(username)) username = handleFromUrl(username);
      if (!username) {
        const at = filled.map(text).find((v) => /^@[\w.]+$/.test(v));
        if (at) username = at.slice(1);
      }
      if (!username && profileUrls.length) username = handleFromUrl(profileUrls[0] ?? '');
      if (!username && workUrls.length) {
        const preferred = workUrls.find((u) => platformOf(u) === 'tiktok') ?? workUrls[0] ?? '';
        username = handleFromUrl(preferred);
      }
      if (!username && !workUrls.length) continue; // nothing usable in this row

      // A header row leaking through: a header word with no post link.
      if (!workUrls.length && HEADER_WORDS.has(username.toLowerCase())) continue;

      const columnGroup = cGroup >= 0 ? text(row[cGroup]) : '';
      const group = columnGroup || (multiSheet ? text(sheetName) || 'KOL' : section || 'KOL');

      let followers = 0;
      if (cFollowers >= 0) {
        const parsed = Number.parseInt(text(row[cFollowers]).replace(/[^0-9]/g, ''), 10);
        if (!Number.isNaN(parsed)) followers = parsed;
      }

      kols.push({
        username: username.toLowerCase(),
        display: (cUser >= 0 ? text(row[cUser]) : '') || username,
        group,
        subgroup: cSub >= 0 ? text(row[cSub]) : '',
        links: dedupeLinks(workUrls),
        followers,
      });
    }
  }

  return { kols, debug: debug.join('  ·  '), skipped };
}

/**
 * SheetJS is ~120 kB gzipped and only needed the moment someone actually
 * imports a file, so it is loaded on demand rather than bundled into the page.
 */
async function loadXlsx(): Promise<XlsxModule> {
  return import('xlsx');
}

/** Read + parse an uploaded Excel/CSV file. */
export async function parseSpreadsheetFile(file: File): Promise<ParsedWorkbook> {
  const xlsx = await loadXlsx();
  return parseWorkbook(xlsx, xlsx.read(await file.arrayBuffer(), { type: 'array' }));
}

/** Read + parse raw spreadsheet bytes from the sheet-fetch proxy. */
export async function parseSpreadsheetBytes(bytes: ArrayBuffer): Promise<ParsedWorkbook> {
  const xlsx = await loadXlsx();
  return parseWorkbook(xlsx, xlsx.read(bytes, { type: 'array' }));
}
