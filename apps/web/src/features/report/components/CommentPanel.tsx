import type { CommentCategory, CommentPreviewItem, CommentSummary } from '@kol/shared';
import { useMemo, useState } from 'react';

import { getCommentExport } from '@/features/report/api/reportApi';
import { downloadCommentsExcel } from '@/features/report/lib/commentExcel';
import { useCommentList } from '@/features/report/hooks/useReport';
import { Button } from '@/components/ui/button';

import { EChart } from '@/components/common/EChart';
import { type EChartsOption } from '@/lib/echarts';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Fixed colour per topic so the same slice means the same thing in every
 * campaign — the whole reason the topic set is fixed rather than per-product.
 * The two "not about the product" buckets are deliberately grey: they are
 * usually the biggest slices and should not draw the eye away from the topics
 * a brand can act on.
 */
const CATEGORY_COLORS: Record<string, string> = {
  EFFECT: '#0ea5e9',
  SENSORY: '#8b5cf6',
  PRICE: '#f59e0b',
  WHERE: '#14b8a6',
  INTENT: '#10b981',
  QUESTION: '#6366f1',
  ISSUE: '#ef4444',
  OFFTOPIC: '#94a3b8',
  SPAM: '#cbd5e1',
};

/** Short chip labels. The donut legend carries the full ones from the server. */
const CHIP_LABELS: Record<string, string> = {
  EFFECT: '🧪 ผลลัพธ์',
  SENSORY: '👃 กลิ่น/รสชาติ',
  PRICE: '💰 ราคา',
  WHERE: '🛒 หาซื้อ',
  INTENT: '🙋 อยากซื้อ',
  QUESTION: '❓ ถามข้อมูล',
  ISSUE: '⚠️ ติดปัญหา',
};

function CategoryBreakdown({ data }: { data: CommentSummary }) {
  const slices = useMemo(() => data.categories.filter((c) => c.count > 0), [data.categories]);

  const option = useMemo<EChartsOption>(
    () => ({
      // Count only. The percentage lives in the list beside the chart and is
      // computed over ALL comments including unclassified ones, whereas
      // ECharts' own {d} is computed over the plotted slices — showing both
      // would put two different percentages for the same slice on screen.
      tooltip: { trigger: 'item', formatter: '{b}<br>{c} คอมเมนต์' },
      // ECharts' legend is off on purpose: with nine topics it falls back to a
      // paginated "1/2" strip that hides half the data behind an arrow. The
      // list beside the chart shows every topic at once, with counts.
      legend: { show: false },
      series: [
        {
          type: 'pie',
          radius: ['58%', '82%'],
          center: ['50%', '50%'],
          avoidLabelOverlap: true,
          label: { show: false },
          labelLine: { show: false },
          data: slices.map((c) => ({
            name: c.label,
            value: c.count,
            itemStyle: { color: CATEGORY_COLORS[c.code] },
          })),
        },
      ],
    }),
    [slices],
  );

  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
      <div className="relative w-full max-w-[240px] shrink-0">
        <EChart option={option} height={240} ariaLabel="สัดส่วนคอมเมนต์แยกตามเรื่องที่พูดถึง" />
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-3xl font-bold leading-none">{data.total.toLocaleString()}</div>
          <div className="mt-1 text-xs text-muted-foreground">คอมเมนต์</div>
        </div>
      </div>

      <ul className="w-full flex-1 space-y-1.5">
        {slices.map((c) => (
          <li key={c.code} className="flex items-center gap-2 text-sm">
            <span
              className="h-3 w-3 shrink-0 rounded-sm"
              style={{ backgroundColor: CATEGORY_COLORS[c.code] }}
            />
            <span className="min-w-0 flex-1 truncate">{c.label}</span>
            <span className="shrink-0 tabular-nums text-muted-foreground">
              {c.count.toLocaleString()}
            </span>
            <span className="w-14 shrink-0 text-right font-semibold tabular-nums">
              {c.pct.toFixed(1)}%
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function PreviewCard({ item }: { item: CommentPreviewItem }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="mb-2 min-w-0">
        <div className="truncate text-sm font-semibold">{item.author || 'ไม่ทราบชื่อ'}</div>
        {/* Whose post this sat under — a comment is meaningless without it */}
        <div className="truncate text-xs text-muted-foreground">
          {item.platform === 'tiktok' ? 'TikTok' : 'Facebook'} · โพสต์ของ{' '}
          {item.post_url ? (
            <a
              href={item.post_url}
              target="_blank"
              rel="noreferrer"
              className="underline hover:text-foreground"
            >
              @{item.kol} ↗
            </a>
          ) : (
            <>@{item.kol}</>
          )}
        </div>
      </div>
      <p className="whitespace-pre-wrap break-words text-sm">{item.text}</p>
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <span
          className="rounded px-1.5 py-0.5 text-[10px] font-semibold text-white"
          style={{ backgroundColor: CATEGORY_COLORS[item.category ?? ''] ?? '#94a3b8' }}
        >
          {item.label}
        </span>
        {item.theme ? <span>#{item.theme}</span> : null}
        <span>👍 {item.likes}</span>
      </div>
    </div>
  );
}

/** Fetches every comment and hands it to SheetJS. Own component so its pending
 *  state does not re-render the list beside it. */
function ExportButton({ campaign, campaignName }: { campaign: string; campaignName: string }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function run() {
    setBusy(true);
    setError('');
    try {
      const data = await getCommentExport(campaign);
      if (!data.rows.length) {
        setError('ยังไม่มีคอมเมนต์ให้ export');
        return;
      }
      await downloadCommentsExcel(data, campaignName || campaign);
      if (data.truncated) {
        setError(
          `ไฟล์มี ${data.rows.length.toLocaleString()} อันแรก จากทั้งหมด ${data.total.toLocaleString()}`,
        );
      }
    } catch {
      setError('export ไม่สำเร็จ ลองอีกครั้ง');
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="text-right">
      <Button variant="outline" size="sm" onClick={() => void run()} disabled={busy}>
        {busy ? 'กำลังสร้างไฟล์…' : '⬇️ Export Excel'}
      </Button>
      {error ? <div className="mt-1 text-[10px] text-amber-700">{error}</div> : null}
    </div>
  );
}

const PAGE_SIZE = 20;

/** Filter chips + one page of comments. Server-paged: see list_comments(). */
function CommentList({
  campaign,
  campaignName,
  data,
  viewToken,
}: {
  campaign: string;
  campaignName: string;
  data: CommentSummary;
  viewToken: string;
}) {
  const [category, setCategory] = useState<'' | CommentCategory>('');
  const [offset, setOffset] = useState(0);
  const list = useCommentList(campaign, category, offset, PAGE_SIZE, true, viewToken);

  function pick(next: '' | CommentCategory) {
    setCategory(next);
    setOffset(0); // page 3 of "all" is not page 3 of one topic
  }

  const chips: { key: '' | CommentCategory; label: string; count: number }[] = [
    { key: '', label: 'ทั้งหมด', count: data.product_total },
    ...data.by_topic.map((t) => ({
      key: t.code,
      label: CHIP_LABELS[t.code] ?? t.label,
      count: t.count,
    })),
  ];

  const total = list.data?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <Card className="lg:col-span-3">
      <CardContent className="p-4">
        <div className="mb-3 flex items-start justify-between gap-3">
          <div className="min-w-0">
            <h3 className="mb-1 font-semibold">ตัวอย่าง Comment</h3>
            <p className="text-xs text-muted-foreground">
              เรียงตามยอดไลก์ — ยอดไลก์คือการโหวตของคนดูเองว่าคอมเมนต์ไหนสำคัญ
            </p>
          </div>
          {/* Next to the comments it exports, but note the scope difference:
              this file holds EVERY comment, not the product-related page above.
              Internal only — a client link has no session to call it with, and
              the raw dump includes spam and off-topic chatter. */}
          {viewToken ? null : <ExportButton campaign={campaign} campaignName={campaignName} />}
        </div>

        <div className="mb-3 flex flex-wrap gap-1.5">
          {chips.map((c) => (
            <button
              key={c.key || 'all'}
              type="button"
              onClick={() => pick(c.key)}
              // count of 0 stays clickable rather than disabled: an empty
              // result is itself the answer ("nobody mentioned price at all")
              className={`rounded-full border px-3 py-1 text-xs font-semibold transition ${
                category === c.key ? 'border-transparent bg-slate-800 text-white' : 'hover:bg-muted'
              }`}
            >
              {c.label} <span className="tabular-nums opacity-70">{c.count}</span>
            </button>
          ))}
        </div>

        {list.isError ? (
          <div className="py-6 text-center text-sm text-destructive">โหลดคอมเมนต์ไม่สำเร็จ</div>
        ) : total === 0 ? (
          <div className="py-6 text-center text-sm text-muted-foreground">
            ไม่มีคอมเมนต์ในกลุ่มนี้
          </div>
        ) : (
          <>
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {(list.data?.items ?? []).map((item) => (
                <PreviewCard key={item.id} item={item} />
              ))}
            </div>

            <div className="mt-4 flex items-center justify-between gap-3">
              <span className="text-xs text-muted-foreground">
                {from}–{to} จาก {total.toLocaleString()}
                {list.isFetching ? ' · กำลังโหลด…' : ''}
              </span>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
                >
                  ← ก่อนหน้า
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  disabled={to >= total}
                  onClick={() => setOffset(offset + PAGE_SIZE)}
                >
                  ถัดไป →
                </Button>
              </div>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

export function CommentPanel({
  campaign,
  campaignName = '',
  data,
  /** Set on a public client link. Routes the reads through the token endpoints
   *  (no session exists) and hides the internal controls. */
  viewToken = '',
}: {
  campaign: string;
  campaignName?: string;
  data: CommentSummary;
  viewToken?: string;
}) {
  // Both empty states below tell the team which button to press. A client has no
  // such button and no reason to read about our pipeline, so on a client link the
  // section simply is not there — the same way the rest of the controls are not.
  const client = Boolean(viewToken);

  if (data.total === 0) {
    if (client) return null;
    return (
      <Card>
        <CardContent className="p-6 text-center text-sm text-muted-foreground">
          ยังไม่มีคอมเมนต์ที่เก็บไว้ — กดปุ่ม <strong>💬 Comment Analysis</strong> ด้านบนเพื่อเริ่ม
          <div className="mt-1 text-xs">
            ปุ่มนี้แยกจาก Refresh Data เพราะคิดเงินตามจำนวนคอมเมนต์
          </div>
        </CardContent>
      </Card>
    );
  }

  // Comments are stored but NONE carry a current label. The state a campaign
  // classified under the previous taxonomy lands in: without this it would draw
  // a donut of nine empty slices and an empty preview, which reads as a bug
  // rather than as "the rules changed, run it again".
  if (data.unclassified >= data.total) {
    if (client) return null;
    return (
      <Card>
        <CardContent className="p-6 text-center text-sm text-muted-foreground">
          เก็บคอมเมนต์ไว้ {data.total.toLocaleString()} อัน แต่ยังจัดประเภทตามเกณฑ์ใหม่ไม่ได้
          <div className="mt-1 text-xs">
            กด <strong>💬 Comment Analysis</strong> อีกครั้งเพื่อจัดประเภทใหม่ทั้งหมด
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <Card className="lg:col-span-2">
        <CardContent className="p-4">
          <h3 className="mb-1 font-semibold">คอมเมนต์พูดถึงเรื่องอะไร</h3>
          <p className="mb-2 text-xs text-muted-foreground">
            {Object.entries(data.by_platform)
              .map(([p, n]) => `${p === 'tiktok' ? 'TikTok' : 'Facebook'} ${n.toLocaleString()}`)
              .join(' · ')}
            {data.replies > 0 ? <span> · reply {data.replies.toLocaleString()}</span> : null}
            {/* Never hide this: percentages computed over a subset without
                saying so are the easiest number in a report to mislead with. */}
            {/* Shown to the client too, minus the instruction: percentages
                computed over a subset without saying so are the easiest number
                in a report to mislead with, and that is truer for the client's
                copy than for ours. */}
            {data.unclassified > 0 ? (
              <span className="text-amber-700">
                {' '}
                · ยังไม่จัดประเภท {data.unclassified.toLocaleString()}
                {client ? '' : ' (กด 💬 Comment Analysis เพื่อจัดต่อ)'}
              </span>
            ) : null}
          </p>
          <CategoryBreakdown data={data} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <h3 className="mb-1 font-semibold">Comment ที่เกี่ยวกับสินค้า</h3>
          <p className="mb-3 text-xs text-muted-foreground">
            เฉพาะคอมเมนต์ที่พูดถึงสินค้าจริง — ไม่รวมคอมเมนต์ที่ชมครีเอเตอร์เฉย ๆ และไม่รวมสแปม
            {/* Stated, not silently applied: excluding the creator's own words
                changes the denominator, and a reader comparing this to `total`
                deserves to know why the numbers differ. */}
            {data.creator_replies > 0 ? (
              <>
                {' '}
                รวมถึง reply ที่ KOL ตอบใต้โพสต์ตัวเอง {data.creator_replies.toLocaleString()} อัน
              </>
            ) : null}
          </p>

          <div className="mb-4 rounded-lg border p-3 text-center">
            <div className="text-3xl font-bold leading-none">
              {data.product_total.toLocaleString()}
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              จาก {data.total.toLocaleString()} คอมเมนต์
              {data.total ? ` · ${Math.round((100 * data.product_total) / data.total)}%` : ''}
            </div>
          </div>

          {data.themes.length > 0 ? (
            <>
              <h4 className="mb-2 text-sm font-semibold">พูดถึงแง่ไหนบ่อยที่สุด</h4>
              <div className="flex flex-wrap gap-1.5">
                {data.themes.map((t) => (
                  <span key={t.theme} className="rounded-full border px-2 py-0.5 text-xs">
                    {t.theme} <span className="text-muted-foreground">{t.count}</span>
                  </span>
                ))}
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>

      <CommentList
        campaign={campaign}
        campaignName={campaignName}
        data={data}
        viewToken={viewToken}
      />
    </div>
  );
}
