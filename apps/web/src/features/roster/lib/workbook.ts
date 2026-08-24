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
  'acc',
  'เพจ',
  'fanpage',
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
// Commercial columns from the planner's sheet. Boost is matched BEFORE cost so
// a header like "Boost Budget" cannot be eaten by the generic "budget"/"ราคา"
// cost words. KPI columns are collected (plural — some sheets split unit and
// number into two columns) and their text is parsed as one string.
const COL_BOOST = ['boost', 'บูส'];
const COL_COST = ['cost', 'ค่าตัว', 'ราคา', 'rate', 'budget', 'งบ'];
const COL_KPI = ['kpi', 'การันตี', 'เป้า', 'target', 'guarantee'];

/**
 * "12,500", "฿12,500.50", "100K", "1.2m" → number. null when no digits.
 * K/M suffixes appear constantly in planner KPI cells ("100K views").
 */
function parseAmount(raw: string): number | null {
  const m = /([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmM]?)/.exec(raw.replace(/[฿$]/g, ''));
  if (!m?.[1]) return null;
  const base = Number.parseFloat(m[1].replace(/,/g, ''));
  if (!Number.isFinite(base)) return null;
  const mul = m[2]?.toLowerCase() === 'k' ? 1_000 : m[2]?.toLowerCase() === 'm' ? 1_000_000 : 1;
  return base * mul;
}

/** The unit vocabulary the planner team actually sells on. */
function kpiMetricOf(fragment: string): string {
  const low = fragment.toLowerCase();
  if (/reach|รีช|เข้าถึง/.test(low)) return 'reach';
  if (/imp|อิม/.test(low)) return 'impressions';
  if (/inter|eng|ปฏิสัมพันธ์|เอนเกจ/.test(low)) return 'interaction';
  if (/view|วิว|ยอดชม/.test(low)) return 'views';
  return '';
}

/**
 * KPI cell text → list of {metric, target}. A LIST, because one KOL can be
 * sold on two KPIs at once — "100K Views + 5,000 Engagement". The text is
 * split on the separators planner sheets actually use (/ + , และ newlines)
 * and each fragment read as "unit word + number"; a fragment with a number
 * but an unrecognised word keeps the number with metric '' rather than being
 * dropped. Units seen so far: Views · Impressions · Interaction/Engagement ·
 * Reach (the last two verifiable only from the creator's own insights).
 */
function parseKpis(raw: string): { metric: string; target: number }[] {
  const out: { metric: string; target: number }[] = [];
  // A comma is a LIST separator only when what follows is not a digit —
  // otherwise it is the thousands separator inside "250,000".
  for (const fragment of raw.split(/[/+\n·]|และ|,(?=\s*\D)/)) {
    const target = parseAmount(fragment);
    if (target === null || target <= 0) continue;
    const metric = kpiMetricOf(fragment);
    if (out.some((k) => k.metric === metric)) continue; // same unit twice = noise
    out.push({ metric, target });
  }
  return out;
}

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

/**
 * A running-number cell — "1", "2.", "#3", "1.1" — is the sheet's row counter,
 * never an account. Bounded to 4 digits so a numeric Facebook page id
 * (100063588291234) is still allowed through as a handle.
 */
const INDEX_LIKE = /^#?\d{1,4}(\.\d{1,3})?\s*[.)]?$/;

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

/**
 * Sheets hidden inside the file are almost always leftovers from an old campaign
 * the team copied the file from, so they are never imported.
 *
 * Falls back to every sheet when they are ALL hidden — otherwise such a file
 * would import as empty with no explanation.
 */
function visibleSheetNames(wb: XLSX.WorkBook): string[] {
  const meta = wb.Workbook?.Sheets ?? [];
  const hidden = new Set(
    meta
      .filter((sheet) => sheet?.Hidden)
      .map((sheet) => sheet.name)
      .filter((name): name is string => Boolean(name)),
  );
  const visible = wb.SheetNames.filter((name) => !hidden.has(name));
  return visible.length ? visible : wb.SheetNames;
}

export function parseWorkbook(xlsx: XlsxModule, wb: XLSX.WorkBook): ParsedWorkbook {
  const kols: BulkKol[] = [];
  const debug: string[] = [];
  const skipped: string[] = [];
  const sheetNames = visibleSheetNames(wb);
  const multiSheet = sheetNames.length > 1;

  for (const sheetName of sheetNames) {
    const sheet = wb.Sheets[sheetName];
    if (!sheet) continue;

    const rows = xlsx.utils.sheet_to_json<unknown[]>(sheet, {
      header: 1,
      blankrows: true,
      defval: '',
    });
    if (!rows.length) continue;

    const hyper = collectHyperlinks(xlsx, sheet);

    // Header = the first row with at least two filled cells. A single-cell first
    // row is a merged campaign title ("รายชื่อ KOL <brand>"), and reading it as
    // the header made every column key match column A — the row counter — so the
    // numbers 1,2,3… were imported as usernames. Falls back to any content, for
    // sheets that really are one column wide.
    let headerIndex = -1;
    let firstFilled = -1;
    for (let i = 0; i < rows.length; i++) {
      const count = (rows[i] ?? []).filter((c) => text(c)).length;
      if (count >= 1 && firstFilled < 0) firstFilled = i;
      if (count >= 2) {
        headerIndex = i;
        break;
      }
    }
    if (headerIndex < 0) headerIndex = Math.max(firstFilled, 0);
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
    // boost first, then cost among the REMAINING headers — "Boost Budget"
    // contains the cost word "budget" and must not become the cost column
    const cBoost = pickCol(headers, COL_BOOST);
    const cCost = headers.findIndex(
      (h, i) => i !== cBoost && Boolean(h) && COL_COST.some((k) => h.includes(k)),
    );
    // every KPI-ish column — sheets that split unit and number use two
    const kpiCols = headers.flatMap((h, i) => (h && COL_KPI.some((k) => h.includes(k)) ? [i] : []));

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
      const colRaw = cUser >= 0 ? text(row[cUser]) : '';
      // A picked column holding the row counter tells us nothing about the
      // account, so treat it as empty and let the links name the KOL instead.
      const colIsIndex = INDEX_LIKE.test(colRaw.replace(/^@/, ''));
      let colName = colIsIndex ? '' : colRaw.replace(/^@/, '');
      if (/https?:|\//.test(colName)) colName = handleFromUrl(colName);

      // Handle-like column text IS the username; free text is display-only.
      let username = /^[\w.]{2,}$/.test(colName) ? colName : '';

      // A row that names its account but whose links yield no handle (e.g. a
      // Facebook share short link) is kept under the written name rather than
      // silently dropped. Bounded so a sentence of free text can't become a
      // username.
      if (
        !username &&
        colName &&
        colName.length <= 40 &&
        colName.split(/\s+/).length <= 5 &&
        !HEADER_WORDS.has(colName.toLowerCase())
      ) {
        username = colName;
      }

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

      // Commercial columns, when the sheet has them. KPI cells are joined into
      // one string first, so "หน่วย: Views" + "จำนวน: 100,000" in two columns
      // parses the same as "100,000 Views" in one.
      const cost = cCost >= 0 ? parseAmount(text(row[cCost])) : null;
      const boost = cBoost >= 0 ? parseAmount(text(row[cBoost])) : null;
      const kpis = kpiCols.length ? parseKpis(kpiCols.map((i2) => text(row[i2])).join(' ')) : [];

      kols.push({
        username: username.toLowerCase(),
        display: (colIsIndex ? '' : colRaw) || username,
        group,
        subgroup: cSub >= 0 ? text(row[cSub]) : '',
        links: dedupeLinks(workUrls),
        followers,
        cost_thb: cost,
        boost_thb: boost,
        kpis,
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
