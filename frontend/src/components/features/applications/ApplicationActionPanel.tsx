"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Puzzle, Send } from "lucide-react";
import { useRef } from "react";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppLinkButton } from "@/components/ui/AppLinkButton";
import { AppNotice } from "@/components/ui/AppNotice";
import { miniAppApi } from "@/lib/api/client";
import { contactExtension } from "@/lib/extension/bridge";

const active = new Set(["processing", "queued", "delivered", "opening_page", "page_ready", "form_found", "filling"]);
const successful = new Set(["submitted", "already_applied"]);

export function ApplicationActionPanel({ id }: { id: number }) {
  const client = useQueryClient();
  const extension = useQuery({ queryKey: ["extension-status"], queryFn: miniAppApi.extensionStatus, refetchInterval: 15_000 });
  const action = useQuery({
    queryKey: ["application", id],
    queryFn: () => miniAppApi.application(id),
    refetchInterval: (query) => {
      const data = query.state.data;
      return data && (active.has(data.status) || (data.command && active.has(data.command.status))) ? 2_000 : false;
    },
  });
  const key = useRef(crypto.randomUUID());
  const submit = useMutation({
    mutationFn: () => miniAppApi.submitApplication(id, key.current),
    onSuccess: async (result) => {
      if (result.status === "failed") key.current = crypto.randomUUID();
      if (result.command) await contactExtension({ type: "CHECK_NOW" });
      await client.invalidateQueries({ queryKey: ["application", id] });
    },
  });
  if (action.isLoading) return null;
  if (action.isError) return <AppNotice tone="danger">Не удалось получить способ отклика.</AppNotice>;
  const current = action.data;
  if (!current) return null;
  const done = successful.has(current.status);
  const needsExtension = Boolean(current.command) || current.provider === "browser_extension";
  const extensionOnline = extension.data?.state === "CONNECTED";
  const tone = done ? "mint" : current.status === "failed" || current.status === "uncertain" ? "yellow" : "blue";
  return (
    <AppCard tone={tone}>
      <div className="split"><h2>{current.title}</h2><AppBadge tone={done ? "mint" : current.status === "failed" ? "pink" : "blue"}>{done ? "Готово" : current.provider === "hh" ? "HH" : current.provider === "browser_extension" ? "Браузер" : "Вручную"}</AppBadge></div>
      <p>{current.message}</p>
      {current.resume_title && <p className="muted">Резюме: {current.resume_title}</p>}
      {current.error_code && current.status === "failed" && <AppNotice tone="danger">Повторите после проверки подключения.</AppNotice>}
      <div className="stack-actions">
        {current.status === "ready" && (!needsExtension || extensionOnline) && <AppButton disabled={submit.isPending} onClick={() => submit.mutate()}><Send size={18} /> {submit.isPending ? "Отправляем…" : "Откликнуться"}</AppButton>}
        {current.status === "failed" && <AppButton disabled={submit.isPending} onClick={() => submit.mutate()}>{submit.isPending ? "Повторяем…" : "Повторить"}</AppButton>}
        {(current.status === "connection_required" || current.status === "resume_required") && <AppLinkButton href="/app/connections"><Puzzle size={18} /> Открыть площадки</AppLinkButton>}
        {current.status === "external_action_required" && current.command && extensionOnline && <AppButton onClick={() => void contactExtension({ type: "CHECK_NOW" })}><Puzzle size={18} /> Продолжить в браузере</AppButton>}
        {needsExtension && !extensionOnline && <AppLinkButton href="/app/connections"><Puzzle size={18} /> Подключить расширение</AppLinkButton>}
        {current.external_url && (current.status !== "ready" || current.provider === "manual") && <AppLinkButton href={current.external_url} target="_blank" rel="noreferrer" variant="ghost">Открыть площадку <ExternalLink size={18} /></AppLinkButton>}
      </div>
      {submit.isError && <AppNotice tone="danger">{submit.error.message}</AppNotice>}
    </AppCard>
  );
}
