import type { Request, Response } from 'express';

/** Build marker — confirms which commit is actually running. */
export function version(_req: Request, res: Response): void {
  res.json({ build: 'campaign-hub-v96' });
}
