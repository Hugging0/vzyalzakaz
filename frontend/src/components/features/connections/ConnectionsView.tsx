"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Check, Clock3, Copy, PlugZap, Puzzle, Unplug } from "lucide-react";
import { useState } from "react";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppSegmentedControl } from "@/components/ui/AppSegmentedControl";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import { contactExtension } from "@/lib/extension/bridge";
import type { SourceConnection } from "@/types/domain";

const statusCopy: Record<SourceConnection["connectionStatus"], string> = { connected: "Подключено", syncing: "Синхронизация", attention: "Нужно внимание", available: "Можно подключить", planned: "Запланировано" };
const submissionCopy: Record<SourceConnection["submissionType"], string> = { manual: "Ручная отправка", api: "API", browser_extension: "Заполнение в браузере" };
const capabilityCopy: Record<SourceConnection["capabilities"][number], string> = {
  collect: "поиск заказов",
  quick_apply: "быстрый отклик",
  browser_autofill: "автозаполнение",
  attachments: "вложения",
  custom_questions: "вопросы площадки",
  requires_auth: "нужен вход",
  requires_confirmation: "отправка после проверки",
};

export function ConnectionsView() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["sources"], queryFn: miniAppApi.sources });
  const extension = useQuery({ queryKey: ["extension-status"], queryFn: miniAppApi.extensionStatus, refetchInterval: 15_000 });
  const [filter, setFilter] = useState<"active" | "extension" | "all">("active");
  const [linkCode, setLinkCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const createLink = useMutation({
    mutationFn: miniAppApi.createExtensionLink,
    onSuccess: async ({ code }) => {
      setCopied(false);
      setLinkCode(code);
      if (await contactExtension({ type: "LINK", code })) {
        setLinkCode(null);
        await client.invalidateQueries({ queryKey: ["extension-status"] });
      }
    },
  });
  const disconnect = useMutation({
    mutationFn: miniAppApi.disconnectExtension,
    onSuccess: () => client.invalidateQueries({ queryKey: ["extension-status"] }),
  });

  if (query.isLoading) return <FeedSkeleton />;
  const sources = (query.data ?? []).filter((source) => {
    if (filter === "all") return true;
    if (filter === "extension") return source.submissionType === "browser_extension";
    return source.enabled;
  });
  return (
    <>
      <AppPageHeader title="Площадки" description="Поиск заказов и подготовка откликов." />
      <ExtensionConnectionCard
        state={extension.data?.state}
        installationId={extension.data?.installations[0]?.id}
        activeSourceId={extension.data?.installations[0]?.activeSourceId}
        marketplaceAuthState={extension.data?.installations[0]?.marketplaceAuthState}
        linkCode={linkCode}
        copied={copied}
        busy={createLink.isPending || disconnect.isPending}
        onConnect={() => createLink.mutate()}
        onDisconnect={(id) => disconnect.mutate(id)}
        onCopy={async () => {
          if (!linkCode) return;
          await navigator.clipboard.writeText(linkCode);
          setCopied(true);
        }}
      />
      {(createLink.isError || disconnect.isError || extension.isError) && <AppNotice tone="danger">Не удалось обновить подключение расширения.</AppNotice>}
      <AppSegmentedControl
        label="Фильтр площадок"
        value={filter}
        options={[{ value: "active", label: "Активные" }, { value: "extension", label: "С расширением" }, { value: "all", label: "Все" }]}
        onChange={setFilter}
      />
      {query.isError ? <AppEmptyState title="Площадки недоступны" text="Не удалось получить состояние источников. Повторите позже." /> : sources.length ? (
        <div className="connection-list">{sources.map((source) => <SourceCard key={source.name} source={source} />)}</div>
      ) : <AppEmptyState title="Здесь пока пусто" text="Площадки появятся после настройки источников." />}
    </>
  );
}

function ExtensionConnectionCard({
  state,
  installationId,
  activeSourceId,
  marketplaceAuthState,
  linkCode,
  copied,
  busy,
  onConnect,
  onDisconnect,
  onCopy,
}: {
  state?: "CONNECTED" | "OFFLINE" | "NOT_DETECTED" | "ERROR";
  installationId?: string;
  activeSourceId?: string | null;
  marketplaceAuthState?: "AUTHENTICATED" | "AUTH_REQUIRED" | "UNKNOWN" | "UNSUPPORTED" | null;
  linkCode: string | null;
  copied: boolean;
  busy: boolean;
  onConnect: () => void;
  onDisconnect: (id: string) => void;
  onCopy: () => void;
}) {
  const online = state === "CONNECTED";
  return (
    <AppCard tone={online ? "mint" : "yellow"} className="extension-connect-card">
      <div className="connection-icon" data-status={online ? "connected" : "attention"}><Puzzle size={22} /></div>
      <div>
        <div className="connection-title"><h2>Расширение для откликов</h2><AppBadge tone={online ? "mint" : "yellow"}>{online ? "На связи" : state === "OFFLINE" ? "Не в сети" : "Не подключено"}</AppBadge></div>
        <p>Заполняет форму на Freelancer, Freelance.ru, FL.ru и Kwork. Отправляете вы.</p>
        {online && activeSourceId && <p className="muted small">Текущая площадка: {activeSourceId.replaceAll("_", ".")}.</p>}
        {marketplaceAuthState === "AUTH_REQUIRED" && <AppNotice tone="warning">На текущей площадке нужно войти в аккаунт.</AppNotice>}
        {linkCode && <div className="extension-code"><code>{linkCode}</code><AppButton variant="ghost" onClick={onCopy}><Copy size={18} /> {copied ? "Скопировано" : "Копировать"}</AppButton></div>}
        <div className="inline-actions">
          {!online && <AppButton disabled={busy} onClick={onConnect}>{busy ? "Создаём код…" : linkCode ? "Новый код" : "Подключить"}</AppButton>}
          {installationId && <AppButton variant="danger" disabled={busy} onClick={() => onDisconnect(installationId)}><Unplug size={18} /> Отключить</AppButton>}
        </div>
        {linkCode && <AppNotice tone="warning">Код действует 5 минут и используется один раз. Вставьте его во всплывающее окно расширения.</AppNotice>}
      </div>
    </AppCard>
  );
}

function SourceCard({ source }: { source: SourceConnection }) {
  return (
    <AppCard className="connection-row">
      <div className="connection-icon" data-status={source.connectionStatus}>
        {source.connectionStatus === "connected" ? <Check size={20} /> : source.connectionStatus === "attention" ? <AlertTriangle size={20} /> : source.connectionStatus === "syncing" ? <Clock3 size={20} /> : <PlugZap size={20} />}
      </div>
      <div>
        <div className="connection-title"><h2>{source.displayName}</h2><AppBadge tone={source.connectionStatus === "connected" ? "mint" : source.connectionStatus === "attention" ? "pink" : "blue"}>{statusCopy[source.connectionStatus]}</AppBadge></div>
        <p>{submissionCopy[source.submissionType]}</p>
        <ul className="capability-list">{source.capabilities.map((capability) => <li key={capability}><Check size={15} />{capabilityCopy[capability]}</li>)}</ul>
        {source.lastError && <p className="form-error">{source.lastError}</p>}
      </div>
    </AppCard>
  );
}
