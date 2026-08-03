import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AxiosError } from 'axios';

import { queryKeys } from '@/app/queryClient';
import { apiErrorMessage } from '@/lib/axios';
import { getSheetLink } from '@/features/roster/api/rosterApi';
import { bulkReplaceRoster } from '@/features/roster/api/rosterApi';
import { prepareImport } from '@/features/roster/lib/importSync';
import { parseSpreadsheetBytes } from '@/features/roster/lib/workbook';
import { fetchSheetBytes } from '@/features/roster/api/rosterApi';
import { startRefresh } from '@/features/report/api/reportApi';

/** Confirmation text — this is the last gate before spending Apify credits. */
export const REFRESH_CONFIRM =
  'อัปเดตข้อมูลแคมเปญนี้ (เฉพาะ KOL ที่ติ๊ก active):\n' +
  '• ถ้าผูกไฟล์ออนไลน์ไว้ จะดึงรายชื่อ+ลิงก์ล่าสุดจากไฟล์ก่อน\n' +
  '• แล้วดึงสถิติ + รูปโปรไฟล์จากทุกลิงก์\n' +
  '(ใช้เครดิต Apify · อาจใช้เวลา ~1-2 นาที)';

/**
 * The "🔄 Refresh Data" flow.
 *
 * If the campaign is linked to an online spreadsheet, the roster is re-synced
 * from it FIRST, so links edited in the source file are picked up by this run.
 * A sync failure is reported but does not abort — scraping the existing links is
 * still useful, and that is what the legacy page did.
 */
export function useRefreshFlow(campaign: string) {
  const queryClient = useQueryClient();
  const [starting, setStarting] = useState(false);

  async function syncRosterFromLinkedSheet(onStatus: (msg: string) => void): Promise<void> {
    const url = await getSheetLink(campaign);
    if (!url) return;

    onStatus('🔄 กำลังซิงก์รายชื่อจากไฟล์ต้นทาง…');
    const bytes = await fetchSheetBytes(url);
    const parsed = await parseSpreadsheetBytes(bytes);
    const { kols } = await prepareImport(parsed.kols, onStatus);
    if (!kols.length) throw new Error('ไม่พบรายชื่อในไฟล์');

    const result = await bulkReplaceRoster(campaign, { kols, sheet_url: url });
    onStatus(`ซิงก์รายชื่อจากไฟล์แล้ว ${result.count} ราย · กำลังดึงสถิติ…`);
  }

  async function run(onStatus: (msg: string) => void, onAlert: (msg: string) => void) {
    setStarting(true);
    try {
      try {
        await syncRosterFromLinkedSheet(onStatus);
      } catch (error) {
        onStatus(`⚠️ ซิงก์จากไฟล์ไม่สำเร็จ (${apiErrorMessage(error)}) — ดึงสถิติจากลิงก์เดิมต่อ`);
      }

      try {
        await startRefresh(campaign);
      } catch (error) {
        // 409 means a run is already in flight; the poller will follow it.
        if (error instanceof AxiosError && error.response?.status === 409) {
          onAlert('กำลังดึงข้อมูลอยู่แล้ว');
        } else {
          throw error;
        }
      }

      await queryClient.invalidateQueries({
        queryKey: queryKeys.report.refreshStatus(campaign),
      });
    } catch {
      onStatus('เริ่มงานไม่สำเร็จ');
    } finally {
      setStarting(false);
    }
  }

  return { run, starting };
}
