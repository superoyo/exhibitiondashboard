import { RouterProvider } from 'react-router-dom';

import { Providers } from '@/app/providers';
import { router } from '@/app/router';
import { Toaster } from '@/components/common/Toaster';

export default function App() {
  return (
    <Providers>
      <RouterProvider router={router} />
      <Toaster />
    </Providers>
  );
}
