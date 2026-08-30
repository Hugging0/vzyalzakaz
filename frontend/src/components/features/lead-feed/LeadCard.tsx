import { ExternalLink, Sparkles } from "lucide-react";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { leadStatusLabel } from "@/lib/copy/leads";
import type { Lead } from "@/types/domain";

function freshness(publishedAt: string | null): string {
  if (!publishedAt) return "недавно";
  const hours = Math.max(0, Math.round((Date.now() - Date.parse(publishedAt)) / 3_600_000));
  return hours < 1 ? "только что" : hours < 24 ? `${hours} ч назад` : new Intl.DateTimeFormat("ru", { day: "numeric", month: "short" }).format(new Date(publishedAt));
}

export function LeadCard({ lead, onOpen, onSkip }: { lead: Lead; onOpen: () => void; onSkip: () => void }) {
  const awaitingDecision = lead.status === "recommended" || lead.status === "approved";
  return <AppCard className="lead-card"><div className="split"><span className="match-score"><Sparkles size={14} /> {lead.matchScore}% совпадение</span><span className="small muted">{freshness(lead.publishedAt)}</span></div>
    <h2>{lead.title}</h2><p className="lead-meta">{lead.budgetLabel} · {lead.source}</p>
    <p className="lead-reason">{lead.fitReasons[0]}</p>
    {!awaitingDecision && <span className="status-label">{leadStatusLabel[lead.status]}</span>}
    <div className="lead-actions"><AppButton onClick={onOpen}>{awaitingDecision ? (lead.proposal ? "Проверить отклик" : "Открыть") : "Подробнее"}</AppButton>{awaitingDecision && <AppButton variant="ghost" onClick={onSkip}>Пропустить</AppButton>}</div>
    {lead.sourceUrl && <a className="original-link" href={lead.sourceUrl} target="_blank" rel="noreferrer">Оригинал <ExternalLink size={14} /></a>}
  </AppCard>;
}
