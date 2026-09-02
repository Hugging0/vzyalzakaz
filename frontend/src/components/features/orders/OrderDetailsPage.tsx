"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";

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
      <div className="detail-toolbar"><Link className="back-link" href="/app/orders"><ArrowLeft size={18} />К заказам</Link><AppBadge tone="pink">{lead.matchScore}%</AppBadge></div>
      <header className="detail-heading"><h1>{lead.title}</h1><p>{lead.source} · {lead.budgetLabel}</p></header>
      <div className="detail-grid">
        <div className="detail-primary">
          <AppCard><h2>Почему подходит</h2><ul className="reason-list">{lead.fitReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>{lead.requiredSkills.length > 0 && <p className="muted">Навыки: {lead.requiredSkills.join(", ")}</p>}</AppCard>
          <AppCard><h2>Описание</h2><p className="detail-description">{lead.description || "В источнике нет подробного описания."}</p>{lead.sourceUrl && <a className="text-link" href={lead.sourceUrl} target="_blank" rel="noreferrer">Открыть источник <ExternalLink size={16} /></a>}</AppCard>
        </div>
        <aside className="detail-side"><AppCard tone="yellow"><h2>Следующее действие</h2><p>Подготовьте черновик. Отправка останется под вашим контролем.</p><div className="stack-actions"><AppButton disabled={prepare.isPending} onClick={() => lead.proposal ? router.push(`/app/applications/${id}`) : prepare.mutate()}>{prepare.isPending ? "Готовим текст" : lead.proposal ? "Открыть отклик" : "Подготовить отклик"}</AppButton><AppButton variant="ghost" disabled={skip.isPending} onClick={() => skip.mutate()}>Не подходит</AppButton></div></AppCard>{lead.risks.length > 0 && <AppCard tone="blue"><h2>Что проверить</h2><p>{lead.risks[0]}</p></AppCard>}</aside>
      </div>
    </>
  );
}
