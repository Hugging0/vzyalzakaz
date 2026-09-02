"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppField } from "@/components/ui/AppField";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { BillingCard } from "@/components/features/billing/BillingCard";
import { miniAppApi } from "@/lib/api/client";
import type { Profile } from "@/types/domain";

export function ProfileView({ profile }: { profile: Profile }) {
  const client = useQueryClient();
  const [form, setForm] = useState({ about: profile.about, skills: profile.skills.join(", "), languages: profile.languages.join(", "), minimumBudget: String(profile.minimumBudget || ""), hourlyRate: String(profile.hourlyRate || "") });
  const save = useMutation({ mutationFn: () => miniAppApi.updateProfile({ about: form.about, skills: form.skills.split(",").map((item) => item.trim()).filter(Boolean), languages: form.languages.split(",").map((item) => item.trim()).filter(Boolean), minimumBudget: Number(form.minimumBudget || 0), hourlyRate: Number(form.hourlyRate || 0) }), onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }) });
  return <><AppPageHeader title="Профиль" description="Опыт и условия, которые агент учитывает при подборе и подготовке откликов." /><div className="profile-layout"><AppCard className="profile-form"><h2>Рабочий профиль</h2><AppField label="О себе" htmlFor="profile-about" hint="Опишите опыт, сильные задачи и ограничения обычным языком."><textarea id="profile-about" className="app-textarea" value={form.about} onChange={(event) => setForm({ ...form, about: event.target.value })} /></AppField><div className="form-grid"><AppField label="Навыки" htmlFor="profile-skills"><input id="profile-skills" className="app-input" value={form.skills} onChange={(event) => setForm({ ...form, skills: event.target.value })} /></AppField><AppField label="Языки" htmlFor="profile-languages"><input id="profile-languages" className="app-input" value={form.languages} onChange={(event) => setForm({ ...form, languages: event.target.value })} /></AppField><AppField label="Минимальный бюджет, ₽" htmlFor="profile-budget"><input id="profile-budget" className="app-input" type="number" min="0" value={form.minimumBudget} onChange={(event) => setForm({ ...form, minimumBudget: event.target.value })} /></AppField><AppField label="Целевая ставка, ₽/ч" htmlFor="profile-rate"><input id="profile-rate" className="app-input" type="number" min="0" value={form.hourlyRate} onChange={(event) => setForm({ ...form, hourlyRate: event.target.value })} /></AppField></div><AppButton variant="secondary" disabled={save.isPending || form.about.trim().length < 20} onClick={() => save.mutate()}>{save.isPending ? "Сохраняем" : "Сохранить профиль"}</AppButton>{save.isSuccess && <AppNotice tone="success">Профиль обновлён. Новые рекомендации будут пересчитаны.</AppNotice>}{save.isError && <AppNotice tone="danger">Профиль не сохранён. Проверьте соединение и повторите.</AppNotice>}</AppCard><aside><AppNotice>Отклики отправляете только вы. Агент готовит текст и помогает вести статусы.</AppNotice><BillingCard /></aside></div></>;
}
