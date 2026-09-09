"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Pause, Play } from "lucide-react";
import { useState } from "react";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppCheckbox } from "@/components/ui/AppCheckbox";
import { AppField } from "@/components/ui/AppField";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { AppRangeField } from "@/components/ui/AppRangeField";
import { AppToggle } from "@/components/ui/AppToggle";
import { miniAppApi } from "@/lib/api/client";
import type { Profile } from "@/types/domain";

function values(value: string): string[] {
  return value.split(",").map((item) => item.trim()).filter(Boolean);
}

export function AgentSettingsView({ profile }: { profile: Profile }) {
  const client = useQueryClient();
  const sources = useQuery({ queryKey: ["sources"], queryFn: miniAppApi.sources });
  const [form, setForm] = useState({
    threshold: profile.matchThreshold,
    minimumBudget: String(profile.minimumBudget || ""),
    hourlyRate: String(profile.hourlyRate || ""),
    excludedKeywords: profile.excludedKeywords.join(", "),
    preferredSources: profile.preferredSources,
    automationLevel: profile.automationLevel,
    notifications: profile.notifications,
  });
  const toggleAgent = useMutation({
    mutationFn: () => miniAppApi.setAgentActive(!profile.isActive),
    onSuccess: (updated) => client.setQueryData(["profile"], updated),
  });
  const save = useMutation({
    mutationFn: () => miniAppApi.updateProfile({
      matchThreshold: form.threshold,
      minimumBudget: Number(form.minimumBudget || 0),
      excludedKeywords: values(form.excludedKeywords),
      hourlyRate: Number(form.hourlyRate || 0),
      preferredSources: form.preferredSources,
      automationLevel: form.automationLevel,
      notifications: form.notifications,
    }),
    onSuccess: (updated) => client.setQueryData(["profile"], updated),
  });
  const toggleSource = (name: string) => setForm((current) => ({
    ...current,
    preferredSources: current.preferredSources.includes(name)
      ? current.preferredSources.filter((item) => item !== name)
      : [...current.preferredSources, name],
  }));

  return (
    <>
      <AppPageHeader title="Настройки агента" description="Условия поиска, уведомления и допустимая степень автоматизации." />
      <form className="settings-layout" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <div className="stack">
          <AppCard tone={profile.isActive ? "mint" : "yellow"}>
            <div className="split">
              <div>
                <h2>{profile.isActive ? "Агент работает" : "Агент на паузе"}</h2>
                <p>{profile.isActive ? "Новые источники проверяются по расписанию." : "Новые рекомендации и уведомления остановлены."}</p>
              </div>
              <AppButton variant={profile.isActive ? "ghost" : "primary"} disabled={toggleAgent.isPending} onClick={() => toggleAgent.mutate()}>
                {profile.isActive ? <><Pause size={18} />Поставить на паузу</> : <><Play size={18} />Запустить поиск</>}
              </AppButton>
            </div>
          </AppCard>
          <AppCard>
            <h2>Условия подработки</h2>
            <p className="muted">Оставьте сумму пустой, если ограничения нет. Заказы без указанного бюджета тоже участвуют в подборе.</p>
            <div className="form-grid">
              <AppField label="От какой суммы за задачу, ₽" htmlFor="settings-budget">
                <input id="settings-budget" className="app-input" type="number" inputMode="numeric" min="0" max="100000000" step="1" value={form.minimumBudget} onChange={(event) => setForm({ ...form, minimumBudget: event.target.value })} />
              </AppField>
              <AppField label="Желаемая ставка, ₽/час" htmlFor="settings-rate">
                <input id="settings-rate" className="app-input" type="number" inputMode="numeric" min="0" max="1000000" step="1" value={form.hourlyRate} onChange={(event) => setForm({ ...form, hourlyRate: event.target.value })} />
              </AppField>
            </div>
            <AppField label="Не показывать" htmlFor="settings-excluded" hint="Слова и темы через запятую">
              <input id="settings-excluded" className="app-input" value={form.excludedKeywords} onChange={(event) => setForm({ ...form, excludedKeywords: event.target.value })} />
            </AppField>
          </AppCard>
          <AppCard>
            <h2>Уведомления</h2>
            <AppRangeField id="settings-threshold" label="Сообщать об оценке от" value={form.threshold} min={60} max={95} suffix="/100" onChange={(threshold) => setForm({ ...form, threshold })} hint="Порог влияет только на срочные сообщения в Telegram." />
            <div className="toggle-list">
              <AppToggle id="notify-matches" label="Сильные заказы" checked={form.notifications.strongMatches} onChange={(strongMatches) => setForm({ ...form, notifications: { ...form.notifications, strongMatches } })} />
              <AppToggle id="notify-replies" label="Ответы заказчиков" checked={form.notifications.replies} onChange={(replies) => setForm({ ...form, notifications: { ...form.notifications, replies } })} />
              <AppToggle id="notify-connections" label="Проблемы площадок" checked={form.notifications.connectionIssues} onChange={(connectionIssues) => setForm({ ...form, notifications: { ...form.notifications, connectionIssues } })} />
            </div>
          </AppCard>
        </div>
        <aside className="stack">
          <AppCard tone="blue">
            <h2>Автоматизация</h2>
            <AppField label="Режим" htmlFor="automation-level">
              <select id="automation-level" className="app-input" value={form.automationLevel} onChange={(event) => setForm({ ...form, automationLevel: event.target.value as Profile["automationLevel"] })}>
                <option value="drafts">Готовить черновики</option>
                <option value="manual">Только подбирать заказы</option>
              </select>
            </AppField>
            <AppNotice>Финальную отправку всегда подтверждаете вы. Первая версия расширения остановится перед отправкой.</AppNotice>
          </AppCard>
          <AppCard>
            <h2>Предпочтительные источники</h2>
            <p className="muted">Если ничего не выбрано, агент использует все подключённые источники.</p>
            {sources.isError ? <AppNotice tone="danger">Не удалось загрузить источники.</AppNotice> : (
              <div className="source-checklist">
                {sources.data?.filter((source) => source.enabled).map((source) => (
                  <AppCheckbox key={source.name} label={source.displayName} checked={form.preferredSources.includes(source.name)} onChange={() => toggleSource(source.name)} />
                ))}
              </div>
            )}
          </AppCard>
          <AppButton type="submit" disabled={save.isPending}>{save.isPending ? "Сохраняем" : "Сохранить настройки"}</AppButton>
          {save.isSuccess && <AppNotice tone="success">Настройки сохранены.</AppNotice>}
          {save.isError && <AppNotice tone="danger">Настройки не сохранены. Повторите попытку.</AppNotice>}
        </aside>
      </form>
    </>
  );
}
