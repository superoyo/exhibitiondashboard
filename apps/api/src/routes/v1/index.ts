import { Router } from 'express';

import * as campaigns from '../../controllers/campaigns.controller.js';
import * as health from '../../controllers/health.controller.js';
import { bulkReplace, rosterController, sheetLink } from '../../controllers/roster.controller.js';
import { asyncHandler } from '../../utils/asyncHandler.js';

/**
 * Natively-implemented endpoints.
 *
 * Everything NOT registered here falls through to the Python service (see
 * `pythonProxy`). Endpoints move over one group at a time, reads before writes,
 * so a regression is limited to one group and easy to attribute.
 *
 * Ported: version · campaigns (list, summary, detail, patch, archive,
 * view-token, rename) · roster (tracker + report CRUD, bulk replace, sheet link).
 *
 * Still proxied: POST /campaigns — it stores a 64px JPEG thumbnail of the
 * creator's photo, which needs image resizing. Pillow is already a transitive
 * dependency on the Python side; adding a native Node image library is a
 * separate decision, so creation stays there for now.
 */
export const v1Router = Router();

v1Router.get('/version', health.version);

// ---- campaigns ------------------------------------------------------------
v1Router.get('/campaigns', asyncHandler(campaigns.list));
// `/campaigns/summary` MUST precede `/campaigns/:key`, or the parameterised
// route swallows it and "summary" is treated as a campaign key.
v1Router.get('/campaigns/summary', asyncHandler(campaigns.summary));
v1Router.get('/campaigns/:key/view-token', asyncHandler(campaigns.viewToken));
v1Router.post('/campaigns/:key/rename', asyncHandler(campaigns.rename));
v1Router.get('/campaigns/:key', asyncHandler(campaigns.detail));
v1Router.patch('/campaigns/:key', asyncHandler(campaigns.patch));
v1Router.delete('/campaigns/:key', asyncHandler(campaigns.archive));

// ---- roster ---------------------------------------------------------------
// The two rosters are separate tables with different columns; `/roster/*` also
// keeps them clear of `GET /api/kols/:username`, which is the tracker's
// per-KOL detail endpoint and unrelated.
const tracker = rosterController('tracker');
const report = rosterController('report');

// Literal sub-paths first: otherwise 'bulk' / 'sheet' would parse as an :id.
v1Router.post('/roster/report/bulk', asyncHandler(bulkReplace));
v1Router.get('/roster/report/sheet', asyncHandler(sheetLink));

for (const [name, ctrl] of [
  ['tracker', tracker],
  ['report', report],
] as const) {
  v1Router.get(`/roster/${name}`, asyncHandler(ctrl.list));
  v1Router.post(`/roster/${name}`, asyncHandler(ctrl.add));
  v1Router.patch(`/roster/${name}/:id`, asyncHandler(ctrl.patch));
  v1Router.delete(`/roster/${name}/:id`, asyncHandler(ctrl.remove));
}
