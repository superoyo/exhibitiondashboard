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

console.log('\n✅ all import-behaviour checks passed');
