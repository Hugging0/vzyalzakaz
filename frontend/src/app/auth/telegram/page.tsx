"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { AppCard } from "@/components/ui/AppCard";
import { AppLinkButton } from "@/components/ui/AppLinkButton";
import { miniAppApi } from "@/lib/api/client";

function TelegramExchangeContent() {
  const search = useSearchParams();
  const router = useRouter();
  const [error, setError] = useState(false);
  const ticket = search.get("ticket");
  useEffect(() => {
    if (!ticket) return;
    const requested = search.get("next") ?? "/app/today";
    const destination = requested.startsWith("/app/") ? requested : "/app/today";
    void miniAppApi.exchangeWebTicket(ticket)
      .then(() => router.replace(destination))
      .catch(() => setError(true));
  }, [router, search, ticket]);
  const hasError = !ticket || error;
  return <main className="public-page"><AppCard className="public-card" tone={hasError ? "yellow" : "blue"}><h1>{hasError ? "Ссылка не сработала" : "Входим в кабинет"}</h1><p>{hasError ? "Она могла устареть или уже использоваться. Запросите новую ссылку в Telegram." : "Проверяем одноразовую ссылку. Это займёт несколько секунд."}</p>{hasError && <AppLinkButton href="/login">Получить новую ссылку</AppLinkButton>}</AppCard></main>;
}

export default function TelegramExchangePage() {
  return <Suspense fallback={<main className="public-page"><AppCard className="public-card" tone="blue"><h1>Входим в кабинет</h1><p>Проверяем одноразовую ссылку.</p></AppCard></main>}><TelegramExchangeContent /></Suspense>;
}
