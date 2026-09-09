"use client";

import { useQuery } from "@tanstack/react-query";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo } from "react";

import { OrderListItem } from "@/components/features/orders/OrderListItem";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppField } from "@/components/ui/AppField";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";

export function OrdersView() {
  const params = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();
  const source = params.get("source") ?? "";
  const sort = params.get("sort") ?? "recommended";
  const update = (key: string, value: string) => {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    router.replace(`${pathname}${next.size ? `?${next}` : ""}`, { scroll: false });
  };
  const query = useQuery({ queryKey: ["leads"], queryFn: async () => (await miniAppApi.leads()).map((item) => mapLeadDtoToLead(item as never)) });
  const recommendations = useMemo(() => (query.data ?? []).filter((lead) => lead.status === "recommended"), [query.data]);
  const sources = useMemo(() => Array.from(new Set(recommendations.map((lead) => lead.source))).sort(), [recommendations]);
  const leads = useMemo(() => {
    const result = recommendations.filter((lead) => !source || lead.source === source);
    if (sort === "newest") result.sort((a, b) => Date.parse(b.publishedAt ?? b.createdAt) - Date.parse(a.publishedAt ?? a.createdAt));
    return result;
  }, [recommendations, source, sort]);
  if (query.isLoading) return <FeedSkeleton />;
  const returnTo = `${pathname}${params.size ? `?${params}` : ""}`;
  return (
    <>
      <AppPageHeader title="Заказы" description="Задачи по вашему профилю. Выберите заказ, чтобы изучить условия и подготовить отклик." />
      <AppCard className="filter-bar">
        <AppField label="Источник" htmlFor="orders-source"><select id="orders-source" className="app-input" value={source} onChange={(event) => update("source", event.target.value)}><option value="">Все источники</option>{sources.map((item) => <option value={item} key={item}>{item}</option>)}{source && !sources.includes(source) && <option value={source}>{source}</option>}</select></AppField>
        <AppField label="Показывать сначала" htmlFor="orders-sort"><select id="orders-sort" className="app-input" value={sort} onChange={(event) => update("sort", event.target.value)}><option value="recommended">Рекомендуемые</option><option value="newest">Новые</option></select></AppField>
        {source && <AppButton variant="ghost" onClick={() => update("source", "")}>Сбросить источник</AppButton>}
      </AppCard>
      {query.isError ? <AppEmptyState title="Не удалось загрузить заказы" text="Проверьте соединение и повторите запрос." action="Повторить" onAction={() => void query.refetch()} /> : leads.length ? <div className="order-list">{leads.map((lead) => <OrderListItem key={lead.id} lead={lead} returnTo={returnTo} />)}</div> : <AppEmptyState title={source ? "Из этого источника заказов пока нет" : "Новых рекомендаций пока нет"} text={source ? "Посмотрите задачи из остальных источников." : "Сохранённые отклики доступны в разделе «Отклики». Новые задачи появятся после проверки источников."} action={source ? "Все источники" : undefined} onAction={source ? () => update("source", "") : undefined} />}
    </>
  );
}
