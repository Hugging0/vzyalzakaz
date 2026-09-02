"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Plus, Trash2 } from "lucide-react";
import { useState } from "react";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppField } from "@/components/ui/AppField";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppEmptyState, FeedSkeleton } from "@/components/ui/States";
import { miniAppApi } from "@/lib/api/client";

export function PortfolioView() {
  const client = useQueryClient();
  const query = useQuery({ queryKey: ["portfolio"], queryFn: miniAppApi.portfolio });
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ title: "", description: "", skills: "", url: "" });
  const add = useMutation({ mutationFn: () => miniAppApi.addPortfolio({ title: form.title.trim(), description: form.description.trim(), skills: form.skills.split(",").map((item) => item.trim()).filter(Boolean), url: form.url.trim() || null }), onSuccess: () => { setForm({ title: "", description: "", skills: "", url: "" }); setOpen(false); void client.invalidateQueries({ queryKey: ["portfolio"] }); } });
  const remove = useMutation({ mutationFn: miniAppApi.deletePortfolio, onSuccess: () => client.invalidateQueries({ queryKey: ["portfolio"] }) });
  if (query.isLoading) return <FeedSkeleton />;
  return (
    <>
      <AppPageHeader title="Портфолио" description="Кейсы, которые агент использует для подбора примеров в откликах." actions={<AppButton variant="secondary" onClick={() => setOpen((value) => !value)}><Plus size={18} />Добавить кейс</AppButton>} />
      {open && <AppCard className="portfolio-form" tone="blue"><h2>Новый кейс</h2><div className="form-grid"><AppField label="Название" htmlFor="case-title"><input id="case-title" className="app-input" value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} /></AppField><AppField label="Ссылка" htmlFor="case-url"><input id="case-url" className="app-input" type="url" value={form.url} onChange={(event) => setForm({ ...form, url: event.target.value })} placeholder="https://" /></AppField><AppField label="Описание" htmlFor="case-description"><textarea id="case-description" className="app-textarea" value={form.description} onChange={(event) => setForm({ ...form, description: event.target.value })} /></AppField><AppField label="Навыки через запятую" htmlFor="case-skills"><input id="case-skills" className="app-input" value={form.skills} onChange={(event) => setForm({ ...form, skills: event.target.value })} /></AppField></div><AppButton disabled={form.title.trim().length < 2 || form.description.trim().length < 10 || add.isPending} onClick={() => add.mutate()}>{add.isPending ? "Сохраняем" : "Сохранить кейс"}</AppButton>{add.isError && <AppNotice tone="danger">Кейс не сохранён. Проверьте поля и повторите.</AppNotice>}</AppCard>}
      {query.isError ? <AppEmptyState title="Не удалось загрузить портфолио" text="Проверьте соединение и повторите." /> : query.data?.length ? <div className="portfolio-grid">{query.data.map((item) => <AppCard key={item.slug}><div className="split"><h2>{item.title}</h2><AppButton variant="ghost" aria-label={`Удалить кейс ${item.title}`} disabled={remove.isPending} onClick={() => remove.mutate(item.slug)}><Trash2 size={18} /></AppButton></div><p>{item.description}</p><p className="muted">{item.skills.join(", ") || "Навыки не указаны"}</p>{item.url && <a className="text-link" href={item.url} target="_blank" rel="noreferrer">Открыть кейс <ExternalLink size={16} /></a>}</AppCard>)}</div> : <AppEmptyState title="Портфолио пока пустое" text="Это не блокирует подбор. Добавьте кейс, когда захотите усилить персональные отклики." action="Добавить кейс" onAction={() => setOpen(true)} />}
    </>
  );
}
