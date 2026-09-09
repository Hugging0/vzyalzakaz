"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { AppNotice } from "@/components/ui/AppNotice";
import { ApplicationCommandPanel } from "@/components/features/applications/ApplicationCommandPanel";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";

export function OrderDetailsPage({ id, returnTo = "/app/orders" }: { id: number; returnTo?: string }) {
  const router = useRouter();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["lead", id], queryFn: async () => mapLeadDtoToLead(await miniAppApi.lead(id) as never) });
  const prepare = useMutation({ mutationFn: () => miniAppApi.prepareProposal(id), onSuccess: () => { void client.invalidateQueries({ queryKey: ["lead", id] }); void client.invalidateQueries({ queryKey: ["leads"] }); router.push(`/app/applications/${id}`); } });
  const skip = useMutation({ mutationFn: () => miniAppApi.skipLead(id), onSuccess: () => { void client.invalidateQueries({ queryKey: ["leads"] }); router.push(returnTo); } });
  if (query.isLoading) return <FeedSkeleton />;
  if (query.isError) return <AppEmptyState title="Не удалось открыть заказ" text="Проверьте соединение и повторите запрос." action="Повторить" onAction={() => void query.refetch()} />;
  if (!query.data) return <AppEmptyState title="Заказ не найден" text="Возможно, он удалён или недоступен этому аккаунту." />;
  const lead = query.data;
  const reasons = lead.recommendationReasons.length ? lead.recommendationReasons.map((item) => item.text) : lead.fitReasons;
  const pending = prepare.isPending || skip.isPending;
  return (
    <div className="order-detail">
      <div className="detail-toolbar"><Link className="back-link" href={returnTo}><ArrowLeft size={18} />К заказам</Link></div>
      <header className="detail-heading"><h1>{lead.title}</h1><p><strong>{lead.budgetLabel}</strong> · {lead.source}</p></header>
      <section className="detail-actions" aria-label="Действия с заказом">
        <AppButton disabled={pending} onClick={() => lead.proposal ? router.push(`/app/applications/${id}`) : prepare.mutate()}>{prepare.isPending ? "Готовим отклик…" : lead.proposal ? "Открыть отклик" : "Подготовить отклик"}</AppButton>
        <AppButton variant="ghost" disabled={pending} onClick={() => skip.mutate()}>{skip.isPending ? "Скрываем…" : "Не подходит"}</AppButton>
        {(prepare.isError || skip.isError) && <AppNotice tone="danger">Действие не выполнено. Попробуйте ещё раз.</AppNotice>}
      </section>
      <div className="detail-grid">
        <div className="detail-primary">
          <AppCard className="order-fit"><h2>Почему рекомендуем</h2><ul className="evidence-list">{reasons.slice(0, 3).map((reason) => <li key={reason}>{reason}</li>)}</ul>{lead.checks.length > 0 && <><h2>Что уточнить</h2><ul className="evidence-list">{lead.checks.slice(0, 3).map((item) => <li key={item.text}>{item.text}</li>)}</ul></>}</AppCard>
          <AppCard><h2>Задача</h2><p className="detail-description">{lead.description || "В источнике нет подробного описания."}</p>{lead.sourceUrl && <a className="text-link" href={lead.sourceUrl} target="_blank" rel="noreferrer">Открыть источник <ExternalLink size={16} /></a>}</AppCard>
        </div>
        <aside className="detail-side">
          {lead.economics.normalizedLabel && <AppNotice>В рублях: {lead.economics.normalizedLabel}. Курс ЦБ на {lead.economics.fxRateDate ?? "дату публикации"}.</AppNotice>}
          {lead.economics.requiresCheck && <AppNotice tone="warning">Сумму в рублях нужно уточнить: курс валюты недоступен.</AppNotice>}
          <ApplicationCommandPanel id={id} source={lead.source} sourceUrl={lead.sourceUrl} />
        </aside>
      </div>
    </div>
  );
}
