import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

interface ImportCardProps {
  /** Sheet URL already linked to this campaign, if any. */
  linkedUrl: string;
  busy: boolean;
  status: string;
  onImportFile: (file: File) => void;
  onImportUrl: (url: string) => void;
}

/**
 * Bulk import — "แทนที่ทั้งหมด". Two entry points (file upload, online link)
 * plus a re-sync shortcut once a campaign has a linked file.
 */
export function ImportCard({
  linkedUrl,
  busy,
  status,
  onImportFile,
  onImportUrl,
}: ImportCardProps) {
  const [url, setUrl] = useState(linkedUrl);
  const fileRef = useRef<HTMLInputElement>(null);

  // Populate the field once the linked URL arrives from the server.
  useEffect(() => {
    if (linkedUrl) setUrl(linkedUrl);
  }, [linkedUrl]);

  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) onImportFile(file);
    // Reset so re-picking the same file fires change again.
    e.target.value = '';
  }

  function handleSync() {
    if (
      window.confirm(
        'ดึงรายชื่อ+ลิงก์จาก Google Sheet ที่เชื่อมไว้ใหม่ (แทนที่รายชื่อเดิมทั้งหมด)?',
      )
    ) {
      onImportUrl(url.trim());
    }
  }

  return (
    <Card className="mb-4">
      <CardContent className="p-3">
        <div className="mb-1 text-sm font-semibold">📥 นำเข้ารายชื่อ KOL (แทนที่ทั้งหมด)</div>
        <p className="mb-3 text-xs text-muted-foreground">
          ระบบจะวิเคราะห์หมวดหมู่ให้อัตโนมัติ — จากชื่อ <b>Sheet</b> (ถ้ามีหลายชีต) หรือคอลัมน์{' '}
          <b>หมวด/ประเภท/group</b> · คอลัมน์ที่รองรับ: username/ชื่อ · ลิงก์โพสต์ · หมวด · กลุ่มย่อย
          · followers · <b>⚠️ การนำเข้าจะลบรายชื่อเดิมทั้งหมดแล้วแทนที่</b>
        </p>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <div>
            <div className="mb-1 text-xs font-semibold">แบบที่ 1 · อัปโหลดไฟล์ Excel / CSV</div>
            <input
              ref={fileRef}
              type="file"
              accept=".xlsx,.xls,.csv"
              disabled={busy}
              onChange={handleFile}
              aria-label="อัปโหลดไฟล์ Excel หรือ CSV"
              className="w-full rounded-lg border border-border bg-white px-2.5 py-1.5 text-[0.85rem] file:mr-2 file:rounded file:border-0 file:bg-slate-100 file:px-2 file:py-1 file:text-xs"
            />
          </div>

          <div>
            <div className="mb-1 text-xs font-semibold">
              แบบที่ 2 · ลิงก์ไฟล์ออนไลน์ (Google Sheet / Drive / OneDrive / Dropbox)
            </div>
            <div className="flex gap-2">
              <Input
                className="h-9 text-[0.85rem]"
                placeholder="วางลิงก์ Google Sheet / Drive / OneDrive / Dropbox…"
                aria-label="ลิงก์ไฟล์ออนไลน์"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <Button
                className="whitespace-nowrap"
                disabled={busy}
                onClick={() => onImportUrl(url.trim())}
              >
                นำเข้า
              </Button>
            </div>
            <div className="mt-1 text-xs text-muted-foreground">
              รองรับลิงก์ที่ตั้งแชร์เป็น &quot;ใครก็ตามที่มีลิงก์ (ผู้อ่าน)&quot;
            </div>
            {linkedUrl && (
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                🔗 เชื่อมกับไฟล์ออนไลน์นี้แล้ว —
                <Button
                  variant="outline"
                  size="sm"
                  className="h-auto px-2 py-0.5 text-xs"
                  disabled={busy}
                  onClick={handleSync}
                >
                  🔄 ดึงรายชื่อจากไฟล์ใหม่
                </Button>
              </div>
            )}
          </div>
        </div>

        {status && (
          <div className="mt-2 text-xs text-muted-foreground" aria-live="polite">
            {status}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
