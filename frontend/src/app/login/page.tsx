import { Send } from "lucide-react";

import { AppCard } from "@/components/ui/AppCard";
import { AppLogo } from "@/components/ui/AppLogo";

function loginPayload(destination: string): string {
  const details = destination.match(/^\/app\/(orders|applications)\/(\d+)$/);
  if (details) {
    return `web-login-${details[1] === "orders" ? "order" : "application"}-${details[2]}`;
  }
  const section = destination.match(/^\/app\/(today|orders|applications|portfolio|connections|analytics|profile|settings)$/)?.[1];
  return `web-login-${section ?? "today"}`;
}

export default async function LoginPage({ searchParams }: { searchParams: Promise<{ next?: string }> }) {
  const requested = (await searchParams).next ?? "/app/today";
  const next = requested.startsWith("/app/") ? requested : "/app/today";
  const configuredBot = (process.env.TELEGRAM_BOT_USERNAME ?? "vzyal_zakaz_bot").replace(/^@/, "");
  const botUsername = /^[a-zA-Z0-9_]{5,32}$/.test(configuredBot) ? configuredBot : "vzyal_zakaz_bot";
  const botUrl = `https://t.me/${botUsername}?start=${loginPayload(next)}`;
  return (
    <main className="public-page">
      <AppCard className="public-card login-card">
        <AppLogo />
        <div><h1>Войти в кабинет</h1><p>Telegram подтвердит аккаунт и пришлёт одноразовую ссылку. Пароль не нужен.</p></div>
        <a className="app-button app-button--primary" href={botUrl} target="_blank" rel="noreferrer"><Send size={18} /> Продолжить через Telegram</a>
        <p className="field-hint">После входа откроется нужный раздел кабинета.</p>
      </AppCard>
    </main>
  );
}
