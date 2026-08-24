/**
 * Behaviour checks for the two import changes pulled in from main:
 *   4ac3f7a  skip sheets hidden inside the Excel file
 *   5be7ab0  never silently drop a row that names its account
 *
 * Kept in the repo (an earlier version of these checks lived in a temp dir and
 * was lost between sessions). Build the parser first:
 *
 *   node_modules/.bin/esbuild src/features/roster/lib/workbook.ts \
 *     --bundle --format=esm --external:xlsx --outfile=/tmp/workbook.mjs
 *   node scripts/workbook-import-checks.mjs /tmp/workbook.mjs
 */
import { strict as assert } from 'node:assert';
import * as XLSX from 'xlsx';

const bundle = process.argv[2];
if (!bundle) throw new Error('usage: node workbook-import-checks.mjs <bundled-workbook.mjs>');
const { parseWorkbook } = await import(bundle);

const parse = (wb) => parseWorkbook(XLSX, wb);

// ---- 4ac3f7a: a hidden sheet must not be imported -------------------------
{
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['username', 'ลิงก์'],
      ['livekol', 'https://www.tiktok.com/@livekol/video/7300000000000000001'],
    ]),
    'Live',
  );
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['username', 'ลิงก์'],
      ['oldkol', 'https://www.tiktok.com/@oldkol/video/7300000000000000002'],
    ]),
    'OldCampaign',
  );
  // Mark the second sheet hidden, the way a copied-from workbook would be.
  wb.Workbook = { Sheets: [{ name: 'Live' }, { name: 'OldCampaign', Hidden: 1 }] };

  const names = parse(wb).kols.map((k) => k.username);
  assert.deepEqual(names, ['livekol'], `hidden sheet leaked: ${JSON.stringify(names)}`);
  console.log('✅ hidden sheet skipped');
}

// ---- ...but if EVERY sheet is hidden, fall back to importing them ---------
{
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['username', 'ลิงก์'],
      ['onlykol', 'https://www.tiktok.com/@onlykol/video/7300000000000000003'],
    ]),
    'Only',
  );
  wb.Workbook = { Sheets: [{ name: 'Only', Hidden: 1 }] };

  assert.deepEqual(parse(wb).kols.map((k) => k.username), ['onlykol']);
  console.log('✅ all-hidden falls back to importing');
}

// ---- 5be7ab0: a named row whose links yield no handle is KEPT -------------
{
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['เพจ', 'ลิงก์'],
      // FB share short link: no handle derivable, but the row names its account
      ['MyFanPage', 'https://www.facebook.com/share/p/AbCdEf/'],
      // free text too long / too many words -> must NOT become a username
      ['this is a long sentence of free text that is not an account', 'https://www.facebook.com/share/p/ZzZz/'],
      // handle-like text is used as-is
      ['clean.handle', 'https://www.facebook.com/share/p/QqQq/'],
    ]),
    'Sheet1',
  );

  const names = parse(wb).kols.map((k) => k.username);
  assert.ok(names.includes('myfanpage'), `named row dropped: ${JSON.stringify(names)}`);
  assert.ok(names.includes('clean.handle'), `handle-like row missing: ${JSON.stringify(names)}`);
  assert.ok(
    !names.some((n) => n.includes('sentence')),
    `free text became a username: ${JSON.stringify(names)}`,
  );
  console.log('✅ named row kept; long free text rejected');
}

// ---- the new 'เพจ' / 'fanpage' / 'acc' column keys are recognised ---------
{
  for (const header of ['เพจ', 'fanpage', 'acc'] ) {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(
      wb,
      XLSX.utils.aoa_to_sheet([
        [header, 'ลิงก์'],
        ['namedacct', 'https://www.tiktok.com/@other/video/7300000000000000004'],
      ]),
      'Sheet1',
    );
    const kols = parse(wb).kols;
    assert.equal(kols[0].username, 'namedacct', `column '${header}' not used as username source`);
  }
  console.log("✅ 'เพจ' / 'fanpage' / 'acc' recognised as account columns");
}

// ---- a row counter must never become the username -------------------------
// Zilk Ultra Soft (P2026-096) imported as @1..@5: a merged title row was read as
// the header, so every column key matched column A — the row counter.
{
  const posts = [
    'https://www.tiktok.com/@mypaintingg/video/7677717482460290104',
    'https://www.tiktok.com/@somm.ooo/video/7673398770523907334',
    'https://www.tiktok.com/@ying_pacharaporn/video/7672660851201716073',
  ];
  const expected = ['mypaintingg', 'somm.ooo', 'ying_pacharaporn'];

  const sheets = {
    'merged title row above the real header': [
      ['รายชื่อ KOL Zilk Ultra Soft', '', ''],
      ['ลำดับ', 'ชื่อ', 'ลิงก์โพสต์'],
      ...posts.map((u, i) => [i + 1, '', u]),
    ],
    'counter column named like an account column': [
      ['KOL No.', 'ลิงก์โพสต์'],
      ...posts.map((u, i) => [i + 1, u]),
    ],
    'counter styled 1. / #2 / 3)': [
      ['ลำดับ KOL', 'ลิงก์โพสต์'],
      ['1.', posts[0]],
      ['#2', posts[1]],
      ['3)', posts[2]],
    ],
  };

  for (const [what, aoa] of Object.entries(sheets)) {
    const wb = XLSX.utils.book_new();
    XLSX.utils.book_append_sheet(wb, XLSX.utils.aoa_to_sheet(aoa), 'Sheet1');
    const kols = parse(wb).kols;
    assert.deepEqual(
      kols.map((k) => k.username),
      expected,
      `${what}: usernames not taken from the post links`,
    );
    assert.ok(
      !kols.some((k) => /^\d+$/.test(k.display)),
      `${what}: a row number became the display name`,
    );
  }
  console.log('✅ row counters never become usernames');
}

// ---- a genuinely numeric account (FB numeric page) still survives ----------
{
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['username', 'ลิงก์'],
      ['100063588291234', 'https://www.facebook.com/share/p/AbCdEf/'],
    ]),
    'Sheet1',
  );
  assert.deepEqual(parse(wb).kols.map((k) => k.username), ['100063588291234']);
  console.log('✅ numeric Facebook page id still accepted');
}

// ---- a profile link names the KOL even when the row has post links ---------
{
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['ลำดับ', 'ลิงก์บัญชี', 'ลิงก์โพสต์'],
      [
        1,
        'https://www.tiktok.com/@realhandle',
        'https://www.tiktok.com/@shared.repost/video/7300000000000000009',
      ],
    ]),
    'Sheet1',
  );
  const kols = parse(wb).kols;
  assert.equal(kols[0].username, 'realhandle', 'profile link should win over the post link');
  console.log('✅ account link preferred over post link for the username');
}

// ---- planner commercial columns: cost / boost / KPI ------------------------
{
  // one-column KPI: unit word and number share a cell
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['username', 'ลิงก์', 'ค่าตัว', 'Boost Budget', 'KPI'],
      ['kolview', 'https://www.tiktok.com/@kolview/video/7300000000000000021', '฿12,500.50', '3,000', '100K Views'],
      ['kolimp', 'https://www.tiktok.com/@kolimp/video/7300000000000000022', '45,000', '', 'Imp 500,000'],
      ['kolint', 'https://www.tiktok.com/@kolint/video/7300000000000000023', '', '1.5k', 'Interaction: 5,000'],
      ['kolnone', 'https://www.tiktok.com/@kolnone/video/7300000000000000024', '', '', ''],
    ]),
    'Sheet1',
  );
  const got = Object.fromEntries(parse(wb).kols.map((k) => [k.username, k]));
  assert.equal(got.kolview.cost_thb, 12500.5, 'baht sign + comma + decimals');
  assert.equal(got.kolview.boost_thb, 3000, '"Boost Budget" is boost, not cost');
  assert.deepEqual(
    [got.kolview.kpi_metric, got.kolview.kpi_target],
    ['views', 100000],
    `100K Views: ${got.kolview.kpi_metric} ${got.kolview.kpi_target}`,
  );
  assert.deepEqual([got.kolimp.kpi_metric, got.kolimp.kpi_target], ['impressions', 500000]);
  assert.equal(got.kolint.boost_thb, 1500, '1.5k boost');
  assert.deepEqual([got.kolint.kpi_metric, got.kolint.kpi_target], ['interaction', 5000]);
  assert.equal(got.kolnone.cost_thb, null, 'empty cells stay null');
  assert.equal(got.kolnone.kpi_target, null, 'no KPI stays null');
  console.log('✅ cost / boost / one-column KPI parsed');
}

{
  // two-column KPI: unit in one column, number in the next
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['username', 'ลิงก์', 'KPI หน่วยวัด', 'KPI จำนวน'],
      ['splitkol', 'https://www.tiktok.com/@splitkol/video/7300000000000000025', 'Views', '250,000'],
    ]),
    'Sheet1',
  );
  const k = parse(wb).kols[0];
  assert.deepEqual(
    [k.kpi_metric, k.kpi_target],
    ['views', 250000],
    `split KPI columns: ${k.kpi_metric} ${k.kpi_target}`,
  );
  console.log('✅ two-column KPI (หน่วย + จำนวน) parsed');
}

{
  // a sheet WITHOUT commercial columns must not invent values
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['username', 'ลิงก์'],
      ['plainkol', 'https://www.tiktok.com/@plainkol/video/7300000000000000026'],
    ]),
    'Sheet1',
  );
  const k = parse(wb).kols[0];
  assert.equal(k.cost_thb, null);
  assert.equal(k.boost_thb, null);
  assert.equal(k.kpi_metric, null);
  console.log('✅ sheets without planner columns stay clean');
}

console.log('\n✅ all import-behaviour checks passed');
