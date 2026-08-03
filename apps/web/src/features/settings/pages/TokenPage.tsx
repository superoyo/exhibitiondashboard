import { Alert, AlertDescription } from '@/components/ui/alert';
import { AppShell } from '@/components/layout/AppShell';
import { SETTINGS_TABS } from '@/components/layout/NavBar';
import { AiKeyCard } from '@/features/settings/components/AiKeyCard';
import { ApifyTokenCard, ApifyTokenForm } from '@/features/settings/components/ApifyTokenCard';

/**
 * /token — Apify token + Claude key management.
 *
 * The page itself is behind the session guard, and the write endpoints are
 * checked server-side. The notice below is kept from the legacy page because it
 * is still accurate: anyone signed in as staff can rotate these keys.
 */
export default function TokenPage() {
  return (
    <AppShell tabs={SETTINGS_TABS} width="narrow">
      <header className="mb-4">
        <h1 className="text-xl font-bold sm:text-2xl">🔑 Apify Token &amp; สถานะระบบ</h1>
        <p className="text-sm text-muted-foreground">
          Token ที่เว็บใช้ดึงข้อมูลจาก TikTok/Facebook · เปลี่ยนได้เมื่อ key หมดอายุ
        </p>
      </header>

      <Alert variant="warning" className="mb-4">
        <AlertDescription>
          ⚠️ หน้านี้ <b>ใครที่ล็อกอินเป็นพนักงานก็เปลี่ยน token ได้</b> — Token ถูกซ่อนไว้
          (โชว์แค่บางส่วน) ถ้าต้องการจำกัดสิทธิ์เฉพาะบางคนแจ้งผมเพิ่มได้
        </AlertDescription>
      </Alert>

      <ApifyTokenCard />
      <AiKeyCard />
      <ApifyTokenForm />
    </AppShell>
  );
}
