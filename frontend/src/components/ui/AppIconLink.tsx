import type { ReactNode } from "react";

export function AppIconLink({ href, label, children }: { href: string; label: string; children: ReactNode }) {
  return <a className="icon-link" href={href} target="_blank" rel="noreferrer" aria-label={label}>{children}</a>;
}
