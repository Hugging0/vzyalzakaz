"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, type ReactNode } from "react";

import { WorkspaceShell } from "@/components/layout/WorkspaceShell";
import { AppCard } from "@/components/ui/AppCard";
import { FeedSkeleton } from "@/components/ui/States";
import { ApiError, clearSessionToken, miniAppApi, setSessionToken } from "@/lib/api/client";
import { telegramBridge } from "@/lib/telegram/telegram-webapp";
import type { Profile } from "@/types/domain";

type GateState = "checking" | "ready" | "error";

async function telegramInitData(): Promise<string> {
  const launchedByTelegram = telegramBridge.isAvailable() || window.location.href.includes("tgWebApp");
  if (!launchedByTelegram) return "";
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const value = telegramBridge.getInitData();
    if (value) return value;
    await new Promise((resolve) => window.setTimeout(resolve, 100));
  }
  return "";
}

export function WorkspaceGate({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const client = useQueryClient();
  const [state, setState] = useState<GateState>("checking");

  useEffect(() => {
    let active = true;
    async function authenticate() {
      telegramBridge.ready();
      try {
        const profile = await miniAppApi.me();
        client.setQueryData(["profile"], profile);
      } catch (error) {
        if (!(error instanceof ApiError) || error.status !== 401) throw error;
        const initData = await telegramInitData();
        if (!initData && process.env.NEXT_PUBLIC_ALLOW_DEV_AUTH !== "true") {
          router.replace(`/login?next=${encodeURIComponent(pathname)}`);
          return;
        }
        const session = initData ? await miniAppApi.auth(initData) : await miniAppApi.devAuth();
        setSessionToken(session.token);
        await miniAppApi.bootstrapWebSession();
        clearSessionToken();
        const profile = await miniAppApi.me();
        client.setQueryData(["profile"], profile);
      }
      if (active) setState("ready");
    }
    void authenticate().catch(() => active && setState("error"));
    return () => { active = false; };
  }, [client, pathname, router]);

  const profileQuery = useQuery<Profile>({
    queryKey: ["profile"],
    queryFn: miniAppApi.me,
    enabled: state === "ready",
  });

  useEffect(() => {
    const profile = profileQuery.data;
    if (!profile) return;
    if (!profile.onboardingCompleted && pathname !== "/app/onboarding") {
      router.replace("/app/onboarding");
    } else if (profile.onboardingCompleted && pathname === "/app/onboarding") {
      router.replace("/app/today");
    }
  }, [pathname, profileQuery.data, router]);

  if (state === "error") {
    return <main className="public-page"><AppCard className="public-card" tone="yellow"><h1>Не удалось открыть кабинет</h1><p>Проверьте соединение и обновите страницу. Данные не изменены.</p></AppCard></main>;
  }
  if (state !== "ready" || profileQuery.isLoading || !profileQuery.data) {
    return <main className="workspace-loading"><FeedSkeleton /></main>;
  }
  return <WorkspaceShell profile={profileQuery.data}>{children}</WorkspaceShell>;
}
