import { Pause, Play, Plus } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppField } from "@/components/ui/AppField";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppRangeField } from "@/components/ui/AppRangeField";
import { BillingCard } from "@/components/features/billing/BillingCard";
import { miniAppApi } from "@/lib/api/client";
import type { Profile } from "@/types/domain";

function SkillEditor({ profile }: { profile: Profile }) {
  const client = useQueryClient(); const [skills, setSkills] = useState(profile.skills.join(", "));
  const save = useMutation({ mutationFn: () => miniAppApi.updateProfile({ skills: skills.split(",").map((item) => item.trim()).filter(Boolean) }), onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }) });
  return <AppCard><h2>Профиль поиска</h2><AppField label="Навыки" htmlFor="skills" hint="Перечислите через запятую — они влияют на подбор."><input id="skills" className="app-input" value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="Python, FastAPI, Telegram bots" /></AppField><AppButton variant="secondary" disabled={save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Сохраняем…" : "Сохранить навыки"}</AppButton></AppCard>;
}

function NotificationSettings({ profile }: { profile: Profile }) {
  const client = useQueryClient();
  const [threshold, setThreshold] = useState(profile.matchThreshold);
  const save = useMutation({
    mutationFn: () => miniAppApi.updateProfile({ matchThreshold: threshold }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }),
  });
  return <AppCard><h2>Уведомления</h2><AppRangeField id="match-threshold" label="Порог совпадения" value={threshold} min={60} max={95} disabled={save.isPending} onChange={setThreshold} hint="Бот пришлёт проект от этого значения. В ленте остаются подходящие варианты от 60%." /><AppButton variant="secondary" disabled={save.isPending || threshold === profile.matchThreshold} onClick={() => save.mutate()}>{save.isPending ? "Сохраняем…" : "Сохранить порог"}</AppButton>{save.isError && <p className="form-error">Не удалось сохранить. Попробуйте ещё раз.</p>}</AppCard>;
}

export function ProfileView({ profile }: { profile: Profile }) {
  const client = useQueryClient(); const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: miniAppApi.portfolio });
  const toggle = useMutation({ mutationFn: () => miniAppApi.setAgentActive(!profile.isActive), onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }) });
  const [title, setTitle] = useState(""); const addCase = useMutation({ mutationFn: () => miniAppApi.addPortfolio({ title, description: "Добавлено из Mini App", skills: profile.skills, url: null }), onSuccess: () => { setTitle(""); client.invalidateQueries({ queryKey: ["portfolio"] }); } });
  return <><header className="app-header"><div><h1>Профиль</h1></div></header><div className="stack">
    <AppCard tone={profile.isActive ? "mint" : "yellow"}><div className="split"><h2>{profile.isActive ? "Поиск включён" : "Поиск на паузе"}</h2><AppButton variant={profile.isActive ? "ghost" : "primary"} disabled={toggle.isPending} onClick={() => toggle.mutate()}>{profile.isActive ? <><Pause size={17} /> Пауза</> : <><Play size={17} /> Продолжить</>}</AppButton></div></AppCard>
    <AppNotice tone="neutral">Перед отправкой вы всегда проверяете и подтверждаете текст отклика.</AppNotice>
    <NotificationSettings profile={profile} />
    <SkillEditor profile={profile} />
    <AppCard><h2>Портфолио</h2>{portfolio.data?.length ? <ul className="list-reset portfolio-list">{portfolio.data.map((item) => <li key={item.slug}><strong>{item.title}</strong><span>{item.skills.join(", ")}</span></li>)}</ul> : <p className="small muted">Добавьте кейс — это поможет подобрать сильный пример для отклика.</p>}<AppField label="Новый кейс" htmlFor="new-case"><div className="add-case"><input id="new-case" className="app-input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Например, бот для поддержки" /><AppButton variant="ghost" aria-label="Добавить кейс" disabled={!title || addCase.isPending} onClick={() => addCase.mutate()}><Plus size={18} /></AppButton></div></AppField></AppCard>
    <BillingCard />
  </div></>;
}
