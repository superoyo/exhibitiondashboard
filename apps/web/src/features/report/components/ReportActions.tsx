import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { routes } from '@/config/routes';
import { apiErrorMessage } from '@/lib/axios';
import { getViewToken } from '@/features/campaigns/api/campaignsApi';
import { usePptxExport } from '@/features/report/hooks/usePptxExport';
import { REFRESH_CONFIRM, useRefreshFlow } from '@/features/report/hooks/useRefreshFlow';
import { usePackshot, useSavePackshot } from '@/features/report/hooks/useReport';

/** Max pack-shot upload, matching the server-side limit. */
const MAX_PACKSHOT_BYTES = 8 * 1024 * 1024;

/** Readable campaign slug for the client link; the token is what grants access. */
function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 40);
}

interface ReportActionsProps {
  campaign: string;
  campaignName: string;
  /** True while a refresh job is running (drives the button's spinner). */
  refreshing: boolean;
  onStatus: (message: string) => void;
}

export function ReportActions({
  campaign,
  campaignName,
  refreshing,
  onStatus,
}: ReportActionsProps) {
  const fileRef = useRef<HTMLInputElement>(null);

  const packshot = usePackshot(campaign, true);
  const savePackshot = useSavePackshot(campaign);
  const pptx = usePptxExport(campaign);
  const refresh = useRefreshFlow(campaign);
  const [uploading, setUploading] = useState(false);

  const packSet = packshot.data?.is_set ?? false;

  function handlePackClick() {
    if (packSet && !window.confirm('มีภาพสินค้าอยู่แล้ว ต้องการเปลี่ยนเป็นภาพใหม่?')) return;
    if (fileRef.current) {
      fileRef.current.value = '';
      fileRef.current.click();
    }
  }

  function handlePackFile(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_PACKSHOT_BYTES) {
      window.alert('ไฟล์ใหญ่เกิน 8MB — ย่อรูปก่อนครับ');
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      // readAsDataURL always yields a string; guard rather than stringify a
      // possible ArrayBuffer into "[object ArrayBuffer]".
      const dataUri = typeof reader.result === 'string' ? reader.result : '';
      if (!dataUri) {
        window.alert('อ่านไฟล์ภาพไม่สำเร็จ');
        return;
      }
      setUploading(true);
      savePackshot.mutate(dataUri, {
        onSuccess: (result) => {
          onStatus(
            '✅ บันทึกภาพสินค้าแล้ว — กด PowerPoint เพื่อให้ AI หา tie-in shot โดยเทียบกับภาพนี้' +
              (result.unlocked
                ? ` (ปลดล็อก ${result.unlocked} คลิปที่เคยหาไม่เจอ ให้ลองใหม่)`
                : ''),
          );
        },
        onError: (error) => window.alert(`อัพโหลดไม่สำเร็จ: ${apiErrorMessage(error)}`),
        onSettled: () => setUploading(false),
      });
    };
    reader.readAsDataURL(file);
  }

  async function handleShare() {
    try {
      const { token } = await getViewToken(campaign);
      if (!token) throw new Error('ขอลิงก์ไม่สำเร็จ');
      const slug = slugify(campaignName) || campaign;
      const link = `${window.location.origin}/v/${slug}/${token}`;
      try {
        await navigator.clipboard.writeText(link);
        onStatus(`✅ คัดลอกลิงก์สำหรับลูกค้าแล้ว — ${link}`);
      } catch {
        // Clipboard blocked (insecure context / permission) — show it instead so
        // the link is never simply lost.
        window.prompt('คัดลอกลิงก์นี้ส่งให้ลูกค้า (ดูได้อย่างเดียว):', link);
      }
    } catch (error) {
      onStatus(`⚠️ ${apiErrorMessage(error)}`);
    }
  }

  function handleRefresh() {
    if (!window.confirm(REFRESH_CONFIRM)) return;
    void refresh.run(onStatus, (msg) => window.alert(msg));
  }

  const busy = refreshing || refresh.starting;

  return (
    <div className="flex flex-wrap gap-2">
      <Button asChild className="rounded-[10px] bg-slate-600 font-bold hover:bg-slate-700">
        <Link to={`${routes.roster}?campaign=${encodeURIComponent(campaign)}`}>✏️ แก้ไข KOL</Link>
      </Button>

      <Button
        onClick={handlePackClick}
        disabled={uploading}
        className="rounded-[10px] bg-violet-600 font-bold hover:bg-violet-700"
      >
        {uploading ? '⏳ อัพโหลด…' : packSet ? '🖼️ ภาพสินค้า ✓' : '🖼️ ภาพสินค้า'}
      </Button>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={handlePackFile}
        aria-label="อัพโหลดภาพสินค้า"
      />

      <Button
        onClick={() => void pptx.run(onStatus, (msg) => window.alert(msg))}
        disabled={pptx.busy}
        className="rounded-[10px] bg-amber-700 font-bold hover:bg-amber-800"
      >
        {pptx.stage === 'tiein'
          ? '⏳ หา Tie-in…'
          : pptx.stage === 'building'
            ? '⏳ กำลังสร้าง…'
            : '📥 PowerPoint'}
      </Button>

      <Button
        onClick={() => void handleShare()}
        className="rounded-[10px] bg-blue-600 font-bold hover:bg-blue-700"
      >
        🔗 View Only for Client
      </Button>

      <Button onClick={handleRefresh} disabled={busy} className="rounded-[10px] font-bold">
        {busy ? '⏳ กำลังดึง…' : '🔄 Refresh Data'}
      </Button>
    </div>
  );
}
