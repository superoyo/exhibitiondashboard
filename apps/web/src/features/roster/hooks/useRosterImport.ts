import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { apiErrorMessage } from '@/lib/axios';
import { toast } from '@/stores/toastStore';
import { bulkReplaceRoster, fetchSheetBytes } from '@/features/roster/api/rosterApi';
import {
  buildImportConfirmMessage,
  importSummary,
  prepareImport,
} from '@/features/roster/lib/importSync';
import {
  parseSpreadsheetBytes,
  parseSpreadsheetFile,
  type ParsedWorkbook,
} from '@/features/roster/lib/workbook';

import { rosterKeys } from './useRoster';

/**
 * Drives the "replace the whole roster from a file/sheet" flow.
 *
 * Status is a plain string rather than a mutation state because the legacy page
 * reported a running commentary through several async stages (reading → resolving
 * links → importing), and that feedback is the only signal during what can be a
 * 90-second link-resolution pass.
 */
export function useRosterImport(campaign: string) {
  const queryClient = useQueryClient();
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  async function runImport(parsed: ParsedWorkbook, sheetUrl?: string) {
    if (!parsed.kols.length) {
      setStatus(
        '⚠️ ไม่พบรายชื่อ KOL — ต้องมีลิงก์โพสต์ (TikTok/FB/IG/YT/X) หรือ @username อย่างน้อย 1 อย่าง · ' +
          `ระบบอ่านเจอ: ${parsed.debug || '(ว่าง)'}`,
      );
      return;
    }

    const { kols, dropped } = await prepareImport(parsed.kols, setStatus);
    if (!kols.length) {
      setStatus('⚠️ ระบุ KOL ไม่ได้เลย — ตรวจว่าไฟล์มีลิงก์โพสต์หรือ @username');
      return;
    }

    if (!window.confirm(buildImportConfirmMessage(kols, dropped, parsed.skipped))) {
      setStatus('');
      return;
    }

    const { linkCount } = importSummary(kols);
    // KOLs whose KPI came from a shared (merged) total, already divided per head
    const kpiCount = kols.filter((k) => (k.kpis ?? []).length > 0).length;
    setStatus('กำลังนำเข้า…');
    try {
      const result = await bulkReplaceRoster(campaign, {
        kols,
        ...(sheetUrl ? { sheet_url: sheetUrl } : {}),
      });
      setStatus(
        `✅ นำเข้าแล้ว ${result.count} รายชื่อ (${linkCount} ลิงก์)` +
          (kpiCount ? ` · KPI ${kpiCount} คน` : '') +
          ' — แทนที่ของเดิม · ไปกด Refresh Data เพื่อดึงสถิติ',
      );
      toast.success(`นำเข้า ${result.count} รายชื่อแล้ว`);
      void queryClient.invalidateQueries({ queryKey: rosterKeys.list('report', campaign) });
      void queryClient.invalidateQueries({ queryKey: ['roster', 'groupkpi', campaign] });
      if (sheetUrl) {
        void queryClient.invalidateQueries({ queryKey: rosterKeys.sheet(campaign) });
      }
    } catch (error) {
      const message = apiErrorMessage(error);
      setStatus(`⚠️ ${message}`);
      toast.error(message);
    }
  }

  async function importFile(file: File) {
    setBusy(true);
    setStatus('กำลังอ่านไฟล์…');
    try {
      await runImport(await parseSpreadsheetFile(file));
    } catch (error) {
      setStatus(`อ่านไฟล์ไม่สำเร็จ: ${apiErrorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  async function importFromUrl(url: string) {
    if (!url) {
      setStatus('วางลิงก์ Google Sheet ก่อน');
      return;
    }
    setBusy(true);
    setStatus('กำลังดึง Google Sheet…');
    try {
      const bytes = await fetchSheetBytes(url);
      await runImport(await parseSpreadsheetBytes(bytes), url);
    } catch (error) {
      setStatus(`⚠️ ${apiErrorMessage(error)}`);
    } finally {
      setBusy(false);
    }
  }

  return { status, busy, importFile, importFromUrl };
}
