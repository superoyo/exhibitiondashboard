import type { AiState } from '@kol/shared';

/**
 * Label + colour per AI state. Carried over verbatim from the legacy
 * `aiPaint()` map — `no_credit` stays visually distinct from `invalid_key`
 * because topping up billing fixes it without a new key.
 */
export const AI_STATE_DISPLAY: Record<AiState, { label: string; color: string }> = {
  ok: { label: '🟢 พร้อมใช้งาน', color: '#059669' },
  no_key: { label: '🔴 ยังไม่ได้ตั้ง key', color: '#dc2626' },
  no_credit: { label: '🟠 เครดิตหมด', color: '#d97706' },
  invalid_key: { label: '🔴 key ใช้ไม่ได้', color: '#dc2626' },
  error: { label: '⚠️ ตรวจสอบไม่ได้', color: '#d97706' },
};

export function aiStateDisplay(state: AiState | undefined) {
  return (state && AI_STATE_DISPLAY[state]) || AI_STATE_DISPLAY.error;
}
