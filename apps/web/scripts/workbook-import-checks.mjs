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
  // ...and the profile link is KEPT (after the work link), so the report can
  // link the name to the channel. It costs nothing — refresh never scrapes it.
  assert.equal(kols[0].links.length, 2, 'both links kept');
  assert.ok(
    kols[0].links[0].url.includes('/video/'),
    'work link stays first (it remains the primary)',
  );
  assert.ok(
    kols[0].links.some((l) => l.url === 'https://www.tiktok.com/@realhandle'),
    'profile link kept for the clickable name');
  console.log('✅ account link preferred over post link for the username (and kept)');
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
    got.kolview.kpis,
    [{ metric: 'views', target: 100000 }],
    `100K Views: ${JSON.stringify(got.kolview.kpis)}`,
  );
  assert.deepEqual(got.kolimp.kpis, [{ metric: 'impressions', target: 500000 }]);
  assert.equal(got.kolint.boost_thb, 1500, '1.5k boost');
  assert.deepEqual(got.kolint.kpis, [{ metric: 'interaction', target: 5000 }]);
  assert.equal(got.kolnone.cost_thb, null, 'empty cells stay null');
  assert.deepEqual(got.kolnone.kpis, [], 'no KPI stays empty');
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
    k.kpis,
    [{ metric: 'views', target: 250000 }],
    `split KPI columns: ${JSON.stringify(k.kpis)}`,
  );
  console.log('✅ two-column KPI (หน่วย + จำนวน) parsed');
}

// ---- multi-KPI cells and the Reach unit -------------------------------------
{
  const wb = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(
    wb,
    XLSX.utils.aoa_to_sheet([
      ['username', 'ลิงก์', 'KPI'],
      // one KOL sold on TWO KPIs in one cell
      ['dualkol', 'https://www.tiktok.com/@dualkol/video/7300000000000000031', '100,000 Views + 5,000 Engagement'],
      // Facebook page sold on Reach — the unit the first version did not know
      ['reachkol', 'https://www.facebook.com/reachkol/posts/123', 'Reach 500,000'],
      // slash-separated pair with thousands commas intact
      ['slashkol', 'https://www.tiktok.com/@slashkol/video/7300000000000000032', 'View 250,000 / Imp 1,000,000'],
    ]),
    'Sheet1',
  );
  const got = Object.fromEntries(parse(wb).kols.map((k) => [k.username, k]));
  assert.deepEqual(
    got.dualkol.kpis,
    [
      { metric: 'views', target: 100000 },
      { metric: 'interaction', target: 5000 },
    ],
    `dual KPI: ${JSON.stringify(got.dualkol.kpis)}`,
  );
  assert.deepEqual(
    got.reachkol.kpis,
    [{ metric: 'reach', target: 500000 }],
    `reach: ${JSON.stringify(got.reachkol.kpis)}`,
  );
  assert.deepEqual(
    got.slashkol.kpis,
    [
      { metric: 'views', target: 250000 },
      { metric: 'impressions', target: 1000000 },
    ],
    `slash pair keeps its thousands commas: ${JSON.stringify(got.slashkol.kpis)}`,
  );
  console.log('✅ multi-KPI cells and Reach parsed');
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
  assert.deepEqual(k.kpis, []);
  console.log('✅ sheets without planner columns stay clean');
}

// ---- merged cells: how planner sheets actually carry group data -------------
// Excel keeps a merged range's value in the top-left cell only. Pao Win Wash
// showed the failure: the Micro package's "7M Imp" KPI merged across the group
// landed on the first member as a PERSONAL target; merged boost cells lost
// their value for every row but the first.
{
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet([
    ['username', 'ลิงก์', 'ค่าตัว', 'Boost', 'KPI'],
    // Macro: own KPI per row, boost merged across the two rows (rows 1-2)
    ['macro1', 'https://www.tiktok.com/@macro1/video/7300000000000000041', '55,500', '20,000', '800K Reach'],
    ['macro2', 'https://www.tiktok.com/@macro2/video/7300000000000000042', '47,100', '', '800K Reach'],
    // Micro package: cost AND KPI merged across the whole group (rows 3-5) —
    // the Pao Win Wash shape: one pack budget, one pack target.
    ['micro1', 'https://www.tiktok.com/@micro1/video/7300000000000000043', '245,000', '', '7M Imp'],
    ['micro2', 'https://www.tiktok.com/@micro2/video/7300000000000000044', '', '', ''],
    ['micro3', 'https://www.tiktok.com/@micro3/video/7300000000000000045', '', '', ''],
  ]);
  ws['!merges'] = [
    { s: { r: 1, c: 3 }, e: { r: 2, c: 3 } }, // boost D2:D3 (vertical)
    { s: { r: 3, c: 2 }, e: { r: 5, c: 2 } }, // cost C4:C6 (vertical, whole pack)
    { s: { r: 3, c: 4 }, e: { r: 5, c: 4 } }, // KPI E4:E6 (vertical, whole group)
  ];
  // groups via section headers are absent here — single sheet, no group column,
  // so everyone lands in 'KOL'; the merged KPI becomes THAT group's total.
  XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');

  const parsed = parse(wb);
  const got = Object.fromEntries(parsed.kols.map((k) => [k.username, k]));
  // Merged money is the range's TOTAL, split evenly — ฿245,000 over a
  // 10-person pack is not ฿245,000 per head (Pao Win Wash, 2026-09-02).
  assert.equal(got.macro1.boost_thb, 10000, 'merged boost splits: 20,000 over 2 = 10,000');
  assert.equal(got.macro2.boost_thb, 10000, 'merged boost splits on every row');
  assert.equal(got.macro1.cost_thb, 55500, 'per-row cost stays personal');
  for (const u of ['micro1', 'micro2', 'micro3']) {
    assert.equal(
      got[u].cost_thb,
      81666.67,
      `${u} gets the pack cost divided: ${got[u].cost_thb}`,
    );
  }
  assert.deepEqual(
    got.macro1.kpis,
    [{ metric: 'reach', target: 800000 }],
    'per-row KPI stays personal and undivided',
  );
  // Team decision: a KPI merged across N rows is a shared total, split evenly —
  // 7,000,000 imp over 3 people = 2,333,333 each.
  for (const u of ['micro1', 'micro2', 'micro3']) {
    assert.deepEqual(
      got[u].kpis,
      [{ metric: 'impressions', target: 2333333 }],
      `${u} gets the divided share: ${JSON.stringify(got[u].kpis)}`,
    );
  }
  console.log('✅ vertical merges spread; shared KPI and shared money split per person');
}

// ---- a REAL merged title row must still not become the header ---------------
{
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet([
    ['รายชื่อ KOL Pao Win Wash', '', ''],
    ['ลำดับ', 'ชื่อ', 'ลิงก์โพสต์'],
    [1, '', 'https://www.tiktok.com/@merged.title/video/7300000000000000046'],
  ]);
  ws['!merges'] = [{ s: { r: 0, c: 0 }, e: { r: 0, c: 2 } }]; // horizontal title merge
  XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');
  const kols = parse(wb).kols;
  assert.deepEqual(
    kols.map((k) => k.username),
    ['merged.title'],
    `horizontal merge leaked into the header: ${JSON.stringify(kols.map((k) => k.username))}`,
  );
  console.log('✅ horizontal title merges stay inert');
}

// ---- the Proof-sheet shape: decorative 2-cell row above the real header -----
// The real Pao Win Wash "Micro Package (Proof)" sheet opens with
// " Tiktok Micro Influencer..." + "เลือก 10 Account" — two filled cells. Header
// detection by cell COUNT took that as the header and lost every column.
{
  const wb = XLSX.utils.book_new();
  const ws = XLSX.utils.aoa_to_sheet([
    [' Tiktok Micro Influencer จำนวน 10 คน', '', '', 'เลือก 10 Account ', ''],
    ['No', 'name', 'Link', 'sow', 'Boost Budget', 'Kpi', 'Period '],
    ['1', '', 'https://www.tiktok.com/@proof1', 'SOW : Tiktok Content', '24500', '7,000,000 imp.', 'W1-W3 Oct'],
    ['2', '', 'https://www.tiktok.com/@proof2', 'SOW : Tiktok Content', '24500', '', 'W1-W3 Oct'],
  ]);
  ws['!merges'] = [
    { s: { r: 0, c: 0 }, e: { r: 0, c: 2 } }, // decorative banner (horizontal)
    { s: { r: 2, c: 5 }, e: { r: 3, c: 5 } }, // Kpi merged down the group
  ];
  XLSX.utils.book_append_sheet(wb, ws, 'Micro Package (Proof) ');
  const got = Object.fromEntries(parse(wb).kols.map((k) => [k.username, k]));
  assert.deepEqual(Object.keys(got).sort(), ['proof1', 'proof2'], 'both rows imported');
  assert.equal(got.proof1.boost_thb, 24500, 'Boost Budget column found despite the banner row');
  assert.equal(got.proof2.boost_thb, 24500, 'boost on every row');
  for (const u of ['proof1', 'proof2']) {
    assert.deepEqual(
      got[u].kpis,
      [{ metric: 'impressions', target: 3500000 }],
      `${u}: shared 7M split by 2 = 3.5M each`,
    );
  }
  console.log('✅ Proof-sheet banner row no longer eats the header');
}

console.log('\n✅ all import-behaviour checks passed');
