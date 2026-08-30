import type { HTMLAttributes, ReactNode } from "react";
export function AppCard({ children, className = "", ...props }: HTMLAttributes<HTMLElement> & { children: ReactNode }) {
  return <section className={`app-card ${className}`} {...props}>{children}</section>;
}
