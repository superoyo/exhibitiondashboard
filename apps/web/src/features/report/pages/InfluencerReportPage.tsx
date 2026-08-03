import { ReportView } from '@/features/report/components/ReportView';

/**
 * `/vi/:viewToken` and `/vi/:slug/:viewToken` — the public link handed to the
 * INFLUENCERS in a campaign.
 *
 * Same tokens and the same resolution path as the client link (`/v/`), but a
 * separate URL namespace so this layout can change without touching what
 * clients see. What differs: no KPI summary, no charts, no metric numbers —
 * an influencer should see whose content is up and who still owes a link, not
 * the campaign's performance figures.
 *
 * Renders with NO session; kept outside RequireAuth on purpose.
 */
export default function InfluencerReportPage() {
  const campaign = window.__CAMPAIGN__ ?? '';

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

  return <ReportView campaign={campaign} viewOnly influencerView />;
}
