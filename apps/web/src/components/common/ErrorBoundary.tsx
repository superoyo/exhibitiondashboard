import { Component, type ErrorInfo, type ReactNode } from 'react';

import { Button } from '@/components/ui/button';

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Last-resort boundary so a render error shows a readable message instead of a
 * blank gold page. Report pages render a lot of user-supplied data, so this is
 * not hypothetical.
 */
export class ErrorBoundary extends Component<Props, State> {
  override state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  override componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error:', error, info.componentStack);
  }

  override render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="mx-auto mt-[15vh] max-w-md px-4 text-center">
        <div className="text-3xl">⚠️</div>
        <h2 className="mt-2 text-lg font-bold">หน้านี้แสดงผลไม่สำเร็จ</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          กรุณารีเฟรชหน้า — ถ้ายังไม่หายแจ้งทีมงานพร้อมข้อความด้านล่าง
        </p>
        <pre className="mt-3 overflow-x-auto rounded-lg border border-border bg-white p-3 text-left text-xs text-destructive">
          {this.state.error.message}
        </pre>
        <Button className="mt-4" onClick={() => window.location.reload()}>
          รีเฟรชหน้า
        </Button>
      </div>
    );
  }
}
