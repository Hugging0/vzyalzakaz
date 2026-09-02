import Link from "next/link";

import { AppCard } from "@/components/ui/AppCard";
import { AppLinkButton } from "@/components/ui/AppLinkButton";

export default function OfflinePage() {
  return (
    <main className="public-page">
      <AppCard className="public-card" tone="blue">
        <h1>Нет соединения</h1>
        <p>Кабинету нужен интернет, чтобы загрузить заказы и сохранить изменения.</p>
        <AppLinkButton href="/app/today">Повторить</AppLinkButton>
        <Link className="text-link" href="/login">Вернуться ко входу</Link>
      </AppCard>
    </main>
  );
}
