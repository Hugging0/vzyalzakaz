import { useQuery } from "@tanstack/react-query";

import { AppCard } from "@/components/ui/AppCard";
import { AppEmptyState } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";

const labels = [{ key: "relevant", label: "Подобрано" }, { key: "sent", label: "Отправлено" }, { key: "replied", label: "Ответили" }, { key: "won", label: "Выиграно" }] as const;
export function AnalyticsView() {
  const query = useQuery({ queryKey: ["analytics"], queryFn: miniAppApi.analytics });
  return <><header className="app-header"><div><h1>Статистика</h1><p>Только подтверждённые действия и результаты</p></div></header>{query.isError ? <AppEmptyState title="Статистика пока недоступна" text="Попробуйте обновить экран позже." /> : <><div className="metric-grid">{labels.map(({ key, label }) => <AppCard key={key}><div className="metric-value">{query.data?.[key] ?? "—"}</div><div className="small muted">{label}</div></AppCard>)}</div><AppCard className="analytics-note"><strong>Воронка появится по мере работы</strong><p className="small muted">Здесь будут видны только лиды, с которыми вы действительно взаимодействовали.</p></AppCard></>}</>;
}
