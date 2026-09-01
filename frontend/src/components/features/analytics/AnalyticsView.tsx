import { useQuery } from "@tanstack/react-query";

import { AppCard } from "@/components/ui/AppCard";
import { AppEmptyState } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";

const labels = [{ key: "relevant", label: "Подобрано" }, { key: "sent", label: "Отправлено" }, { key: "replied", label: "Ответили" }, { key: "won", label: "Выиграно" }] as const;
export function AnalyticsView() {
  const query = useQuery({ queryKey: ["analytics"], queryFn: miniAppApi.analytics });
  return <><header className="app-header"><div><h1>Результаты</h1></div></header>{query.isError ? <AppEmptyState title="Статистика пока недоступна" text="Попробуйте обновить экран позже." /> : <><AppCard className="metric-board" tone="yellow"><div className="metric-list">{labels.map(({ key, label }) => <div className="metric-item" key={key}><span>{label}</span><strong>{query.data?.[key] ?? "—"}</strong></div>)}</div></AppCard>{(query.data?.relevant ?? 0) === 0 && <AppCard className="analytics-note" tone="blue"><strong>Воронка появится после первых действий</strong><p className="small muted">Проект → отклик → ответ → заказ.</p></AppCard>}</>}</>;
}
