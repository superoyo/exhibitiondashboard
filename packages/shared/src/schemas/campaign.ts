import { z } from 'zod';

/**
 * Campaign inputs. Messages match what the current backend returns so the UI
 * copy does not shift when validation moves to Express.
 */

export const campaignFormSchema = z.object({
  name: z.string().trim().min(1, 'ใส่ชื่อแคมเปญก่อน'),
  /** Backend truncates to 8 chars and falls back to the chart emoji. */
  emoji: z.string().trim().max(8).default('📊'),
  subtitle: z.string().trim().default(''),
});

export type CampaignFormInput = z.infer<typeof campaignFormSchema>;

/**
 * URL key rules, mirroring `rename_campaign`: lowercased, anything outside
 * [a-z0-9-] collapsed to '-', trimmed of dashes, capped at 32, min length 2.
 */
export const CAMPAIGN_KEY_MAX = 32;
export const CAMPAIGN_KEY_MIN = 2;
export const CAMPAIGN_KEY_ERROR = 'รหัสต้องเป็น a-z 0-9 หรือ - เท่านั้น (2–32 ตัวอักษร)';

export function normalizeCampaignKey(raw: string): string {
  return raw
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, CAMPAIGN_KEY_MAX);
}

export const campaignKeySchema = z
  .string()
  .transform(normalizeCampaignKey)
  .refine((v) => v.length >= CAMPAIGN_KEY_MIN, { message: CAMPAIGN_KEY_ERROR });
