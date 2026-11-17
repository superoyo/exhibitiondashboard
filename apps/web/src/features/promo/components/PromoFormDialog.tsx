import { useEffect, useState } from 'react';
import type { PromoCampaignDetail, PromoCampaignSummary } from '@kol/shared';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogCloseButton,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { apiErrorMessage } from '@/lib/axios';
import { toast } from '@/stores/toastStore';
import { useCreatePromo, useUpdatePromo } from '@/features/promo/hooks/usePromo';

interface PromoFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** null = add a deal; otherwise edit this one. */
  editing: Pick<PromoCampaignSummary, 'id' | 'name' | 'team' | 'sheet_url'> | null;
  onSaved?: (detail: PromoCampaignDetail) => void;
}

/**
 * Add / edit a deal: a name, who runs it, and the link to their quota sheet.
 * That is all this page ever asks for — the numbers come from the sheet.
 */
export function PromoFormDialog({ open, onOpenChange, editing, onSaved }: PromoFormDialogProps) {
  const isEdit = editing !== null;
  const create = useCreatePromo();
  const update = useUpdatePromo();

  const [name, setName] = useState('');
  const [team, setTeam] = useState('');
  const [sheetUrl, setSheetUrl] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open) return;
    setName(editing?.name ?? '');
    setTeam(editing?.team ?? '');
    setSheetUrl(editing?.sheet_url ?? '');
    setError('');
  }, [open, editing]);

  const pending = create.isPending || update.isPending;

  function handleSubmit() {
    if (!name.trim()) return setError('ใส่ชื่องานก่อน');
    if (!/^https?:\/\//i.test(sheetUrl.trim())) {
      return setError('วางลิงก์ไฟล์เช็กโควต้า (ขึ้นต้นด้วย https://)');
    }
    setError('');
    const input = { name: name.trim(), team: team.trim(), sheet_url: sheetUrl.trim() };

    const done = (detail: PromoCampaignDetail) => {
      // Saved either way; an unreadable sheet is reported, not a failure.
      if (detail.sync_error) toast.error(`บันทึกแล้ว แต่ยังดึงข้อมูลไม่ได้: ${detail.sync_error}`);
      else toast.success(`บันทึก "${detail.name}" แล้ว — ดึงข้อมูลจากชีตเรียบร้อย`);
      onOpenChange(false);
      onSaved?.(detail);
    };
    const fail = (err: unknown) => setError(apiErrorMessage(err));

    if (isEdit) update.mutate({ id: editing.id, input }, { onSuccess: done, onError: fail });
    else create.mutate(input, { onSuccess: done, onError: fail });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? '✏️ แก้ไขงาน' : '🆕 เพิ่มงาน'}</DialogTitle>
          <DialogCloseButton />
        </DialogHeader>

        <div className="grid gap-3">
          <div>
            <Label htmlFor="promo-name">ชื่องาน</Label>
            <Input
              id="promo-name"
              autoFocus
              placeholder="เช่น Lion Beauty Promotion Page 2026"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="promo-team">ทีมที่ดูแล</Label>
            <Input
              id="promo-team"
              placeholder="เช่น BAM / Haru / Ploy"
              value={team}
              onChange={(e) => setTeam(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="promo-sheet">ลิงก์ไฟล์เช็กโควต้า</Label>
            <Input
              id="promo-sheet"
              placeholder="https://docs.google.com/spreadsheets/d/…"
              value={sheetUrl}
              onChange={(e) => setSheetUrl(e.target.value)}
            />
            <span className="mt-1 block text-xs text-muted-foreground">
              ใช้ได้ทั้ง Google Sheet และ Excel บน SharePoint / OneDrive — ต้องตั้งแชร์เป็น
              &quot;ทุกคนที่มีลิงก์ดูได้&quot; ระบบอ่านอย่างเดียว ไม่แก้ไขไฟล์ของทีม
            </span>
          </div>

          <div className="mt-2 flex items-center justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
              ยกเลิก
            </Button>
            <Button onClick={handleSubmit} disabled={pending}>
              {pending ? 'กำลังดึงข้อมูลจากชีต…' : isEdit ? 'บันทึก' : 'เพิ่มงาน'}
            </Button>
          </div>

          {error && <div className="text-sm text-destructive">{error}</div>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
