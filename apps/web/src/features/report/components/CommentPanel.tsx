import type { CommentPreviewItem, CommentSummary } from '@kol/shared';
import { useMemo } from 'react';

import { EChart } from '@/components/common/EChart';
import { type EChartsOption } from '@/lib/echarts';
import { Card, CardContent } from '@/components/ui/card';

/**
 * Fixed colour per category so the same slice means the same thing in every
 * campaign — the whole reason the category set is fixed rather than
 * per-product. Negative is the one that must never blend in.
 */
const CATEGORY_COLORS: Record<string, string> = {
  FAN: '#8b5cf6',
  PRODUCT: '#0ea5e9',
  INTENT: '#10b981',
  ECHO: '#f59e0b',
  NEG: '#ef4444',
  QUESTION: '#64748b',
  SPAM: '#94a3b8',
};

const SENTIMENT_LABELS: Record<string, string> = {
  pos: 'บวก',
  neu: 'กลาง',
  neg: 'ลบ',
};

const SENTIMENT_CLASSES: Record<string, string> = {
  pos: 'bg-emerald-100 text-emerald-800',
  neu: 'bg-slate-100 text-slate-700',
  neg: 'bg-red-100 text-red-800',
};

function CategoryDonut({ data }: { data: CommentSummary }) {
  const option = useMemo<EChartsOption>(() => {
    const slices = data.categories.filter((c) => c.count > 0);
    return {
      tooltip: { trigger: 'item', formatter: '{b}<br>{c} คอมเมนต์ ({d}%)' },
      legend: { type: 'scroll', bottom: 0, textStyle: { fontSize: 11 } },
      series: [
        {
          type: 'pie',
          radius: ['45%', '70%'],
          center: ['50%', '45%'],
          avoidLabelOverlap: true,
          label: { show: false },
          data: slices.map((c) => ({
            name: c.label,
            value: c.count,
            itemStyle: { color: CATEGORY_COLORS[c.code] },
          })),
        },
      ],
    };
  }, [data]);

  return <EChart option={option} height={300} ariaLabel="สัดส่วนคอมเมนต์แยกตามประเภท" />;
}

function PreviewCard({ item }: { item: CommentPreviewItem }) {
  return (
    <div className="rounded-lg border p-3">
      <div className="mb-2 flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold">{item.author || 'ไม่ทราบชื่อ'}</div>
          {/* Whose post this sat under — a comment is meaningless without it */}
          <div className="truncate text-xs text-muted-foreground">
            {item.platform === 'tiktok' ? 'TikTok' : 'Facebook'} · โพสต์ของ @{item.kol}
          </div>
        </div>
        {item.sentiment ? (
          <span
            className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold ${
              SENTIMENT_CLASSES[item.sentiment] ?? ''
            }`}
          >
            {SENTIMENT_LABELS[item.sentiment]}
          </span>
        ) : null}
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

export function CommentPanel({ data }: { data: CommentSummary }) {
  const sentiment = data.product_sentiment;
  const productTotal = (sentiment.pos ?? 0) + (sentiment.neu ?? 0) + (sentiment.neg ?? 0);

  if (data.total === 0) {
    return (
      <Card>
        <CardContent className="p-6 text-center text-sm text-muted-foreground">
          ยังไม่มีคอมเมนต์ที่เก็บไว้ — กดปุ่ม <strong>ดึงคอมเมนต์</strong> ด้านบนเพื่อเริ่ม
          <div className="mt-1 text-xs">
            ปุ่มนี้แยกจาก Refresh Data เพราะคิดเงินตามจำนวนคอมเมนต์
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardContent className="p-4">
          <h3 className="mb-1 font-semibold">สัดส่วนคอมเมนต์แยกตามประเภท</h3>
          <p className="mb-2 text-xs text-muted-foreground">
            {data.total.toLocaleString()} คอมเมนต์
            {Object.entries(data.by_platform).map(([p, n]) => (
              <span key={p}> · {p === 'tiktok' ? 'TikTok' : 'Facebook'} {n.toLocaleString()}</span>
            ))}
            {/* Never hide this: percentages computed over a subset without
                saying so are the easiest number in a report to mislead with. */}
            {data.unclassified > 0 ? (
              <span className="text-amber-700"> · ยังไม่จัดประเภท {data.unclassified}</span>
            ) : null}
          </p>
          <CategoryDonut data={data} />
        </CardContent>
      </Card>

      <Card>
        <CardContent className="p-4">
          <h3 className="mb-1 font-semibold">เสียงต่อสินค้า</h3>
          <p className="mb-3 text-xs text-muted-foreground">
            เฉพาะคอมเมนต์ที่พูดถึงสินค้าจริง ({productTotal.toLocaleString()} อัน) — ไม่รวมคอมเมนต์
            ที่ชมครีเอเตอร์เฉย ๆ
          </p>
          <div className="mb-4 grid grid-cols-3 gap-2 text-center">
            {(['pos', 'neu', 'neg'] as const).map((s) => (
              <div key={s} className="rounded-lg border p-3">
                <div className="text-2xl font-bold">{sentiment[s] ?? 0}</div>
                <div className="text-xs text-muted-foreground">{SENTIMENT_LABELS[s]}</div>
                <div className="text-xs text-muted-foreground">
                  {productTotal ? Math.round((100 * (sentiment[s] ?? 0)) / productTotal) : 0}%
                </div>
              </div>
            ))}
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

      <Card className="lg:col-span-2">
        <CardContent className="p-4">
          <h3 className="mb-1 font-semibold">คอมเมนต์ที่เกี่ยวกับสินค้า</h3>
          <p className="mb-3 text-xs text-muted-foreground">
            เรียงตามยอดไลก์ — ยอดไลก์คือการโหวตของคนดูเองว่าคอมเมนต์ไหนสำคัญ
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {data.preview.map((item) => (
              <PreviewCard key={item.id} item={item} />
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
