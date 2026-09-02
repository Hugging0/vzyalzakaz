"use client";

import { useQuery } from "@tanstack/react-query";

import { AppCard } from "@/components/ui/AppCard";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppStat } from "@/components/ui/AppStat";
import { AppEmptyState } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";

export function AnalyticsView() {
  const query = useQuery({ queryKey: ["analytics"], queryFn: miniAppApi.analytics });
  if (query.isError) return <><AppPageHeader title="Статистика" /><AppEmptyState title="Статистика пока недоступна" text="Попробуйте обновить страницу позже." /></>;
  const data = query.data;
  return <><AppPageHeader title="Статистика" description="Результаты поиска и прохождение откликов по воронке." /><AppCard className="analytics-summary" tone="yellow"><AppStat label="Найдено" value={data?.relevant ?? 0} /><AppStat label="Отправлено" value={data?.sent ?? 0} /><AppStat label="Ответили" value={data?.replied ?? 0} /><AppStat label="Интервью" value={data?.interviews ?? 0} /><AppStat label="Выиграно" value={data?.won ?? 0} /></AppCard><div className="analytics-grid"><AppCard><h2>Эффективность</h2><div className="metric-pairs"><AppStat label="Ответы" value={`${data?.responseRate ?? 0}%`} /><AppStat label="Экономия времени" value={`${data?.estimatedTimeSavedMinutes ?? 0} мин`} hint="Оценка: 10 минут на подготовленный черновик" /></div></AppCard><AppCard tone="blue"><h2>Лучшие источники</h2>{data?.topSources.length ? <ol className="ranked-list">{data.topSources.map((item) => <li key={item.source}><span>{item.source}</span><strong>{item.count}</strong></li>)}</ol> : <p>Источники появятся после первых рекомендаций.</p>}</AppCard></div>{(data?.relevant ?? 0) === 0 && <AppEmptyState title="Воронка пока пуста" text="Она заполнится после первых подобранных заказов и откликов." />}</>;
}
