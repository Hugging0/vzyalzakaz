import type { ReactNode } from "react";

export function AppStat({ label, value, hint }: { label: string; value: ReactNode; hint?: string }) {
  return (
    <div className="app-stat">
      <span>{label}</span>
      <strong>{value}</strong>
      {hint && <small>{hint}</small>}
    </div>
  );
}
