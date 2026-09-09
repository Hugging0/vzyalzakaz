"use client";

import { useQuery } from "@tanstack/react-query";
import { OrderListItem } from "@/components/features/orders/OrderListItem";
import { AppLinkButton } from "@/components/ui/AppLinkButton";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";
import type { Profile } from "@/types/domain";

export function TodayView({ profile }: { profile: Profile }) {
  const leads = useQuery({ queryKey: ["leads"], queryFn: async () => (await miniAppApi.leads()).map((item) => mapLeadDtoToLead(item as never)) });
  if (leads.isLoading) return <FeedSkeleton />;
  const shortlist = (leads.data ?? []).filter((lead) => lead.status === "recommended").slice(0, 5);
  return <>
    <AppPageHeader title="Для вас" description="Посмотрите задачи и выберите, на какие стоит откликнуться." actions={<AppLinkButton href="/app/orders" variant="secondary">Все заказы</AppLinkButton>} />
    {!profile.isActive && <AppNotice tone="warning">Поиск на паузе. Возобновить его можно в настройках.</AppNotice>}
    {leads.isError ? <AppEmptyState title="Не удалось загрузить заказы" text="Проверьте соединение и повторите запрос." action="Повторить" onAction={() => void leads.refetch()} /> : shortlist.length ? <div className="order-list">{shortlist.map((lead) => <OrderListItem key={lead.id} lead={lead} />)}</div> : <AppEmptyState title="Новых рекомендаций пока нет" text="Сохранённые отклики доступны в разделе «Отклики». Новые задачи появятся после проверки источников." />}
  </>;
}
