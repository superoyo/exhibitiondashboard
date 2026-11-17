import { useEffect, useState } from 'react';
import { apifyTokenInputSchema } from '@kol/shared';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { MASK_PLACEHOLDER } from '@/lib/format';
import { apiErrorMessage } from '@/lib/axios';
import {
  useApifyToken,
  useSaveApifyToken,
  useTestApifyToken,
} from '@/features/settings/hooks/useSettings';
import { KeyCardHeader } from './KeyCardHeader';

/**
 * APIFY Token — status and replacement in ONE card, the same shape as the
 * ANTHROPIC_API_KEY card below it. They used to be two cards with the Claude
 * card wedged between them, so the "change token" box read as belonging to
 * nothing in particular (team, 2026-11-17).
 *
 * The live test runs once on open: a dead token should be red the moment the
 * page loads, not after someone thinks to press "ทดสอบ" — the 2026-11-13
 * outage was only found because a Refresh failed.
 */
export function ApifyTokenCard() {
  const { data: info, isLoading, isError } = useApifyToken();
  const test = useTestApifyToken();
  const save = useSaveApifyToken();

  const [value, setValue] = useState('');
  const [saveMessage, setSaveMessage] = useState<{ text: string; color: string } | null>(null);

  // One automatic check per page open, once we know a token exists.
  const runTest = test.mutate;
  const tokenSet = Boolean(info?.is_set);
  useEffect(() => {
    if (tokenSet) runTest();
  }, [tokenSet, runTest]);

  /**
   * A failed load must not read as "no token set" — that would push someone
   * into re-entering a key that is actually fine.
   */
  const currentToken = isLoading
    ? MASK_PLACEHOLDER
    : isError
      ? 'โหลดไม่สำเร็จ'
      : info?.is_set
        ? info.masked
        : '(ยังไม่ได้ตั้ง)';

  const status = (() => {
    if (isLoading || test.isPending)
      return { label: '…', detail: 'กำลังตรวจสอบ…', color: '#64748b' };
    if (!isError && info && !info.is_set)
      return {
        label: '🔴 ยังไม่ได้ตั้ง token',
        detail: 'วาง token ด้านล่างแล้วกดบันทึก',
        color: '#dc2626',
      };
    if (test.isError)
      return {
        label: '⚠️ ตรวจสอบไม่ได้',
        detail: 'ทดสอบไม่สำเร็จ — ลองกดตรวจสอบใหม่',
        color: '#d97706',
      };
    if (!test.data) return { label: '…', detail: '', color: '#64748b' };
    if (test.data.ok) {
      const plan = test.data.plan ? ` · plan: ${test.data.plan}` : '';
      return {
        label: '🟢 พร้อมใช้งาน',
        detail: `บัญชี Apify: ${test.data.username || '-'}${plan}`,
        color: '#059669',
      };
    }
    return {
      label: '🔴 token ใช้ไม่ได้',
      detail: `${test.data.detail || 'Apify ไม่รับ token นี้'} — สร้าง token ใหม่แล้ววางด้านล่าง`,
      color: '#dc2626',
    };
  })();

  function handleSave() {
    const parsed = apifyTokenInputSchema.safeParse({ token: value });
    if (!parsed.success) {
      setSaveMessage({
        text: value.trim() ? (parsed.error.issues[0]?.message ?? '') : 'วาง token ก่อน',
        color: '#dc2626',
      });
      return;
    }
    if (!window.confirm('เปลี่ยน Apify token เป็นตัวใหม่? มีผลกับการดึงข้อมูลทันที')) return;

    save.mutate(parsed.data.token, {
      onSuccess: () => {
        setValue('');
        setSaveMessage({ text: '✅ บันทึกแล้ว', color: '#059669' });
        // Re-test straight away so the status line reflects the NEW token.
        runTest();
      },
      onError: (error) =>
        setSaveMessage({ text: `❌ ${apiErrorMessage(error)}`, color: '#dc2626' }),
    });
  }

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        <KeyCardHeader
          name="APIFY Token"
          what="— กุญแจที่ระบบใช้ไปดึงข้อมูลจาก TikTok / Facebook / Instagram / YouTube / X"
          uses={[
            '🔄 Refresh Data (ยอดโพสต์ + Followers + รูปโปรไฟล์)',
            '💬 Comment Analysis — ขั้นดึงคอมเมนต์',
            '📥 PowerPoint — ขั้นดึงคลิปมาหา Tie-in shot',
            '📈 Performance Analysis — ขั้นดึงฟอร์มช่อง',
          ]}
        />

        <div className="flex flex-wrap items-center gap-3">
          <div className="text-lg font-semibold" style={{ color: status.color }}>
            {status.label}
          </div>
          <div className="font-mono text-sm text-muted-foreground">{currentToken}</div>
          {info?.is_set && (
            <Badge variant="soft">
              {info.source === 'database' ? 'จาก: หน้านี้ (DB)' : 'จาก: ค่าเริ่มต้น (env)'}
            </Badge>
          )}
          <Button variant="outline" onClick={() => runTest()} disabled={test.isPending}>
            ตรวจสอบใหม่
          </Button>
        </div>
        <div className="mt-1 text-sm" style={{ color: status.color }}>
          {status.detail}
        </div>

        <div className="mt-3 border-t border-border pt-3">
          <div className="mb-1 text-xs text-muted-foreground">
            ใส่/เปลี่ยน Apify API token (เอาจาก{' '}
            <a
              href="https://console.apify.com/account/integrations"
              target="_blank"
              rel="noreferrer"
            >
              console.apify.com → Integrations
            </a>
            ) — มีผลกับการดึงข้อมูลทันที ไม่ต้อง deploy
          </div>
          <Textarea
            rows={2}
            placeholder="apify_api_..."
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-label="Apify API token ตัวใหม่"
          />
          <div className="mt-2 flex gap-2">
            <Button onClick={handleSave} disabled={save.isPending}>
              บันทึก Token
            </Button>
            {saveMessage && (
              <span className="self-center text-sm" style={{ color: saveMessage.color }}>
                {saveMessage.text}
              </span>
            )}
          </div>
        </div>

        <div className="mt-2 text-xs text-muted-foreground">
          ถ้าบัญชี Apify เครดิตหมด/โดนระงับ: จัดการที่ console.apify.com → Billing ก่อน token
          ใหม่อย่างเดียวจะยังใช้ไม่ได้
        </div>
      </CardContent>
    </Card>
  );
}
