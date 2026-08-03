import type { Request, Response } from 'express';
import { z } from 'zod';

import * as service from '../services/campaign/campaign.service.js';
import { campaignSummary } from '../services/campaign/campaignSummary.service.js';
import * as write from '../services/campaign/campaignWrite.service.js';

/** Same bounds as the Python endpoint: 1..100, default 15. */
const listQuerySchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(15),
  include_inactive: z
    .enum(['true', 'false', '1', '0'])
    .default('false')
    .transform((v) => v === 'true' || v === '1'),
});

const summaryQuerySchema = z.object({
  /** Comma-separated campaign keys; empty means every campaign. */
  keys: z.string().default(''),
  days: z.coerce.number().int().min(0).max(730).default(0),
});

const patchBodySchema = z.object({
  name: z.string().optional(),
  emoji: z.string().optional(),
  subtitle: z.string().optional(),
  groups: z.array(z.string()).optional(),
  subgroups: z.array(z.string()).optional(),
  active: z.boolean().optional(),
});

const renameBodySchema = z.object({ new_key: z.string() });

const keyParam = z.string().min(1);

export async function list(req: Request, res: Response): Promise<void> {
  const { limit, include_inactive } = listQuerySchema.parse(req.query);
  res.json({ campaigns: await service.listCampaigns(limit, include_inactive) });
}

export async function summary(req: Request, res: Response): Promise<void> {
  const { keys, days } = summaryQuerySchema.parse(req.query);
  const wanted = keys
    .split(',')
    .map((k) => k.trim())
    .filter(Boolean);
  res.json(await campaignSummary(wanted, days));
}

export async function detail(req: Request, res: Response): Promise<void> {
  res.json(await service.getCampaignDetail(keyParam.parse(req.params.key)));
}

export async function patch(req: Request, res: Response): Promise<void> {
  const key = keyParam.parse(req.params.key);
  res.json(await write.patchCampaign(key, patchBodySchema.parse(req.body)));
}

export async function archive(req: Request, res: Response): Promise<void> {
  res.json(await write.archiveCampaign(keyParam.parse(req.params.key)));
}

export async function viewToken(req: Request, res: Response): Promise<void> {
  res.json(await write.getViewToken(keyParam.parse(req.params.key)));
}

export async function rename(req: Request, res: Response): Promise<void> {
  const key = keyParam.parse(req.params.key);
  const { new_key } = renameBodySchema.parse(req.body);
  res.json(await write.renameCampaign(key, new_key));
}
