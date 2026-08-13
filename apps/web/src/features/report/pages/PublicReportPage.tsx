import { useParams } from 'react-router-dom';

import { ReportView } from '@/features/report/components/ReportView';

/**
 * `/v/:viewToken` and `/v/:slug/:viewToken` — the public, view-only client link.
 *
 * The token in the path is deliberately NOT the campaign key: it is random and
 * unguessable so client links can't be enumerated. That means the browser cannot
 * derive which campaign this is — the server resolves the token and injects
 * `window.__CAMPAIGN__` into the HTML shell before sending it.
 *
 * This page must render with NO session; it is intentionally outside RequireAuth.
 */
export default function PublicReportPage() {
  const campaign = window.__CAMPAIGN__ ?? '';
  // The comment reads need the token itself: they are addressed by token rather
  // than by campaign key, so that opening them to sessionless visitors does not
  // also open every other campaign's comments to anyone guessing short keys.
  // Present in both route shapes — /v/:viewToken and /v/:slug/:viewToken.
  const { viewToken = '' } = useParams<{ viewToken: string }>();

  if (!campaign) {
    return (
      <div className="mx-auto mt-[20vh] max-w-md px-4 text-center">
        <h2 className="text-lg font-bold">ไม่พบลิงก์รายงานนี้</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          ลิงก์อาจถูกเปลี่ยน — กรุณาขอลิงก์ใหม่จากทีมงาน
        </p>
      </div>
    );
  }

  return <ReportView campaign={campaign} viewOnly viewToken={viewToken} />;
}
