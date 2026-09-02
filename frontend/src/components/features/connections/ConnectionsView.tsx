"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Check, Clock3, PlugZap } from "lucide-react";
import { useState } from "react";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppCard } from "@/components/ui/AppCard";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppSegmentedControl } from "@/components/ui/AppSegmentedControl";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import type { SourceConnection } from "@/types/domain";

const statusCopy: Record<SourceConnection["connectionStatus"], string> = { connected: "Подключено", syncing: "Синхронизация", attention: "Нужно внимание", available: "Можно подключить", planned: "Запланировано" };
const submissionCopy: Record<SourceConnection["submissionType"], string> = { manual: "Ручная отправка", api: "API", browser_extension: "Расширение" };
const capabilityCopy = { collect: "поиск заказов", quick_apply: "быстрый отклик", autofill: "автозаполнение", requires_confirmation: "требуется подтверждение" } as const;

export function ConnectionsView() {
  const query = useQuery({ queryKey: ["sources"], queryFn: miniAppApi.sources });
  const [filter, setFilter] = useState<"active" | "planned" | "all">("active");
  if (query.isLoading) return <FeedSkeleton />;
  const sources = (query.data ?? []).filter((source) => filter === "all" || (filter === "active" ? source.enabled : !source.enabled && source.submissionType === "browser_extension"));
  return <><AppPageHeader title="Площадки" description="Источники заказов, состояние подключения и доступные способы отклика." /><AppSegmentedControl label="Фильтр площадок" value={filter} options={[{ value: "active", label: "Подключены" }, { value: "planned", label: "Расширение" }, { value: "all", label: "Все" }]} onChange={setFilter} />{query.isError ? <AppEmptyState title="Площадки недоступны" text="Не удалось получить состояние источников. Повторите позже." /> : sources.length ? <div className="connection-list">{sources.map((source) => <AppCard key={source.name} className="connection-row"><div className="connection-icon" data-status={source.connectionStatus}>{source.connectionStatus === "connected" ? <Check size={20} /> : source.connectionStatus === "attention" ? <AlertTriangle size={20} /> : source.connectionStatus === "syncing" ? <Clock3 size={20} /> : <PlugZap size={20} />}</div><div><div className="connection-title"><h2>{source.displayName}</h2><AppBadge tone={source.connectionStatus === "connected" ? "mint" : source.connectionStatus === "attention" ? "pink" : "blue"}>{statusCopy[source.connectionStatus]}</AppBadge></div><p>{submissionCopy[source.submissionType]}</p><ul className="capability-list">{source.capabilities.map((capability) => <li key={capability}><Check size={15} />{capabilityCopy[capability]}</li>)}</ul>{source.lastError && <p className="form-error">{source.lastError}</p>}</div></AppCard>)}</div> : <AppEmptyState title="Здесь пока пусто" text="Площадки появятся после настройки источников или расширения." />}</>;
}
