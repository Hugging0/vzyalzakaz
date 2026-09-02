"use client";

import { useQuery } from "@tanstack/react-query";
import { SlidersHorizontal } from "lucide-react";
import { useMemo, useState } from "react";

import { OrderListItem } from "@/components/features/orders/OrderListItem";
import { AppCard } from "@/components/ui/AppCard";
import { AppField } from "@/components/ui/AppField";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppRangeField } from "@/components/ui/AppRangeField";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";

export function OrdersView() {
  const [minimumScore, setMinimumScore] = useState(60);
  const [source, setSource] = useState("");
  const query = useQuery({ queryKey: ["leads"], queryFn: async () => (await miniAppApi.leads()).map((item) => mapLeadDtoToLead(item as never)) });
  const sources = useMemo(() => Array.from(new Set((query.data ?? []).map((lead) => lead.source))).sort(), [query.data]);
  const leads = useMemo(() => (query.data ?? []).filter((lead) => lead.status !== "skipped" && lead.matchScore >= minimumScore && (!source || lead.source === source)), [minimumScore, query.data, source]);
  if (query.isLoading) return <FeedSkeleton />;
  return (
    <>
      <AppPageHeader title="Заказы" description="Все найденные проекты с объяснением совпадения и текущим статусом." />
      <AppCard className="filter-bar">
        <div className="filter-title"><SlidersHorizontal size={20} /><strong>Фильтры</strong></div>
        <AppRangeField id="orders-score" label="Совпадение от" value={minimumScore} min={60} max={95} onChange={setMinimumScore} />
        <AppField label="Источник" htmlFor="orders-source"><select id="orders-source" className="app-input" value={source} onChange={(event) => setSource(event.target.value)}><option value="">Все источники</option>{sources.map((item) => <option value={item} key={item}>{item}</option>)}</select></AppField>
      </AppCard>
      {query.isError ? <AppEmptyState title="Не удалось загрузить заказы" text="Проверьте соединение и повторите запрос." action="Повторить" onAction={() => void query.refetch()} /> : leads.length ? <div className="order-list">{leads.map((lead) => <OrderListItem key={lead.id} lead={lead} />)}</div> : <AppEmptyState title="Заказов по этим фильтрам нет" text="Снизьте порог совпадения или выберите другой источник." />}
    </>
  );
}
