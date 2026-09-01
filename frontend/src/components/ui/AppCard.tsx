import type { HTMLAttributes, ReactNode } from "react";
type Tone = "paper" | "pink" | "blue" | "yellow" | "mint" | "ink";
export function AppCard({ children, className = "", tone = "paper", ...props }: HTMLAttributes<HTMLElement> & { children: ReactNode; tone?: Tone }) {
  return <section className={`app-card app-card--${tone} ${className}`} {...props}>{children}</section>;
}
