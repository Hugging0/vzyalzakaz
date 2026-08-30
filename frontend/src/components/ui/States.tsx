import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";

export function AppEmptyState({ title, text, action, onAction }: { title: string; text: string; action?: string; onAction?: () => void }) {
  return <AppCard className="empty-state"><h2>{title}</h2><p className="muted">{text}</p>{action && onAction && <AppButton variant="secondary" onClick={onAction}>{action}</AppButton>}</AppCard>;
}

export function FeedSkeleton() { return <div className="stack"><div className="skeleton heading-skeleton" />{[1, 2, 3].map((item) => <div key={item} className="app-card"><div className="skeleton line-short" /><div className="skeleton line-full" /><div className="skeleton line-medium" /></div>)}</div>; }
