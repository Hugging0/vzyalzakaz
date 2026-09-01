import { AlertCircle, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { AnalyticsView } from "@/components/features/analytics/AnalyticsView";
import { ApplicationsView } from "@/components/features/applications/ApplicationsView";
import { LeadDetailsView } from "@/components/features/lead-details/LeadDetailsView";
import { LeadFeedView } from "@/components/features/lead-feed/LeadFeedView";
import { OnboardingView } from "@/components/features/onboarding/OnboardingView";
import { ProfileView } from "@/components/features/profile/ProfileView";
import { MiniAppShell } from "@/components/layout/MiniAppShell";
import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppNotice } from "@/components/ui/AppNotice";
import { getSessionToken, miniAppApi, setSessionToken } from "@/lib/api/client";
import { telegramBridge } from "@/lib/telegram/telegram-webapp";
import type { Lead } from "@/types/domain";

type Tab = "feed" | "applications" | "analytics" | "profile";
type BootstrapState = "loading" | "ready" | "unavailable" | "error";

function BootstrapScreen({ state, onRetry }: { state: BootstrapState; onRetry: () => void }) {
  const unavailable = state === "unavailable";
  return <main className="app-shell"><div className="app-content bootstrap"><AppCard><AlertCircle size={28} color="var(--warning)" /><h1>{unavailable ? "Откройте внутри Telegram" : "Не удалось открыть кабинет"}</h1><p className="muted">{unavailable ? "Вернитесь в чат с ботом и нажмите кнопку «Открыть кабинет». Так Telegram безопасно подтвердит ваш профиль." : "Проверьте соединение и попробуйте ещё раз. Ваши данные не изменены."}</p>{!unavailable && <AppButton onClick={onRetry}><RefreshCw size={17} /> Повторить</AppButton>}</AppCard></div></main>;
}

export function HuntApp() {
  const [bootstrap, setBootstrap] = useState<BootstrapState>("loading"); const [tab, setTab] = useState<Tab>("feed"); const [selectedLead, setSelectedLead] = useState<Lead | null>(null);
  const profileQuery = useQuery({ queryKey: ["profile"], queryFn: miniAppApi.me, enabled: bootstrap === "ready" });
  const authenticate = async () => {
    setBootstrap("loading"); telegramBridge.ready(); document.documentElement.dataset.theme = "brand";
    const initData = telegramBridge.getInitData();
    if (!getSessionToken() && !initData && process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH !== "true") { setBootstrap("unavailable"); return; }
    try {
      if (!getSessionToken()) {
        const session = initData ? await miniAppApi.auth(initData) : await miniAppApi.devAuth();
        setSessionToken(session.token);
      }
      setBootstrap("ready");
    } catch { setBootstrap("error"); }
  };
  useEffect(() => {
    const timer = window.setTimeout(() => { void authenticate(); }, 0);
    return () => window.clearTimeout(timer);
  }, []);
  if (bootstrap !== "ready") return <BootstrapScreen state={bootstrap} onRetry={() => void authenticate()} />;
  if (profileQuery.isLoading) return <main className="app-shell"><div className="app-content"><p className="muted">Загружаем профиль…</p></div></main>;
  if (profileQuery.isError || !profileQuery.data) return <BootstrapScreen state="error" onRetry={() => void profileQuery.refetch()} />;
  const profile = profileQuery.data;
  let content = !profile.onboardingCompleted ? <OnboardingView /> : tab === "feed" ? <LeadFeedView onOpen={setSelectedLead} /> : tab === "applications" ? <ApplicationsView /> : tab === "analytics" ? <AnalyticsView /> : <ProfileView profile={profile} />;
  if (selectedLead) content = <LeadDetailsView lead={selectedLead} onBack={() => setSelectedLead(null)} />;
  return <MiniAppShell activeTab={tab} onTabChange={(nextTab) => { setSelectedLead(null); setTab(nextTab); }}>{!profile.isActive && <AppNotice tone="warning">Поиск на паузе: новые рекомендации и уведомления остановлены.</AppNotice>}{content}</MiniAppShell>;
}
