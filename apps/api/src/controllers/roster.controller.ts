import type { Request, Response } from 'express';
import { z } from 'zod';

import * as service from '../services/roster/roster.service.js';
import type { RosterKind } from '../services/roster/roster.service.js';

/**
 * `campaign` defaults to 'pao' on every roster endpoint, matching the Python
 * signature. It is ignored for the tracker roster, which is global.
 */
const campaignQuery = z.object({ campaign: z.string().default('pao') });

const idParam = z.coerce.number().int().positive();

const addBodySchema = z.object({
  username: z.string(),
  display: z.string().nullable().optional(),
  group: z.string(),
  subgroup: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
});

const linkSchema = z.object({
  platform: z.string().nullable().optional(),
  url: z.string().nullable().optional(),
  handle: z.string().nullable().optional(),
});

const patchBodySchema = z.object({
  display: z.string().optional(),
  group: z.string().optional(),
  subgroup: z.string().optional(),
  active: z.boolean().optional(),
  url: z.string().optional(),
  links: z.array(linkSchema).optional(),
});

const bulkBodySchema = z.object({
  kols: z.array(
    z.object({
      username: z.string(),
      display: z.string().nullable().optional(),
      group: z.string().nullable().optional(),
      subgroup: z.string().nullable().optional(),
      url: z.string().nullable().optional(),
      links: z
        .array(
          z.object({
            platform: z.string().nullable().optional(),
            url: z.string(),
            handle: z.string().nullable().optional(),
          }),
        )
        .nullable()
        .optional(),
      // Pydantic coerces a numeric string ('77') to int, so z.coerce matches it.
      followers: z.coerce.number().nullable().optional(),
    }),
  ),
  /**
   * Present-but-empty deliberately CLEARS the linked sheet; absent leaves it
   * alone. Matches Python's `if body.sheet_url is not None`.
   */
  sheet_url: z.string().nullable().optional(),
});

/**
 * Builds the four handlers bound to one roster kind.
 *
 * Arrow properties rather than method shorthand: these are passed to the router
 * as detached references, and a method would carry an implicit `this`.
 */
export function rosterController(kind: RosterKind) {
  return {
    list: async (req: Request, res: Response): Promise<void> => {
      const { campaign } = campaignQuery.parse(req.query);
      res.json({ kols: await service.listRoster(kind, campaign) });
    },

    add: async (req: Request, res: Response): Promise<void> => {
      const { campaign } = campaignQuery.parse(req.query);
      res.json(await service.addRosterKol(kind, campaign, addBodySchema.parse(req.body)));
    },

    patch: async (req: Request, res: Response): Promise<void> => {
      const id = idParam.parse(req.params.id);
      res.json(await service.patchRosterKol(kind, id, patchBodySchema.parse(req.body)));
    },

    remove: async (req: Request, res: Response): Promise<void> => {
      res.json(await service.deleteRosterKol(kind, idParam.parse(req.params.id)));
    },
  };
}

export async function bulkReplace(req: Request, res: Response): Promise<void> {
  const { campaign } = campaignQuery.parse(req.query);
  const body = bulkBodySchema.parse(req.body);
  res.json(await service.bulkReplaceRoster(campaign, body.kols, body.sheet_url));
}

export async function sheetLink(req: Request, res: Response): Promise<void> {
  const { campaign } = campaignQuery.parse(req.query);
  res.json(await service.getSheetUrl(campaign));
}
