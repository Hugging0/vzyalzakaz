import type { ReactNode } from "react";

type Tone = "neutral" | "pink" | "blue" | "yellow" | "mint";

export function AppBadge({ children, tone = "neutral" }: { children: ReactNode; tone?: Tone }) {
  return <span className={`app-badge app-badge--${tone}`}>{children}</span>;
}
