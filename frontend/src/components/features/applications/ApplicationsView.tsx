"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { useRouter } from "next/navigation";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppCard } from "@/components/ui/AppCard";
import { AppLinkButton } from "@/components/ui/AppLinkButton";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { leadStatusLabel } from "@/lib/copy/leads";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";

const activeStatuses = new Set(["approved", "contacted", "replied", "interview", "won", "lost"]);

export function ApplicationsView() {
  const router = useRouter();
  const query = useQuery({ queryKey: ["leads"], queryFn: async () => (await miniAppApi.leads()).map((item) => mapLeadDtoToLead(item as never)) });
  if (query.isLoading) return <FeedSkeleton />;
  const applications = (query.data ?? []).filter((lead) => activeStatuses.has(lead.status));
  return (
    <>
      <AppPageHeader title="Отклики" description="Черновики, отправленные отклики и ответы в одной истории." />
      {query.isError ? <AppEmptyState title="Не удалось загрузить отклики" text="Проверьте соединение и повторите запрос." action="Повторить" onAction={() => void query.refetch()} /> : applications.length ? <AppCard className="application-board"><div className="application-head"><span>Заказ</span><span>Статус</span><span>Источник</span><span /></div>{applications.map((lead) => <div className="application-row" key={lead.id}><div><strong>{lead.title}</strong><small>{lead.budgetLabel}</small></div><AppBadge tone={lead.status === "won" ? "mint" : lead.status === "lost" ? "neutral" : "yellow"}>{leadStatusLabel[lead.status]}</AppBadge><span>{lead.source}</span><AppLinkButton href={`/app/applications/${lead.id}`} variant="ghost" aria-label={`Открыть отклик: ${lead.title}`}><ArrowRight size={18} /></AppLinkButton></div>)}</AppCard> : <AppEmptyState title="Откликов пока нет" text="Откройте подходящий заказ и подготовьте первый черновик." action="Перейти к заказам" onAction={() => router.push("/app/orders")} />}
    </>
  );
}
