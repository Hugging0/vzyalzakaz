"use client";

import { useQuery } from "@tanstack/react-query";

import { OrderListItem } from "@/components/features/orders/OrderListItem";
import { AppCard } from "@/components/ui/AppCard";
import { AppLinkButton } from "@/components/ui/AppLinkButton";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppStat } from "@/components/ui/AppStat";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";
import type { Profile } from "@/types/domain";

export function TodayView({ profile }: { profile: Profile }) {
  const leads = useQuery({ queryKey: ["leads"], queryFn: async () => (await miniAppApi.leads()).map((item) => mapLeadDtoToLead(item as never)) });
  const analytics = useQuery({ queryKey: ["analytics"], queryFn: miniAppApi.analytics });
  if (leads.isLoading || analytics.isLoading) return <FeedSkeleton />;
  const shortlist = (leads.data ?? []).filter((lead) => lead.status === "recommended").slice(0, 3);
  return (
    <>
      <AppPageHeader title="Главная" description="Сильные заказы и действия, которые ждут вашего решения." actions={<AppLinkButton href="/app/orders" variant="secondary">Все заказы</AppLinkButton>} />
      <section className="today-overview">
        <AppCard className="agent-panel" tone={profile.isActive ? "mint" : "yellow"}><div><span>Состояние агента</span><h2>{profile.isActive ? "Поиск работает" : "Поиск на паузе"}</h2><p>{profile.isActive ? `Уведомления приходят от ${profile.matchThreshold}/100.` : "Новые рекомендации и уведомления остановлены."}</p></div><AppLinkButton href="/app/settings" variant="ghost">Настроить</AppLinkButton></AppCard>
        <AppCard className="today-stats"><AppStat label="Проверено" value={analytics.data?.scanned ?? 0} /><AppStat label="Подобрано" value={analytics.data?.relevant ?? 0} /><AppStat label="Ждут решения" value={analytics.data?.pendingActions ?? 0} /></AppCard>
      </section>
      <div className="section-heading"><h2>Лучшие заказы</h2><AppLinkButton href="/app/orders" variant="ghost">Открыть поиск</AppLinkButton></div>
      {shortlist.length ? <div className="order-list compact">{shortlist.map((lead) => <OrderListItem key={lead.id} lead={lead} />)}</div> : <AppEmptyState title="Сильных заказов пока нет" text="Агент продолжает проверять источники. Новые совпадения появятся здесь." />}
    </>
  );
}
