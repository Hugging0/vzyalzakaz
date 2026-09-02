"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ExternalLink } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { AppBadge } from "@/components/ui/AppBadge";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppField } from "@/components/ui/AppField";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { applicationEventLabel, leadStatusLabel } from "@/lib/copy/leads";
import { miniAppApi } from "@/lib/api/client";
import { mapLeadDtoToLead } from "@/lib/mappers/lead.mapper";
import type { LeadStatus } from "@/types/domain";

type Action = { status: LeadStatus; label: string; variant: "primary" | "ghost" | "success" | "danger" };
const nextActions: Partial<Record<LeadStatus, Action[]>> = {
  approved: [{ status: "contacted", label: "Я отправил отклик", variant: "success" }],
  contacted: [{ status: "replied", label: "Получен ответ", variant: "success" }, { status: "lost", label: "Нет ответа", variant: "ghost" }],
  replied: [{ status: "interview", label: "Назначено интервью", variant: "success" }, { status: "won", label: "Заказ выигран", variant: "success" }, { status: "lost", label: "Не договорились", variant: "danger" }],
  interview: [{ status: "won", label: "Заказ выигран", variant: "success" }, { status: "lost", label: "Не договорились", variant: "danger" }],
};

export function ApplicationDetailsView({ id }: { id: number }) {
  const client = useQueryClient();
  const leadQuery = useQuery({ queryKey: ["lead", id], queryFn: async () => mapLeadDtoToLead(await miniAppApi.lead(id) as never) });
  const events = useQuery({ queryKey: ["lead-events", id], queryFn: () => miniAppApi.leadEvents(id) });
  const [proposalDraft, setProposalDraft] = useState<string | null>(null);
  const proposal = proposalDraft ?? leadQuery.data?.proposal ?? "";
  const refresh = async () => { await Promise.all([client.invalidateQueries({ queryKey: ["lead", id] }), client.invalidateQueries({ queryKey: ["lead-events", id] }), client.invalidateQueries({ queryKey: ["leads"] })]); };
  const save = useMutation({ mutationFn: () => miniAppApi.updateProposal(id, proposal), onSuccess: refresh });
  const changeStatus = useMutation({ mutationFn: (status: LeadStatus) => miniAppApi.updateLeadStatus(id, status), onSuccess: refresh });
  if (leadQuery.isLoading) return <FeedSkeleton />;
  if (!leadQuery.data || leadQuery.isError) return <AppEmptyState title="Отклик не найден" text="Он недоступен этому аккаунту или был удалён." />;
  const lead = leadQuery.data;
  const actions = nextActions[lead.status] ?? [];
  return (
    <>
      <div className="detail-toolbar"><Link className="back-link" href="/app/applications"><ArrowLeft size={18} />К откликам</Link><AppBadge tone={lead.status === "won" ? "mint" : "yellow"}>{leadStatusLabel[lead.status]}</AppBadge></div>
      <header className="detail-heading"><h1>{lead.title}</h1><p>{lead.source} · {lead.budgetLabel}</p></header>
      <div className="detail-grid application-detail-grid">
        <div className="detail-primary"><AppCard><div className="split"><h2>Текст отклика</h2>{lead.portfolioItem && <AppBadge tone="blue">Кейс: {lead.portfolioItem}</AppBadge>}</div><AppField label="Черновик" htmlFor="proposal"><textarea id="proposal" className="proposal-editor" value={proposal} onChange={(event) => setProposalDraft(event.target.value)} /></AppField><div className="inline-actions"><AppButton variant="secondary" disabled={save.isPending || proposal.trim() === lead.proposal?.trim()} onClick={() => save.mutate()}>{save.isPending ? "Сохраняем" : "Сохранить текст"}</AppButton>{lead.sourceUrl && <a className="text-link" href={lead.sourceUrl} target="_blank" rel="noreferrer">Открыть площадку <ExternalLink size={16} /></a>}</div>{save.isError && <AppNotice tone="danger">Не удалось сохранить текст. Проверьте соединение и повторите.</AppNotice>}</AppCard></div>
        <aside className="detail-side"><AppCard tone="yellow"><h2>Статус отклика</h2><p>Отмечайте только фактические действия и ответы.</p><div className="stack-actions">{actions.map((action) => <AppButton key={action.status} variant={action.variant} disabled={changeStatus.isPending} onClick={() => changeStatus.mutate(action.status)}>{action.label}</AppButton>)}</div>{changeStatus.isError && <AppNotice tone="danger">Статус не изменён. Проверьте допустимый порядок действий.</AppNotice>}</AppCard><AppCard><h2>История</h2><ol className="timeline"><li><span /><div><strong>Заказ добавлен</strong><time>{new Intl.DateTimeFormat("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(lead.createdAt))}</time></div></li>{events.data?.map((event) => <li key={event.id}><span /><div><strong>{applicationEventLabel[event.event] ?? event.event}</strong><time>{new Intl.DateTimeFormat("ru", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" }).format(new Date(event.createdAt))}</time>{event.detail && <small>{event.detail}</small>}</div></li>)}</ol></AppCard></aside>
      </div>
    </>
  );
}
