import { useEffect, useState } from 'react';
import {
  CAMPAIGN_KEY_ERROR,
  campaignFormSchema,
  normalizeCampaignKey,
  type Campaign,
} from '@kol/shared';

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
import { useCreateCampaign, useUpdateCampaign } from '@/features/campaigns/hooks/useCampaigns';

import { DEFAULT_CAMPAIGN_EMOJI, EmojiPicker } from './EmojiPicker';

interface CampaignFormDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** null = create mode; a campaign = edit mode. */
  editing: Campaign | null;
  /** Create mode jumps straight to the new report so KOLs can be added. */
  onCreated: (campaign: Campaign) => void;
}

/**
 * One dialog serving both create and edit, as the legacy modal did. The URL-key
 * field only appears in edit mode — on create the backend derives the key from
 * the campaign name.
 */
export function CampaignFormDialog({
  open,
  onOpenChange,
  editing,
  onCreated,
}: CampaignFormDialogProps) {
  const isEdit = editing !== null;
  const create = useCreateCampaign();
  const update = useUpdateCampaign();

  const [name, setName] = useState('');
  const [subtitle, setSubtitle] = useState('');
  const [emoji, setEmoji] = useState<string>(DEFAULT_CAMPAIGN_EMOJI);
  const [key, setKey] = useState('');
  const [error, setError] = useState('');

  // Reset the form whenever the dialog opens, so a previous edit never leaks
  // its values into the next create.
  useEffect(() => {
    if (!open) return;
    setName(editing?.name ?? '');
    setSubtitle(editing?.subtitle ?? '');
    setEmoji(editing?.emoji || DEFAULT_CAMPAIGN_EMOJI);
    setKey(editing?.key ?? '');
    setError('');
  }, [open, editing]);

  const pending = create.isPending || update.isPending;

  function handleSubmit() {
    const parsed = campaignFormSchema.safeParse({ name, emoji, subtitle });
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message ?? '');
      return;
    }
    setError('');
    const patch = parsed.data;

    if (isEdit) {
      const normalized = key.trim() ? normalizeCampaignKey(key) : editing.key;
      if (normalized.length < 2) {
        setError(CAMPAIGN_KEY_ERROR);
        return;
      }
      update.mutate(
        { key: editing.key, newKey: normalized, patch },
        {
          onSuccess: (updated) => {
            toast.success(`บันทึกแคมเปญ "${updated.name}" แล้ว`);
            onOpenChange(false);
          },
          onError: (err) => setError(apiErrorMessage(err)),
        },
      );
      return;
    }

    create.mutate(patch, {
      onSuccess: (created) => {
        toast.success(`สร้างแคมเปญ "${created.name}" แล้ว`);
        onOpenChange(false);
        onCreated(created);
      },
      onError: (err) => setError(apiErrorMessage(err)),
    });
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        onKeyDown={(e) => {
          if (e.key === 'Enter' && !pending) handleSubmit();
        }}
      >
        <DialogHeader>
          <DialogTitle>{isEdit ? '✏️ แก้ไขแคมเปญ' : '🆕 สร้างแคมเปญใหม่'}</DialogTitle>
          <DialogCloseButton />
        </DialogHeader>

        <div className="grid gap-3">
          <div>
            <Label htmlFor="campaign-name">ชื่อแคมเปญ (แสดงบนหัวรายงาน)</Label>
            <Input
              id="campaign-name"
              autoFocus
              placeholder="เช่น Sahagroup Fair 2028"
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </div>

          <div>
            <span className="mb-1.5 block text-[0.8rem] font-semibold text-muted-foreground">
              Emoji / ไอคอน
            </span>
            <EmojiPicker value={emoji} onChange={setEmoji} />
          </div>

          <div>
            <Label htmlFor="campaign-subtitle">คำอธิบาย (บอกว่าเป็นแคมเปญอะไร)</Label>
            <Input
              id="campaign-subtitle"
              placeholder="เช่น Mega KOL + Micro-Nano KOL · TikTok/FB"
              value={subtitle}
              onChange={(e) => setSubtitle(e.target.value)}
            />
          </div>

          {isEdit ? (
            <div>
              <Label htmlFor="campaign-key">รหัส URL (ลิงก์รายงานคือ …/c/&lt;รหัส&gt;)</Label>
              <Input
                id="campaign-key"
                placeholder="เช่น 00001"
                value={key}
                onChange={(e) => setKey(e.target.value)}
              />
              <span className="mt-1 block text-xs text-muted-foreground">
                a-z 0-9 หรือ - · ⚠️ เปลี่ยนแล้วลิงก์เดิมของแคมเปญนี้จะเปลี่ยนตาม
              </span>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground">
              รหัส URL จะสร้างจากชื่อแคมเปญอัตโนมัติ (เช่น …/c/dna-high-protein) —
              แก้ได้ภายหลังในปุ่ม Edit
            </p>
          )}

          <div className="mt-2 flex items-center justify-end gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={pending}>
              ยกเลิก
            </Button>
            <Button onClick={handleSubmit} disabled={pending}>
              {isEdit ? 'บันทึก' : 'สร้าง'}
            </Button>
          </div>

          {error && <div className="text-sm text-destructive">{error}</div>}
        </div>
      </DialogContent>
    </Dialog>
  );
}
