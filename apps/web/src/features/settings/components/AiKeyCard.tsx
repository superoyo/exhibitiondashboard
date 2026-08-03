import { useState } from 'react';
import { anthropicKeyInputSchema } from '@kol/shared';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import { apiErrorMessage } from '@/lib/axios';
import { aiStateDisplay } from '@/features/settings/lib/aiState';
import {
  useAiKey,
  useAiStatus,
  useRecheckAiStatus,
  useSaveAiKey,
} from '@/features/settings/hooks/useSettings';

/**
 * Claude AI status + key management — powers the PPTX tie-in shot feature.
 */
export function AiKeyCard() {
  const { data: keyInfo } = useAiKey();
  const { data: status, isLoading: statusLoading } = useAiStatus();
  const recheck = useRecheckAiStatus();
  const save = useSaveAiKey();

  const [value, setValue] = useState('');
  const [saveMessage, setSaveMessage] = useState<{ text: string; color: string } | null>(null);

  const checking = statusLoading || recheck.isPending;
  const display = aiStateDisplay(status?.state);

  function handleSave() {
    const parsed = anthropicKeyInputSchema.safeParse({ token: value });
    if (!parsed.success) {
      setSaveMessage({
        text: value.trim() ? (parsed.error.issues[0]?.message ?? '') : 'วาง key ก่อน',
        color: '#dc2626',
      });
      return;
    }
    if (!window.confirm('บันทึก Claude API key ตัวนี้? ระบบจะทดสอบ key ให้ทันที')) return;

    setSaveMessage({ text: 'กำลังบันทึก+ทดสอบ…', color: '#64748b' });
    save.mutate(parsed.data.token, {
      onSuccess: (result) => {
        setValue('');
        setSaveMessage({
          text: result.check?.ok
            ? '✅ บันทึกแล้ว — key ใช้งานได้'
            : '✅ บันทึกแล้ว (ดูสถานะด้านบน)',
          color: '#059669',
        });
      },
      onError: (error) =>
        setSaveMessage({ text: `❌ ${apiErrorMessage(error)}`, color: '#dc2626' }),
    });
  }

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        <div className="mb-1 text-xs text-muted-foreground">
          🤖 Claude AI — ระบบหา Tie-in shot ใน PowerPoint
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <div
            className="text-lg font-semibold"
            style={{ color: checking ? '#64748b' : display.color }}
          >
            {checking ? '…' : display.label}
          </div>
          {keyInfo?.is_set && (
            <>
              <div className="font-mono text-sm text-muted-foreground">{keyInfo.masked}</div>
              <Badge variant="soft">
                {keyInfo.source === 'database' ? 'จาก: หน้านี้ (DB)' : 'จาก: Railway (env)'}
              </Badge>
            </>
          )}
          <Button variant="outline" onClick={() => recheck.mutate()} disabled={checking}>
            ตรวจสอบใหม่
          </Button>
        </div>

        <div className="mt-1 text-sm" style={{ color: checking ? '#64748b' : display.color }}>
          {checking
            ? 'กำลังตรวจสอบ…'
            : recheck.isError
              ? 'ตรวจสอบไม่สำเร็จ — ลองรีเฟรชหน้า'
              : (status?.message ?? '')}
        </div>

        <div className="mt-3 border-t border-border pt-3">
          <div className="mb-1 text-xs text-muted-foreground">
            ใส่/เปลี่ยน Claude API key (เอาจาก{' '}
            <a href="https://console.anthropic.com/settings/keys" target="_blank" rel="noreferrer">
              console.anthropic.com → API Keys
            </a>{' '}
            · บัญชีต้องมีเครดิตที่{' '}
            <a
              href="https://console.anthropic.com/settings/billing"
              target="_blank"
              rel="noreferrer"
            >
              Billing
            </a>
            )
          </div>
          <Textarea
            rows={2}
            placeholder="sk-ant-api03-..."
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-label="Claude API key ตัวใหม่"
          />
          <div className="mt-2 flex gap-2">
            <Button onClick={handleSave} disabled={save.isPending}>
              บันทึก Key
            </Button>
            {saveMessage && (
              <span className="self-center text-sm" style={{ color: saveMessage.color }}>
                {saveMessage.text}
              </span>
            )}
          </div>
        </div>

        <div className="mt-2 text-xs text-muted-foreground">
          ถ้าเครดิตหมด: เติมที่ Billing แล้วใช้ต่อได้ทันที ไม่ต้องเปลี่ยน key
        </div>
      </CardContent>
    </Card>
  );
}
