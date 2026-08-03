import { useState } from 'react';

import { apiErrorMessage } from '@/lib/axios';
import { downloadPptx, getTieinStatus, startTiein } from '@/features/report/api/reportApi';

const POLL_MS = 4000;

/**
 * The "📥 PowerPoint" flow, which is two steps behind one button:
 *
 *  1. Kick off AI tie-in shots for any clips that lack one. Clips already
 *     processed are cached, so this costs nothing on a repeat run.
 *  2. Build and download the deck.
 *
 * A failed tie-in must NOT abort the export — the deck falls back to post cover
 * images, which is what the user actually asked for. The 409 from an
 * already-running job is likewise not an error: we simply wait for that job.
 */
export function usePptxExport(campaign: string) {
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<'idle' | 'tiein' | 'building'>('idle');

  async function waitForTiein(onStatus: (msg: string) => void) {
    for (;;) {
      let state;
      try {
        state = await getTieinStatus(campaign);
      } catch {
        return undefined; // status unreadable — proceed with the export anyway
      }
      if (state.status !== 'running') return state;
      onStatus(`🎯 ${state.message || 'กำลังหา tie-in shot…'}`);
      await new Promise((resolve) => setTimeout(resolve, POLL_MS));
    }
  }

  async function run(onStatus: (msg: string) => void, onAlert: (msg: string) => void) {
    setBusy(true);
    setStage('tiein');
    try {
      onStatus('🎯 กำลังหา tie-in shot จากคลิปใหม่… (คลิปที่เคยหาแล้วไม่เสียเครดิตซ้ำ)');
      try {
        await startTiein(campaign);
      } catch {
        // 409 = already running; waitForTiein below picks up that job.
      }

      const tiein = await waitForTiein(onStatus);
      if (tiein?.status === 'failed') {
        onAlert(
          `⚠️ หา tie-in shot ไม่สำเร็จ:\n\n${tiein.message || 'ไม่ทราบสาเหตุ'}\n\n` +
            'ระบบจะสร้างไฟล์ต่อโดยใช้รูปปกโพสต์แทน',
        );
        onStatus('⚠️ หา tie-in ไม่สำเร็จ — ใช้รูปปกโพสต์แทน');
      } else if (tiein?.message) {
        onStatus(`🎯 ${tiein.message}`);
      }

      setStage('building');
      onStatus('📥 กำลังสร้างไฟล์ PowerPoint… (อาจใช้เวลาสักครู่ถ้ารูปเยอะ)');
      const { blob, filename } = await downloadPptx(campaign);

      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);

      onStatus(
        `✅ ดาวน์โหลดไฟล์ PowerPoint แล้ว${tiein?.posts ? ` · ได้ tie-in shot ใหม่ ${tiein.posts} คลิป` : ''}`,
      );
    } catch (error) {
      onStatus(`⚠️ สร้างไฟล์ไม่สำเร็จ: ${apiErrorMessage(error)}`);
    } finally {
      setBusy(false);
      setStage('idle');
    }
  }

  return { run, busy, stage };
}
