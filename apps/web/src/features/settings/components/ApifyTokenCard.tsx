import { useState } from 'react';
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

/** Current token + live test. */
export function ApifyTokenCard() {
  const { data: info, isLoading, isError } = useApifyToken();
  const test = useTestApifyToken();

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

  const testMessage = (() => {
    if (test.isPending) return { text: 'กำลังทดสอบ…', color: '#64748b' };
    if (test.isError) return { text: '❌ ทดสอบไม่สำเร็จ', color: '#dc2626' };
    if (!test.data) return null;
    if (test.data.ok) {
      const plan = test.data.plan ? `, plan: ${test.data.plan}` : '';
      return { text: `✅ ใช้ได้ (user: ${test.data.username || '-'}${plan})`, color: '#059669' };
    }
    return { text: `❌ ${test.data.detail || 'ใช้ไม่ได้'}`, color: '#dc2626' };
  })();

  return (
    <Card className="mb-4">
      <CardContent className="p-4">
        <div className="mb-1 text-xs text-muted-foreground">Token ปัจจุบัน</div>
        <div className="flex flex-wrap items-center gap-3">
          <div className="font-mono text-lg font-semibold">{currentToken}</div>
          {info && (
            <Badge variant="soft">
              {info.source === 'database' ? 'จาก: หน้านี้ (DB)' : 'จาก: ค่าเริ่มต้น (env)'}
            </Badge>
          )}
          <Button variant="outline" onClick={() => test.mutate()} disabled={test.isPending}>
            ทดสอบ token
          </Button>
          {testMessage && (
            <span className="text-sm" style={{ color: testMessage.color }}>
              {testMessage.text}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

/** Replace the token — takes effect immediately, no redeploy. */
export function ApifyTokenForm() {
  const save = useSaveApifyToken();
  const [value, setValue] = useState('');
  const [message, setMessage] = useState<{ text: string; color: string } | null>(null);

  function handleSave() {
    const parsed = apifyTokenInputSchema.safeParse({ token: value });
    if (!parsed.success) {
      setMessage({
        text: value.trim() ? (parsed.error.issues[0]?.message ?? '') : 'วาง token ก่อน',
        color: '#dc2626',
      });
      return;
    }
    if (!window.confirm('เปลี่ยน Apify token เป็นตัวใหม่? มีผลกับการดึงข้อมูลทันที')) return;

    save.mutate(parsed.data.token, {
      onSuccess: () => {
        setValue('');
        setMessage({ text: '✅ บันทึกแล้ว', color: '#059669' });
      },
      onError: (error) => setMessage({ text: `❌ ${apiErrorMessage(error)}`, color: '#dc2626' }),
    });
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="mb-2 text-sm font-semibold">เปลี่ยน Token</div>
        <p className="mb-2 text-xs text-muted-foreground">
          วาง Apify API token ตัวใหม่ (เอาจาก{' '}
          <a href="https://console.apify.com/account/integrations" target="_blank" rel="noreferrer">
            console.apify.com → Integrations
          </a>
          ) แล้วกดบันทึก — มีผลกับการดึงข้อมูลทันที ไม่ต้อง deploy
        </p>
        <Textarea
          rows={2}
          placeholder="apify_api_..."
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="Apify API token ตัวใหม่"
        />
        <div className="mt-3 flex gap-2">
          <Button onClick={handleSave} disabled={save.isPending}>
            บันทึก Token
          </Button>
          {message && (
            <span className="self-center text-sm" style={{ color: message.color }}>
              {message.text}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
