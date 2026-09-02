"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Puzzle } from "lucide-react";
import { useRef } from "react";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppLinkButton } from "@/components/ui/AppLinkButton";
import { AppNotice } from "@/components/ui/AppNotice";
import { miniAppApi } from "@/lib/api/client";
import { contactExtension } from "@/lib/extension/bridge";
import type { ApplicationCommandStatus } from "@/types/domain";

const activeStatuses = new Set<ApplicationCommandStatus>(["queued", "delivered", "opening_page", "waiting_for_auth", "page_ready", "form_found", "filling"]);
const statusCopy: Record<ApplicationCommandStatus, { label: string; text: string; tone: "blue" | "yellow" | "mint" | "pink" }> = {
  queued: { label: "В очереди", text: "Передаём отклик расширению.", tone: "blue" },
  delivered: { label: "Получено", text: "Расширение получило задачу.", tone: "blue" },
  opening_page: { label: "Открываем", text: "Загружаем страницу площадки.", tone: "blue" },
  waiting_for_auth: { label: "Нужен вход", text: "Войдите на площадку — затем продолжим автоматически.", tone: "yellow" },
  page_ready: { label: "Страница готова", text: "Ищем форму отклика.", tone: "blue" },
  form_found: { label: "Форма найдена", text: "Готовим поля.", tone: "blue" },
  filling: { label: "Заполняем", text: "Переносим текст и известные данные.", tone: "blue" },
  partially_filled: { label: "Нужно дополнить", text: "Часть обязательных полей оставлена вам.", tone: "pink" },
  ready_for_review: { label: "Можно проверить", text: "Проверьте форму и отправьте её на площадке.", tone: "mint" },
  submitted: { label: "Отправлено", text: "Площадка подтвердила отклик.", tone: "mint" },
  failed: { label: "Не готово", text: "Расширение не смогло закончить подготовку.", tone: "pink" },
  cancelled: { label: "Отменено", text: "Подготовка отменена.", tone: "yellow" },
  expired: { label: "Время вышло", text: "Запустите подготовку ещё раз.", tone: "yellow" },
};

export function ApplicationCommandPanel({ id, source, sourceUrl }: { id: number; source: string; sourceUrl: string | null }) {
  const client = useQueryClient();
  const sources = useQuery({ queryKey: ["sources"], queryFn: miniAppApi.sources });
  const extension = useQuery({ queryKey: ["extension-status"], queryFn: miniAppApi.extensionStatus, refetchInterval: 15_000 });
  const command = useQuery({
    queryKey: ["application-command", id],
    queryFn: () => miniAppApi.applicationCommand(id),
    refetchInterval: (query) => query.state.data && activeStatuses.has(query.state.data.status) ? 2_000 : false,
  });
  const sourceConfig = sources.data?.find((item) => item.name === source);
  const supported = sourceConfig?.submissionType === "browser_extension";
  const online = extension.data?.state === "CONNECTED";
  const idempotencyKey = useRef(crypto.randomUUID());
  const queue = useMutation({
    mutationFn: () => miniAppApi.queueApplication(id, idempotencyKey.current),
    onSuccess: async () => {
      idempotencyKey.current = crypto.randomUUID();
      await contactExtension({ type: "CHECK_NOW" });
      await client.invalidateQueries({ queryKey: ["application-command", id] });
    },
  });
  if (!supported) return null;
  const current = command.data;
  const copy = current ? statusCopy[current.status] : null;
  return (
    <AppCard tone={current?.status === "ready_for_review" || current?.status === "submitted" ? "mint" : "blue"}>
      <div className="split">
        <h2>Отклик в браузере</h2>
        <AppBadge tone={copy?.tone ?? (online ? "mint" : "yellow")}>{copy?.label ?? (online ? "Готово" : "Не на связи")}</AppBadge>
      </div>
      <p>{copy?.text ?? (online ? "Расширение заполнит форму и оставит отправку вам." : "Подключите расширение, чтобы перенести отклик на площадку.")}</p>
      {current?.result.attentionCount ? <p className="muted small">Проверить вручную: {current.result.attentionFields.join(", ")}.</p> : null}
      {current?.error?.message && <AppNotice tone="danger">{current.error.message}</AppNotice>}
      <div className="stack-actions">
        {!online ? <AppLinkButton href="/app/connections"><Puzzle size={18} /> Подключить расширение</AppLinkButton> : (!current || ["failed", "cancelled", "expired"].includes(current.status)) ? <AppButton disabled={queue.isPending || !sourceUrl} onClick={() => queue.mutate()}>{queue.isPending ? "Передаём…" : "Заполнить форму"}</AppButton> : null}
        {sourceUrl && current && <AppLinkButton href={sourceUrl} target="_blank" rel="noreferrer" variant="ghost">Открыть площадку <ExternalLink size={18} /></AppLinkButton>}
      </div>
      {queue.isError && <AppNotice tone="danger">{queue.error.message}</AppNotice>}
    </AppCard>
  );
}
