import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { miniAppApi } from "@/lib/api/client";

const specialties = ["Backend", "Frontend", "Fullstack", "Telegram bots", "AI / Automation", "Design", "Marketing"];
export function OnboardingView() {
  const client = useQueryClient(); const [selected, setSelected] = useState<string[]>([]); const [skills, setSkills] = useState(""); const [budget, setBudget] = useState("10000"); const [about, setAbout] = useState("");
  const save = useMutation({ mutationFn: () => miniAppApi.updateProfile({ specialties: selected, skills: skills.split(",").map((item) => item.trim()).filter(Boolean), minimumBudget: Number(budget), about, onboardingCompleted: true }), onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }) });
  const toggle = (value: string) => setSelected((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value]);
  return <><header className="app-header"><div><h1>Расскажите о себе</h1><p>Настроим первые совпадения за минуту</p></div></header><div className="stack"><AppCard><h2>Чем вы занимаетесь?</h2><div className="chip-grid">{specialties.map((item) => <button key={item} type="button" className="choice-chip" data-selected={selected.includes(item)} onClick={() => toggle(item)}>{item}</button>)}</div></AppCard><AppCard><label className="field-label" htmlFor="onboarding-skills">Ключевые навыки</label><input id="onboarding-skills" className="app-input" value={skills} onChange={(event) => setSkills(event.target.value)} placeholder="Python, FastAPI, PostgreSQL" /><label className="field-label" htmlFor="onboarding-budget">Минимальный бюджет, ₽</label><input id="onboarding-budget" className="app-input" type="number" min="0" value={budget} onChange={(event) => setBudget(event.target.value)} /><label className="field-label" htmlFor="onboarding-about">Какие задачи вы берёте лучше всего?</label><textarea id="onboarding-about" className="proposal-editor compact-editor" value={about} onChange={(event) => setAbout(event.target.value)} placeholder="Делаю API, Telegram-ботов и автоматизацию…" /><AppButton disabled={save.isPending || selected.length === 0 || skills.trim().length === 0} onClick={() => save.mutate()}>{save.isPending ? "Сохраняем…" : "Открыть ленту"}</AppButton></AppCard></div></>;
}
