import { useState } from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';

export interface AddKolDraft {
  username: string;
  display: string;
  group: string;
  subgroup: string;
  url: string;
}

interface AddKolFormProps {
  groups: string[];
  showSubgroup: boolean;
  /** Post-link field is report-only; the tracker roster has no links. */
  showUrl: boolean;
  groupListId: string;
  subListId: string;
  onAdd: (draft: AddKolDraft) => void;
  pending: boolean;
}

/** "แบบที่ 3" — add a single KOL by hand. */
export function AddKolForm({
  groups,
  showSubgroup,
  showUrl,
  groupListId,
  subListId,
  onAdd,
  pending,
}: AddKolFormProps) {
  const [username, setUsername] = useState('');
  const [display, setDisplay] = useState('');
  const [group, setGroup] = useState(groups[0] ?? '');
  const [subgroup, setSubgroup] = useState('');
  const [url, setUrl] = useState('');

  function submit() {
    onAdd({ username, display, group, subgroup, url });
    // Clearing here (rather than on success) matches the legacy form, which
    // reset immediately; a failed add surfaces as a toast, not a lost draft.
    setUsername('');
    setDisplay('');
    setSubgroup('');
    setUrl('');
  }

  return (
    <Card className="mb-4">
      <CardContent className="p-3">
        <div className="mb-2 text-sm font-semibold">➕ แบบที่ 3 · เพิ่ม KOL ทีละคน</div>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
          <Input
            className="h-9 text-[0.85rem]"
            placeholder="username (ไม่ต้องใส่ @)"
            aria-label="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !pending) submit();
            }}
          />
          <Input
            className="h-9 text-[0.85rem]"
            placeholder="ชื่อแสดง (เว้นว่าง = username)"
            aria-label="ชื่อแสดง"
            value={display}
            onChange={(e) => setDisplay(e.target.value)}
          />
          <Input
            className="h-9 text-[0.85rem]"
            placeholder="กลุ่มใหญ่"
            aria-label="กลุ่มใหญ่"
            list={groupListId}
            value={group}
            onChange={(e) => setGroup(e.target.value)}
          />
          {showSubgroup && (
            <Input
              className="h-9 text-[0.85rem]"
              placeholder="กลุ่มย่อย"
              aria-label="กลุ่มย่อย"
              list={subListId}
              value={subgroup}
              onChange={(e) => setSubgroup(e.target.value)}
            />
          )}
          <Button onClick={submit} disabled={pending}>
            เพิ่ม
          </Button>
        </div>
        {showUrl && (
          <div className="mt-2">
            <Input
              className="h-9 text-[0.85rem]"
              placeholder="🔗 ลิงก์โพสต์ TikTok/Facebook ของแคมเปญ (เว้นว่างได้ ใส่ทีหลัง)"
              aria-label="ลิงก์โพสต์"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
