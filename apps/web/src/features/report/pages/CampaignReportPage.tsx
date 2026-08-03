import { useLocation, useParams } from 'react-router-dom';

import { ReportView } from '@/features/report/components/ReportView';

/**
 * `/c/:campaignKey` — the internal report.
 *
 * `?view=1` still forces client mode, as it did on the legacy page, so an
 * existing preview link keeps behaving the same way.
 */
export default function CampaignReportPage() {
  const { campaignKey = '' } = useParams<{ campaignKey: string }>();
  const location = useLocation();
  const viewOnly = new URLSearchParams(location.search).get('view') === '1';

  return <ReportView campaign={campaignKey.toLowerCase()} viewOnly={viewOnly} />;
}
