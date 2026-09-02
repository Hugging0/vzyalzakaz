"use client";

import { Check, RefreshCw } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { AppButton } from "@/components/ui/AppButton";
import { AppCard } from "@/components/ui/AppCard";
import { AppNotice } from "@/components/ui/AppNotice";
import { miniAppApi } from "@/lib/api/client";

export function BillingCard() {
  const client = useQueryClient();
  const billing = useQuery({ queryKey: ["billing"], queryFn: miniAppApi.billing });
  const checkout = useMutation({
    mutationFn: () => miniAppApi.createCheckout(crypto.randomUUID()),
    onSuccess: (data) => { if (data.confirmation_url) window.location.assign(data.confirmation_url); },
  });
  const refresh = useMutation({ mutationFn: miniAppApi.refreshBilling, onSuccess: () => client.invalidateQueries({ queryKey: ["billing"] }) });
  const paid = billing.data?.status === "succeeded";
  return <AppCard className="billing-card"><div className="split"><div><span className="billing-eyebrow">Профессиональный режим</span><h2>{paid ? "Подписка активна" : "Больше возможностей для поиска"}</h2></div></div>
    <ul className="billing-benefits"><li><Check size={16} /> Расширенный лимит источников</li><li><Check size={16} /> Черновики откликов под задачу</li><li><Check size={16} /> Приоритетные уведомления</li></ul>
    {paid ? <AppNotice tone="success">Оплата подтверждена. Доступ Pro активен.</AppNotice> : <><p className="small muted">Тестовая оплата: деньги не списываются. Цену и реальные тарифы настроим перед запуском.</p><div className="billing-actions"><AppButton disabled={checkout.isPending || !billing.data?.checkout_available} onClick={() => checkout.mutate()}>{checkout.isPending ? "Открываем ЮKassa…" : "Протестировать оплату"}</AppButton>{billing.data?.status === "pending" && <AppButton variant="ghost" disabled={refresh.isPending} onClick={() => refresh.mutate()} aria-label="Проверить оплату"><RefreshCw size={17} /></AppButton>}</div>{checkout.isError && <p className="form-error">Не удалось открыть оплату. Попробуйте ещё раз.</p>}{!billing.data?.checkout_available && !billing.isLoading && <p className="small muted">Оплата будет доступна после настройки ключей на сервере.</p>}</>}
  </AppCard>;
}
