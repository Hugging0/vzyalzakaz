import type { ReactNode } from "react";

export function AppField({ label, htmlFor, hint, children }: { label: string; htmlFor: string; hint?: string; children: ReactNode }) {
  return <div className="app-field"><label className="field-label" htmlFor={htmlFor}>{label}</label>{children}{hint && <p className="field-hint">{hint}</p>}</div>;
}
