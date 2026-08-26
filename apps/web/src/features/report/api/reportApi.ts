import type {
  ActiveJob,
  AdvisorState,
  CommentExportResponse,
  CommentListResponse,
  CommentSummary,
  JobState,
  PackshotSaveResult,
  PackshotState,
  ReportDataResponse,
} from '@kol/shared';

import { api } from '@/lib/axios';

export async function getReportData(campaign: string): Promise<ReportDataResponse> {
  const { data } = await api.get<ReportDataResponse>('/report/data', { params: { campaign } });
  return data;
}

// ---- Refresh (spends Apify credits) ---------------------------------------

/** Starts a background scrape. 409 means one is already running. */
export async function startRefresh(campaign: string): Promise<void> {
  await api.post('/report/refresh', null, { params: { campaign } });
}

export async function getRefreshStatus(campaign: string): Promise<JobState> {
  const { data } = await api.get<JobState>('/report/refresh/status', { params: { campaign } });
  return data;
}

// ---- AI tie-in shots ------------------------------------------------------

export async function startTiein(campaign: string): Promise<void> {
  await api.post('/report/tiein', null, { params: { campaign } });
}

export async function getTieinStatus(campaign: string): Promise<JobState> {
  const { data } = await api.get<JobState>('/report/tiein/status', { params: { campaign } });
  return data;
}

// ---- Background jobs ------------------------------------------------------

/** Every job running now, plus ones that just ended. Cheap: in-memory state. */
export async function getActiveJobs(): Promise<ActiveJob[]> {
  const { data } = await api.get<ActiveJob[]>('/jobs/active');
  return data;
}

// ---- Comment breakdown ----------------------------------------------------

/** Reads stored comments only — opening the report never scrapes. */
export async function getComments(campaign: string): Promise<CommentSummary> {
  const { data } = await api.get<CommentSummary>('/report/comments', { params: { campaign } });
  return data;
}

/** One page of product-related comments, filtered and paged on the server. */
export async function getCommentList(
  campaign: string,
  category: string,
  offset: number,
  limit: number,
): Promise<CommentListResponse> {
  const { data } = await api.get<CommentListResponse>('/report/comments/list', {
    params: { campaign, category, offset, limit },
  });
  return data;
}

/**
 * The same two reads for a public client link (`/v/:viewToken`), which has no
 * session at all.
 *
 * Addressed by the token, never by the campaign key: the key is a short
 * guessable string, so a `?campaign=` endpoint open to the internet would serve
 * every client's comments — and the commenters' names — to anyone who tried a
 * few. The token is 72 random bits, and whoever has it already has the report.
 */
export async function getViewComments(viewToken: string): Promise<CommentSummary> {
  const { data } = await api.get<CommentSummary>(`/view/${encodeURIComponent(viewToken)}/comments`);
  return data;
}

export async function getViewCommentList(
  viewToken: string,
  category: string,
  offset: number,
  limit: number,
): Promise<CommentListResponse> {
  const { data } = await api.get<CommentListResponse>(
    `/view/${encodeURIComponent(viewToken)}/comments/list`,
    { params: { category, offset, limit } },
  );
  return data;
}

/**
 * Every stored comment, for the Excel export. Not a react-query hook: it runs
 * once when the button is pressed, and caching a few thousand rows the page
 * never renders would cost memory for nothing.
 *
 * There is deliberately no client-link equivalent — a raw dump of every comment,
 * spam included, is an internal tool.
 */
export async function getCommentExport(campaign: string): Promise<CommentExportResponse> {
  const { data } = await api.get<CommentExportResponse>('/report/comments/export', {
    params: { campaign },
  });
  return data;
}

/**
 * Starts a comment scrape + classify. Its own action on purpose: Apify bills
 * per comment, so this is the priciest thing in the product and must never
 * ride along with a stat refresh.
 */
export async function startCommentRefresh(campaign: string): Promise<void> {
  await api.post('/report/comments/refresh', null, { params: { campaign } });
}

export async function getCommentStatus(campaign: string): Promise<JobState> {
  const { data } = await api.get<JobState>('/report/comments/status', { params: { campaign } });
  return data;
}

// ---- Performance advisor ----------------------------------------------------
// Internal only: the analysis input includes selling prices, so none of this is
// ever fetched on a client link.

export async function getAdvisor(campaign: string): Promise<AdvisorState> {
  const { data } = await api.get<AdvisorState>('/report/advisor', { params: { campaign } });
  return data;
}

/** One Claude call over the whole campaign (~a few baht, not in the cost table). */
export async function runAdvisor(campaign: string): Promise<void> {
  await api.post('/report/advisor/run', null, { params: { campaign } });
}

export async function getAdvisorStatus(campaign: string): Promise<JobState> {
  const { data } = await api.get<JobState>('/report/advisor/status', { params: { campaign } });
  return data;
}

// ---- Product pack shot ----------------------------------------------------

export async function getPackshot(campaign: string): Promise<PackshotState> {
  const { data } = await api.get<PackshotState>('/report/packshot', { params: { campaign } });
  return data;
}

export async function savePackshot(
  campaign: string,
  imageBase64: string,
): Promise<PackshotSaveResult> {
  const { data } = await api.post<PackshotSaveResult>(
    '/report/packshot',
    { image_base64: imageBase64 },
    { params: { campaign } },
  );
  return data;
}

// ---- Cost -----------------------------------------------------------------

export async function resetCost(campaign: string): Promise<void> {
  await api.post('/report/cost/reset', null, { params: { campaign } });
}

// ---- PowerPoint -----------------------------------------------------------

export interface PptxDownload {
  blob: Blob;
  filename: string;
}

/**
 * Downloads the generated deck.
 *
 * Goes through the Axios instance rather than `location.href` so the bearer
 * token rides along — a plain navigation would arrive unauthenticated.
 */
export async function downloadPptx(campaign: string): Promise<PptxDownload> {
  const response = await api.get('/report/pptx', {
    params: { campaign },
    responseType: 'blob',
  });

  // Prefer the server's RFC 5987 filename; it carries the campaign name.
  const disposition = String(response.headers['content-disposition'] ?? '');
  let filename = 'report.pptx';
  const match = /filename\*=UTF-8''([^;]+)/i.exec(disposition);
  if (match?.[1]) {
    try {
      filename = decodeURIComponent(match[1]);
    } catch {
      // Malformed encoding — keep the default name.
    }
  }
  return { blob: response.data as Blob, filename };
}
