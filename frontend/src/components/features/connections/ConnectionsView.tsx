"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, BriefcaseBusiness, Check, Clock3, Copy, Download, PlugZap, Puzzle, RefreshCw, Unplug } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppCheckbox } from "@/components/ui/AppCheckbox";
import { AppField } from "@/components/ui/AppField";
import { AppLinkButton } from "@/components/ui/AppLinkButton";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppSegmentedControl } from "@/components/ui/AppSegmentedControl";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import { contactExtension } from "@/lib/extension/bridge";
import type { HHConnection, SourceConnection } from "@/types/domain";

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
  const searchParams = useSearchParams();
  const query = useQuery({ queryKey: ["sources"], queryFn: miniAppApi.sources });
  const extension = useQuery({ queryKey: ["extension-status"], queryFn: miniAppApi.extensionStatus, refetchInterval: 15_000 });
  const hh = useQuery({ queryKey: ["hh-connection"], queryFn: miniAppApi.hhConnection });
  const [filter, setFilter] = useState<"active" | "extension" | "all">("active");
  const [linkCode, setLinkCode] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [hhAgreement, setHHAgreement] = useState(false);
  const hhReturn = searchParams.get("hh");
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
  const connectHH = useMutation({
    mutationFn: () => miniAppApi.startHHOAuth(hhAgreement),
    onSuccess: ({ authorizeUrl }) => window.location.assign(authorizeUrl),
  });
  const refreshHH = useMutation({
    mutationFn: miniAppApi.refreshHHResumes,
    onSuccess: () => client.invalidateQueries({ queryKey: ["hh-connection"] }),
  });
  const selectResume = useMutation({
    mutationFn: miniAppApi.selectHHResume,
    onSuccess: () => client.invalidateQueries({ queryKey: ["hh-connection"] }),
  });
  const disconnectHH = useMutation({
    mutationFn: miniAppApi.disconnectHH,
    onSuccess: () => client.invalidateQueries({ queryKey: ["hh-connection"] }),
  });

  if (query.isLoading || hh.isLoading) return <FeedSkeleton />;
  const sources = (query.data ?? []).filter((source) => {
    if (source.name === "hh_ru") return false;
    if (filter === "all") return true;
    if (filter === "extension") return source.submissionType === "browser_extension";
    return source.enabled;
  });
  return (
    <>
      <AppPageHeader title="Площадки" description="Поиск заказов и подготовка откликов." />
      <HHConnectionCard
        connection={hh.data}
        agreement={hhAgreement}
        busy={connectHH.isPending || refreshHH.isPending || selectResume.isPending || disconnectHH.isPending}
        onAgreement={setHHAgreement}
        onConnect={() => connectHH.mutate()}
        onRefresh={() => refreshHH.mutate()}
        onSelect={(id) => selectResume.mutate(id)}
        onDisconnect={() => disconnectHH.mutate()}
      />
      {hhReturn === "connected" && <AppNotice tone="success">HH подключён. Проверьте основное резюме.</AppNotice>}
      {hhReturn === "cancelled" && <AppNotice tone="warning">Подключение HH отменено.</AppNotice>}
      {hhReturn === "error" && <AppNotice tone="danger">HH не удалось подключить. Начните ещё раз.</AppNotice>}
      {(hh.isError || connectHH.isError || refreshHH.isError || selectResume.isError || disconnectHH.isError) && <AppNotice tone="danger">Не удалось обновить подключение HH.</AppNotice>}
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

function HHConnectionCard({ connection, agreement, busy, onAgreement, onConnect, onRefresh, onSelect, onDisconnect }: {
  connection?: HHConnection;
  agreement: boolean;
  busy: boolean;
  onAgreement: (value: boolean) => void;
  onConnect: () => void;
  onRefresh: () => void;
  onSelect: (id: string) => void;
  onDisconnect: () => void;
}) {
  const connected = connection?.status === "connected";
  const needsAuth = connection?.status === "reauth_required";
  const hasError = connection?.status === "error";
  return (
    <AppCard tone={connected ? "mint" : needsAuth ? "yellow" : hasError ? "pink" : "blue"} className="extension-connect-card">
      <div className="connection-icon" data-status={connected ? "connected" : needsAuth || hasError ? "attention" : "available"}><BriefcaseBusiness size={22} /></div>
      <div>
        <div className="connection-title"><h2>HH</h2><AppBadge tone={connected ? "mint" : needsAuth || hasError ? "pink" : "blue"}>{connected ? "Подключено" : needsAuth ? "Нужен вход" : hasError ? "Ошибка" : "Не подключено"}</AppBadge></div>
        <p>{connected ? `Аккаунт ${connection.accountName || "подключён"}.` : "Официальный API для поиска и отправки откликов."}</p>
        {connected ? (
          <>
            <AppField label="Основное резюме" htmlFor="hh-resume">
              <select id="hh-resume" className="app-input" value={connection.selectedResumeId ?? ""} disabled={busy} onChange={(event) => onSelect(event.target.value)}>
                <option value="" disabled>Выберите резюме</option>
                {connection.resumes.map((resume) => <option key={resume.id} value={resume.id}>{resume.title}</option>)}
              </select>
            </AppField>
            {!connection.resumes.length && <AppNotice tone="warning">В аккаунте нет доступных резюме.</AppNotice>}
            <div className="inline-actions">
              <AppButton variant="ghost" disabled={busy} onClick={onRefresh}><RefreshCw size={18} /> Обновить</AppButton>
              <AppButton variant="danger" disabled={busy} onClick={onDisconnect}><Unplug size={18} /> Отключить</AppButton>
            </div>
          </>
        ) : (
          <>
            <AppCheckbox checked={agreement} onChange={onAgreement} label={<span>Принимаю <a href="https://hh.ru/account/agreement" target="_blank" rel="noreferrer">соглашение об оказании услуг по содействию в трудоустройстве</a>.</span>} />
            <AppButton disabled={busy || !agreement || !connection?.configured} onClick={onConnect}>{busy ? "Открываем HH…" : needsAuth || hasError ? "Подключить снова" : "Подключить HH"}</AppButton>
            {!connection?.configured && <AppNotice tone="warning">Владелец сервиса ещё не настроил HH OAuth.</AppNotice>}
          </>
        )}
      </div>
    </AppCard>
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
        {!online && (
          <ol className="extension-install-steps">
            <li>Скачайте и распакуйте архив.</li>
            <li>Откройте страницу расширений браузера, включите режим разработчика и загрузите распакованную папку.</li>
            <li>Получите код ниже и вставьте его в расширение.</li>
          </ol>
        )}
        {linkCode && <div className="extension-code"><code>{linkCode}</code><AppButton variant="ghost" onClick={onCopy}><Copy size={18} /> {copied ? "Скопировано" : "Копировать"}</AppButton></div>}
        <div className="inline-actions">
          {!online && <AppLinkButton href="/downloads/vzyalzakaz-extension-chromium.zip" download prefetch={false}><Download size={18} /> Chrome / Яндекс</AppLinkButton>}
          {!online && <AppButton variant="secondary" disabled={busy} onClick={onConnect}>{busy ? "Создаём код…" : linkCode ? "Новый код" : "Получить код"}</AppButton>}
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
