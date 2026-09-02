"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { ApplicationCommandPanel } from "@/components/features/applications/ApplicationCommandPanel";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";

const dimensionLabels: Record<string, string> = {
  skills: "Навыки", money: "Деньги", portfolio: "Кейсы", client: "Клиент",
  urgency: "Срочность", format: "Формат", availability: "Загрузка",
};

function provenance(sourceFacts: string[], profileFacts: string[]): string {
  if (sourceFacts.length && profileFacts.length) return "Заказ + профиль";
  if (sourceFacts.length) return "Данные заказа";
  return "Данные профиля";
}

export function OrderDetailsPage({ id }: { id: number }) {
  const router = useRouter();
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["lead", id], queryFn: async () => mapLeadDtoToLead(await miniAppApi.lead(id) as never) });
  const prepare = useMutation({ mutationFn: () => miniAppApi.prepareProposal(id), onSuccess: () => { void client.invalidateQueries({ queryKey: ["lead", id] }); router.push(`/app/applications/${id}`); } });
  const skip = useMutation({ mutationFn: () => miniAppApi.skipLead(id), onSuccess: () => { void client.invalidateQueries({ queryKey: ["leads"] }); router.push("/app/orders"); } });
  if (query.isLoading) return <FeedSkeleton />;
  if (!query.data || query.isError) return <AppEmptyState title="Заказ не найден" text="Возможно, он был удалён или недоступен этому аккаунту." />;
  const lead = query.data;
  return (
    <>
      <div className="detail-toolbar"><Link className="back-link" href="/app/orders"><ArrowLeft size={18} />К заказам</Link><div className="match-rank"><AppBadge tone="pink">{lead.strengthLabel}</AppBadge><strong>{lead.matchScore}/100</strong></div></div>
      <header className="detail-heading"><h1>{lead.title}</h1><p>{lead.source} · {lead.budgetLabel}</p></header>
      <div className="detail-grid">
        <div className="detail-primary">
          {Object.keys(lead.dimensions).length > 0 && <AppCard><h2>Оценка</h2><dl className="match-dimensions">{Object.entries(lead.dimensions).map(([key, dimension]) => <div key={key}><dt>{dimensionLabels[key] ?? key}</dt><dd><strong>{dimension.label}</strong><span>{dimension.score}/100</span></dd></div>)}</dl></AppCard>}
          <AppCard><h2>Почему рекомендуем</h2><ol className="evidence-list">{(lead.recommendationReasons.length ? lead.recommendationReasons : lead.fitReasons.map((text) => ({ text, sourceFacts: [], profileFacts: ["legacy"] }))).map((reason) => <li key={`${reason.text}-${reason.sourceFacts.join()}`}><span>{reason.text}</span><small>{provenance(reason.sourceFacts, reason.profileFacts)}</small></li>)}</ol>{lead.requiredSkills.length > 0 && <p className="muted">Подтверждено: {lead.requiredSkills.join(", ")}</p>}</AppCard>
          <AppCard><h2>Описание</h2><p className="detail-description">{lead.description || "В источнике нет подробного описания."}</p>{lead.sourceUrl && <a className="text-link" href={lead.sourceUrl} target="_blank" rel="noreferrer">Открыть источник <ExternalLink size={16} /></a>}</AppCard>
        </div>
        <aside className="detail-side"><AppCard tone="yellow"><h2>Следующее действие</h2><p>Подготовьте текст или сразу перенесите его в форму площадки.</p><div className="stack-actions"><AppButton disabled={prepare.isPending} onClick={() => lead.proposal ? router.push(`/app/applications/${id}`) : prepare.mutate()}>{prepare.isPending ? "Готовим текст" : lead.proposal ? "Открыть текст" : "Подготовить текст"}</AppButton><AppButton variant="ghost" disabled={skip.isPending} onClick={() => skip.mutate()}>Не подходит</AppButton></div></AppCard><ApplicationCommandPanel id={id} source={lead.source} sourceUrl={lead.sourceUrl} />{lead.checks.length > 0 && <AppCard tone="blue"><h2>Что проверить</h2><ul className="evidence-list compact">{lead.checks.map((item) => <li key={`${item.text}-${item.sourceFacts.join()}`}><span>{item.text}</span><small>{provenance(item.sourceFacts, item.profileFacts)}</small></li>)}</ul></AppCard>}</aside>
      </div>
    </>
  );
}
