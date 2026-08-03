import type { Campaign } from '@kol/shared';

import * as repo from '../../repositories/campaign.repo.js';
import { pyJsonList, sliceCodePoints } from '../../utils/pythonJson.js';
import * as write from '../../repositories/campaignWrite.repo.js';
import { AppError } from '../../utils/AppError.js';
import { serializeCampaign } from './campaign.service.js';

/** Campaign keys allow a-z, 0-9 and '-' only, 2..32 characters. */
const KEY_MAX = 32;
const KEY_MIN = 2;
const KEY_ERROR = 'รหัสต้องเป็น a-z 0-9 หรือ - เท่านั้น (2–32 ตัวอักษร)';

/** Same normalisation as `rename_campaign` in app/api/routes.py:1110. */
export function normalizeKey(raw: string): string {
  return (raw || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9-]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, KEY_MAX);
}

export interface CampaignPatchFields {
  name?: string;
  emoji?: string;
  subtitle?: string;
  groups?: string[];
  subgroups?: string[];
  active?: boolean;
}

/**
 * PATCH semantics: only fields PRESENT in the request are touched. An absent
 * field must leave the stored value alone — sending `{name}` alone must not wipe
 * the subtitle.
 */
export async function patchCampaign(key: string, fields: CampaignPatchFields): Promise<Campaign> {
  const existing = await repo.getCampaign(key);
  if (!existing) throw AppError.notFound(`ไม่พบแคมเปญ '${key}'`);

  const patch: Parameters<typeof write.updateCampaign>[1] = {};
  if (fields.name !== undefined) patch.name = fields.name.trim();
  // Capped at 8 by the column. Sliced by CODE POINTS, not UTF-16 units, or a
  // 6-emoji value would be cut to 4 — see utils/pythonJson.ts.
  if (fields.emoji !== undefined) patch.emoji = sliceCodePoints(fields.emoji.trim(), 8) || '📊';
  // Empty subtitle is stored as NULL, not '' — the read path coerces back to ''.
  if (fields.subtitle !== undefined) patch.subtitle = fields.subtitle.trim() || null;
  if (fields.groups !== undefined) patch.groupsJson = pyJsonList(fields.groups);
  if (fields.subgroups !== undefined) patch.subgroupsJson = pyJsonList(fields.subgroups);
  if (fields.active !== undefined) patch.active = fields.active;

  const updated = Object.keys(patch).length ? await write.updateCampaign(key, patch) : existing;
  if (!updated) throw AppError.notFound(`ไม่พบแคมเปญ '${key}'`);

  // Python returns `_campaign_dict(c)` here — i.e. roster_count 0 and
  // refreshed_at null, NOT the real figures. Matched deliberately.
  return serializeCampaign(updated);
}

export async function archiveCampaign(key: string): Promise<{ status: 'archived'; key: string }> {
  const existing = await repo.getCampaign(key);
  if (!existing) throw AppError.notFound(`ไม่พบแคมเปญ '${key}'`);
  await write.archiveCampaign(key);
  return { status: 'archived', key };
}

/** The client link token, generated on first request. */
export async function getViewToken(key: string): Promise<{ token: string }> {
  const token = await write.ensureViewToken(key);
  if (token === null) throw AppError.notFound(`ไม่พบแคมเปญ '${key}'`);
  return { token };
}

export async function renameCampaign(
  key: string,
  rawNewKey: string,
): Promise<{ status: 'renamed' | 'unchanged'; key: string }> {
  const existing = await repo.getCampaign(key);
  if (!existing) throw AppError.notFound(`ไม่พบแคมเปญ '${key}'`);

  const newKey = normalizeKey(rawNewKey);
  if (!newKey || newKey.length < KEY_MIN) throw AppError.badRequest(KEY_ERROR);
  if (newKey === key) return { status: 'unchanged', key };
  if (await write.keyExists(newKey)) throw AppError.conflict(`มีรหัส '${newKey}' อยู่แล้ว`);

  try {
    await write.renameCampaign(key, newKey);
  } catch {
    // A concurrent rename can win the race between the check above and the
    // update; report the same conflict rather than a 500.
    throw AppError.conflict(`มีรหัส '${newKey}' อยู่แล้ว`);
  }
  return { status: 'renamed', key: newKey };
}
