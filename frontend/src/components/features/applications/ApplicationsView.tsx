import { useQuery } from "@tanstack/react-query";

import { AppCard } from "@/components/ui/AppCard";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { leadStatusLabel } from "@/lib/copy/leads";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";

const activeStatuses = new Set(["approved", "contacted", "replied", "interview"]);
export function ApplicationsView() {
  const query = useQuery({ queryKey: ["leads"], queryFn: async () => (await miniAppApi.leads()).map((item) => mapLeadDtoToLead(item as never)) });
  if (query.isLoading) return <FeedSkeleton />;
  const applications = query.data?.filter((lead) => activeStatuses.has(lead.status)) ?? [];
  return <><header className="app-header"><div><h1>Отклики</h1><p>Взаимодействия, которые требуют внимания</p></div></header>{applications.length ? <div className="stack">{applications.map((lead) => <AppCard key={lead.id}><div className="split"><strong>{lead.title}</strong><span className="status-label">{leadStatusLabel[lead.status]}</span></div><p className="lead-meta">{lead.source} · {lead.budgetLabel}</p></AppCard>)}</div> : <AppEmptyState title="Вы ещё не отправляли отклики" text="Подходящие лиды появятся в ленте — там можно подготовить текст и зафиксировать отправку." />}</>;
}
