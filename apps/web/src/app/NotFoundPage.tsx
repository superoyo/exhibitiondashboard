import { Link } from 'react-router-dom';

import { routes } from '@/config/routes';

export default function NotFoundPage() {
  return (
    <div className="mx-auto mt-[20vh] max-w-md px-4 text-center">
      <div className="text-4xl">🔍</div>
      <h2 className="mt-2 text-lg font-bold">ไม่พบหน้านี้</h2>
      <p className="mt-1 text-sm text-muted-foreground">
        ลิงก์อาจถูกเปลี่ยน — กลับไปที่ <Link to={routes.home}>หน้าแรก</Link>
      </p>
    </div>
  );
}
