import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { useState } from "react";

import { LeadCard } from "@/components/features/lead-feed/LeadCard";
import { AppButton } from "@/components/ui/AppButton";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";
import type { Lead } from "@/types/domain";

export function LeadFeedView({ onOpen }: { onOpen: (lead: Lead) => void }) {
  const queryClient = useQueryClient();
  const [minimumScore, setMinimumScore] = useState(0);
  const leadsQuery = useQuery({ queryKey: ["leads"], queryFn: async () => (await miniAppApi.leads()).map((item) => mapLeadDtoToLead(item as never)) });
  const skip = useMutation({ mutationFn: miniAppApi.skipLead, onSuccess: () => queryClient.invalidateQueries({ queryKey: ["leads"] }) });
  if (leadsQuery.isLoading) return <FeedSkeleton />;
  if (leadsQuery.isError) return <AppEmptyState title="Не удалось загрузить ленту" text="Проверьте соединение и попробуйте ещё раз." action="Повторить" onAction={() => leadsQuery.refetch()} />;
  const leads = (leadsQuery.data ?? []).filter((lead) => lead.matchScore >= minimumScore && lead.status !== "skipped");
  return <><header className="app-header"><div><h1>Сильные совпадения</h1><p>Агент отобрал возможности для вашего профиля</p></div><AppButton variant="ghost" aria-label="Показать фильтр" onClick={() => setMinimumScore(minimumScore ? 0 : 80)}><SlidersHorizontal size={18} /></AppButton></header>
    {minimumScore > 0 && <div className="active-filter">Показаны лиды от {minimumScore}% <button onClick={() => setMinimumScore(0)}>Сбросить</button></div>}
    {leads.length ? <div className="stack">{leads.map((lead) => <LeadCard key={lead.id} lead={lead} onOpen={() => onOpen(lead)} onSkip={() => skip.mutate(lead.id)} />)}</div> : <AppEmptyState title="Сильных совпадений пока нет" text="Агент продолжает поиск. Можно расширить навыки или снизить порог." />}
  </>;
}
