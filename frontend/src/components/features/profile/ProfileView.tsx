import { Pause, Play, Plus } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppNotice } from "@/components/ui/AppNotice";
import { BillingCard } from "@/components/features/billing/BillingCard";
import { miniAppApi } from "@/lib/api/client";
import type { Profile } from "@/types/domain";

function SkillEditor({ profile }: { profile: Profile }) {
  const client = useQueryClient(); const [skills, setSkills] = useState(profile.skills.join(", "));
  const save = useMutation({ mutationFn: () => miniAppApi.updateProfile({ skills: skills.split(",").map((item) => item.trim()).filter(Boolean) }), onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }) });
  return <AppCard><h2>Профиль поиска</h2><label className="field-label" htmlFor="skills">Навыки</label><input id="skills" className="app-input" value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="Python, FastAPI, Telegram bots" /><p className="small muted">Через запятую. Эти данные влияют на будущие совпадения.</p><AppButton variant="secondary" disabled={save.isPending} onClick={() => save.mutate()}>Сохранить навыки</AppButton></AppCard>;
}

export function ProfileView({ profile }: { profile: Profile }) {
  const client = useQueryClient(); const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: miniAppApi.portfolio });
  const toggle = useMutation({ mutationFn: () => miniAppApi.setAgentActive(!profile.isActive), onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }) });
  const [title, setTitle] = useState(""); const addCase = useMutation({ mutationFn: () => miniAppApi.addPortfolio({ title, description: "Добавлено из Mini App", skills: profile.skills, url: null }), onSuccess: () => { setTitle(""); client.invalidateQueries({ queryKey: ["portfolio"] }); } });
  return <><header className="app-header"><div><h1>Профиль</h1><p>Настройки поиска и ваши кейсы</p></div></header><div className="stack">
    <AppCard><div className="split"><div><h2>{profile.isActive ? "Агент работает" : "Агент на паузе"}</h2><p className="small muted">{profile.isActive ? `Уведомления от ${profile.matchThreshold}% совпадения` : "Новые уведомления и действия остановлены."}</p></div><AppButton variant={profile.isActive ? "ghost" : "primary"} disabled={toggle.isPending} onClick={() => toggle.mutate()}>{profile.isActive ? <><Pause size={17} /> Пауза</> : <><Play size={17} /> Продолжить</>}</AppButton></div></AppCard>
    <AppNotice tone="neutral">Режим по умолчанию — проверка перед отправкой. Автопилот появится только для источников, где безопасная отправка реально поддерживается.</AppNotice>
    <SkillEditor profile={profile} />
    <AppCard><h2>Портфолио</h2>{portfolio.data?.length ? <ul className="list-reset portfolio-list">{portfolio.data.map((item) => <li key={item.slug}><strong>{item.title}</strong><span>{item.skills.join(", ")}</span></li>)}</ul> : <p className="small muted">Добавьте кейс — это поможет подобрать сильный пример для отклика.</p>}<div className="add-case"><input className="app-input" value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Название кейса" /><AppButton variant="ghost" aria-label="Добавить кейс" disabled={!title || addCase.isPending} onClick={() => addCase.mutate()}><Plus size={18} /></AppButton></div></AppCard>
    <BillingCard />
  </div></>;
}
