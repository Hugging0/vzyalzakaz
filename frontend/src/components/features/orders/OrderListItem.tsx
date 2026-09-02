import { ExternalLink } from "lucide-react";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppCard } from "@/components/ui/AppCard";
import { AppIconLink } from "@/components/ui/AppIconLink";
import { AppLinkButton } from "@/components/ui/AppLinkButton";
import { leadStatusLabel } from "@/lib/copy/leads";
import type { Lead } from "@/types/domain";

function freshness(publishedAt: string | null): string {
  if (!publishedAt) return "Недавно";
  const hours = Math.max(0, Math.round((Date.now() - Date.parse(publishedAt)) / 3_600_000));
  if (hours < 1) return "Только что";
  if (hours < 24) return `${hours} ч назад`;
  return new Intl.DateTimeFormat("ru", { day: "numeric", month: "short" }).format(new Date(publishedAt));
}

export function OrderListItem({ lead }: { lead: Lead }) {
  const tone = lead.matchScore >= 90 ? "pink" : lead.matchScore >= 80 ? "yellow" : "blue";
  return (
    <AppCard className="order-row" tone={tone}>
      <div className="order-score"><strong>{lead.matchScore}/100</strong><span>{lead.strengthLabel}</span></div>
      <div className="order-main">
        <div className="order-meta"><AppBadge>{freshness(lead.publishedAt)}</AppBadge><span>{lead.source}</span><span>{lead.budgetLabel}</span></div>
        <h2>{lead.title}</h2>
        <p>{lead.recommendationReasons[0]?.text ?? lead.fitReasons[0]}</p>
        <div className="order-status"><span>{leadStatusLabel[lead.status]}</span>{lead.applyMode === "api_allowed" && <AppBadge tone="mint">API</AppBadge>}</div>
      </div>
      <div className="order-actions"><AppLinkButton href={`/app/orders/${lead.id}`}>Открыть заказ</AppLinkButton>{lead.sourceUrl && <AppIconLink href={lead.sourceUrl} label="Открыть источник"><ExternalLink size={19} /></AppIconLink>}</div>
    </AppCard>
  );
}
