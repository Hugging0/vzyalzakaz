import type { ReactNode } from "react";
export function AppNotice({ children, tone = "neutral" }: { children: ReactNode; tone?: "neutral" | "warning" | "success" | "danger" }) {
  return <div className={`app-notice app-notice--${tone}`} role={tone === "danger" ? "alert" : "status"}>{children}</div>;
}
