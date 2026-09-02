"use client";

import { AudioLines, FileText, MessageSquareText } from "lucide-react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppField } from "@/components/ui/AppField";
import { AppNotice } from "@/components/ui/AppNotice";
import { AppPageHeader } from "@/components/ui/AppPageHeader";
import { miniAppApi } from "@/lib/api/client";
import { telegramBridge } from "@/lib/telegram/telegram-webapp";

export function OnboardingView() {
  const client = useQueryClient();
  const [about, setAbout] = useState("");
  const [budget, setBudget] = useState("");
  const save = useMutation({
    mutationFn: () => miniAppApi.completeOnboarding({
      about: about.trim(),
      ...(budget ? { minimumBudget: Number(budget) } : {}),
    }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["profile"] }),
  });

  return <>
    <AppPageHeader title="Расскажите, какую работу ищете" description="Одного сообщения достаточно, чтобы запустить подбор." />
    <div className="onboarding-layout">
      <AppCard tone="pink" className="onboarding-intro">
        <MessageSquareText size={24} aria-hidden="true" />
        <strong>Пишите как человеку</strong>
        <p>Чем занимаетесь, какие задачи берёте, с чем работаете и что точно не подходит.</p>
      </AppCard>
      <AppCard className="onboarding-card">
        <AppField label="О себе и желаемых проектах" htmlFor="onboarding-about" hint="Например: проектирую интерфейсы в Figma, люблю сложные кабинеты и дизайн-системы. Ищу проекты от 50 000 ₽.">
          <textarea id="onboarding-about" className="app-textarea onboarding-textarea" value={about} onChange={(event) => setAbout(event.target.value)} placeholder="Расскажите о своём опыте и задачах…" autoFocus />
        </AppField>
        <AppField label="Минимальный бюджет, ₽ (необязательно)" htmlFor="onboarding-budget">
          <input id="onboarding-budget" className="app-input" type="number" inputMode="numeric" min="0" value={budget} onChange={(event) => setBudget(event.target.value)} placeholder="Например, 30 000" />
        </AppField>
        {save.isError && <AppNotice tone="danger">Не удалось сохранить профиль. Проверьте соединение и попробуйте ещё раз.</AppNotice>}
        <AppButton disabled={about.trim().length < 20 || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Собираем профиль" : "Создать профиль"}</AppButton>
      </AppCard>
      <AppCard tone="blue" className="onboarding-alternative">
        <div><AudioLines size={22} aria-hidden="true" /><strong>Удобнее голосом?</strong></div>
        <p>Отправьте боту голосовое и документы портфолио. Без документов профиль тоже будет создан.</p>
        <AppButton variant="ghost" onClick={() => telegramBridge.openTelegramLink("https://t.me/vzyal_zakaz_bot")}><FileText size={18} /> Открыть чат с ботом</AppButton>
      </AppCard>
    </div>
  </>;
}
