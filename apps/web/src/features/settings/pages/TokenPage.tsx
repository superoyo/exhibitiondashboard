import { Alert, AlertDescription } from '@/components/ui/alert';
import { AppShell } from '@/components/layout/AppShell';
import { SETTINGS_TABS } from '@/components/layout/NavBar';
import { AiKeyCard } from '@/features/settings/components/AiKeyCard';
import { ApifyTokenCard } from '@/features/settings/components/ApifyTokenCard';

/**
 * /token — the two credentials the report runs on (APIFY Token and
 * ANTHROPIC_API_KEY), one self-contained card each: status, the buttons that
 * depend on it, and the replace box.
 *
 * The page itself is behind the session guard, and the write endpoints are
 * checked server-side. The notice below is kept from the legacy page because it
 * is still accurate: anyone signed in as staff can rotate these keys.
 */
export default function TokenPage() {
  return (
    <AppShell tabs={SETTINGS_TABS} width="narrow">
      <header className="mb-4">
        <h1 className="text-xl font-bold sm:text-2xl">🔑 Token &amp; API Key ของระบบ</h1>
        <p className="text-sm text-muted-foreground">
          กุญแจ 2 ตัวที่รีพอร์ตต้องใช้ — แต่ละกล่องบอกสถานะ ปุ่มที่ใช้กุญแจนั้น
          และที่วางกุญแจใหม่เมื่อหมดอายุ
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
    </AppShell>
  );
}
