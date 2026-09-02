import Script from "next/script";
import type { ReactNode } from "react";

import { WorkspaceGate } from "@/components/layout/WorkspaceGate";

export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <Script src="https://telegram.org/js/telegram-web-app.js" strategy="afterInteractive" />
      <WorkspaceGate>{children}</WorkspaceGate>
    </>
  );
}
