import { ArrowLeft, ExternalLink } from "lucide-react";
import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { AppButton } from "@/components/ui/AppButton";
import { AppBadge } from "@/components/ui/AppBadge";
import { AppCard } from "@/components/ui/AppCard";
import { AppNotice } from "@/components/ui/AppNotice";
import { miniAppApi } from "@/lib/api/client";
import { telegramBridge } from "@/lib/telegram/telegram-webapp";
import type { Lead } from "@/types/domain";

export function LeadDetailsView({ lead, onBack }: { lead: Lead; onBack: () => void }) {
  const queryClient = useQueryClient();
  const [proposal, setProposal] = useState(lead.proposal ?? "");
  const prepare = useMutation({ mutationFn: () => miniAppApi.prepareProposal(lead.id), onSuccess: (data) => setProposal(data.proposal) });
  const save = useMutation({ mutationFn: () => miniAppApi.updateProposal(lead.id, proposal) });
  const markSent = useMutation({ mutationFn: () => miniAppApi.markSent(lead.id), onSuccess: () => { telegramBridge.hapticSuccess(); queryClient.invalidateQueries({ queryKey: ["leads"] }); } });
  useEffect(() => { window.scrollTo(0, 0); }, []);
  return <><header className="app-header"><AppButton variant="ghost" onClick={onBack} aria-label="Назад"><ArrowLeft size={18} /></AppButton><AppBadge tone="pink">Совпадение {lead.matchScore}%</AppBadge></header>
    <h1 className="detail-title">{lead.title}</h1><p className="lead-meta">{lead.budgetLabel} · {lead.source}</p>
    <div className="stack detail-stack"><AppCard><h2>Почему подходит</h2><ul className="reason-list">{lead.fitReasons.map((reason) => <li key={reason}>{reason}</li>)}</ul>{lead.requiredSkills.length > 0 && <p className="small muted">Нужные навыки: {lead.requiredSkills.join(", ")}</p>}</AppCard>
      {lead.risks.length > 0 && <AppNotice tone="warning">{lead.risks[0]}</AppNotice>}
      <AppCard><h2>О заказе</h2><p className="detail-description">{lead.description || "В источнике нет подробного описания."}</p>{lead.sourceUrl && <a className="original-link" href={lead.sourceUrl} target="_blank" rel="noreferrer">Открыть источник <ExternalLink size={14} /></a>}</AppCard>
      <AppCard><div className="split"><div><h2>Черновик отклика</h2><p className="small muted">Текст всегда можно отредактировать перед отправкой.</p></div>{lead.portfolioItem && <span className="case-chip">{lead.portfolioItem}</span>}</div>
        {proposal ? <textarea className="proposal-editor" value={proposal} onChange={(event) => setProposal(event.target.value)} aria-label="Текст отклика" /> : <AppNotice>Подготовьте персональный черновик, чтобы проверить текст и отправить его вручную.</AppNotice>}
        <div className="detail-actions">{proposal ? <AppButton variant="ghost" disabled={save.isPending} onClick={() => save.mutate()}>Сохранить текст</AppButton> : <AppButton disabled={prepare.isPending} onClick={() => prepare.mutate()}>{prepare.isPending ? "Готовим…" : "Подготовить отклик"}</AppButton>}
          {proposal && <AppButton disabled={markSent.isPending} onClick={() => markSent.mutate()}>{markSent.isPending ? "Сохраняем…" : "Я отправил отклик"}</AppButton>}</div>
        {(prepare.isError || save.isError || markSent.isError) && <p className="form-error">Текст сохранён локально. Не удалось завершить действие — попробуйте ещё раз.</p>}
      </AppCard></div>
  </>;
}
