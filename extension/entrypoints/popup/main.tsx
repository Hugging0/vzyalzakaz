import { ExternalLink, RefreshCw, Unplug } from "lucide-react";
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "@fontsource-variable/golos-text";
import "@fontsource-variable/unbounded";
import type { BackgroundMessage, StoredState } from "../../src/contracts";
import {
  ExtensionBadge,
  ExtensionButton,
  ExtensionCard,
  ExtensionLogo,
  ExtensionNotice,
} from "../../src/ui/primitives";
import "./style.css";

const APP_URL = "https://vzyalzakaz.ru/app";

function Popup() {
  const [state, setState] = useState<StoredState | null>(null);
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => { void refresh(false); }, []);

  async function refresh(check = true) {
    setBusy(true);
    setError(null);
    try {
      if (check) await message({ type: "CHECK_NOW" });
      setState(await message<StoredState>({ type: "GET_STATE" }));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось обновить состояние");
    } finally {
      setBusy(false);
    }
  }

  async function connect() {
    if (code.trim().length < 20) {
      setError("Вставьте код подключения из кабинета");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await message({ type: "LINK", code: code.trim() });
      setCode("");
      await refresh(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Код не принят");
      setBusy(false);
    }
  }

  async function disconnect() {
    await message({ type: "DISCONNECT" });
    await refresh(false);
  }

  const connected = state?.connection === "CONNECTED";
  const command = state?.activeCommand;
  return (
    <main className="popup-shell">
      <header className="popup-head">
        <ExtensionLogo />
        <div><h1>Помощник отклика</h1><p>Отправка только после вашей проверки</p></div>
      </header>

      {!state ? <ExtensionCard tone="blue"><p>Проверяем подключение…</p></ExtensionCard> : !connected ? (
        <ExtensionCard tone="yellow">
          <div className="card-heading"><h2>Подключите кабинет</h2><ExtensionBadge tone="yellow">Не подключено</ExtensionBadge></div>
          <p>Откройте «Площадки» в кабинете, получите одноразовый код и вставьте его сюда.</p>
          <label className="ext-field">
            <span>Код подключения</span>
            <input value={code} onChange={(event) => setCode(event.target.value)} placeholder="Например, x2Y…" autoComplete="off" />
          </label>
          <ExtensionButton disabled={busy} onClick={() => void connect()}>{busy ? "Подключаем…" : "Подключить"}</ExtensionButton>
          <ExtensionButton variant="ghost" onClick={() => void chrome.tabs.create({ url: `${APP_URL}/connections` })}>Открыть кабинет <ExternalLink size={18} /></ExtensionButton>
        </ExtensionCard>
      ) : (
        <>
          <ExtensionCard tone="mint">
            <div className="card-heading"><h2>Расширение готово</h2><ExtensionBadge tone="mint">На связи</ExtensionBadge></div>
            <p>{sourceLabel(state.activeSourceId, state.marketplaceAuthState)}</p>
          </ExtensionCard>
          {command ? <CommandCard state={state} /> : <ExtensionCard><h2>Задач пока нет</h2><p>Подготовьте отклик в кабинете — нужная страница откроется автоматически.</p></ExtensionCard>}
          <div className="popup-actions">
            <ExtensionButton variant="ghost" disabled={busy} onClick={() => void refresh()}><RefreshCw size={18} /> Обновить</ExtensionButton>
            <ExtensionButton variant="ghost" onClick={() => void chrome.tabs.create({ url: APP_URL })}>Кабинет <ExternalLink size={18} /></ExtensionButton>
          </div>
          <ExtensionButton variant="danger" onClick={() => void disconnect()}><Unplug size={18} /> Отключить</ExtensionButton>
        </>
      )}
      {(error || state?.lastError) && <ExtensionNotice tone="danger">{error || state?.lastError?.message}</ExtensionNotice>}
    </main>
  );
}

function CommandCard({ state }: { state: StoredState }) {
  const command = state.activeCommand!;
  const copy = commandCopy(command.status, command.result.attentionCount);
  const tone = command.status === "failed" ? "yellow" : command.status === "ready_for_review" ? "mint" : "blue";
  return (
    <ExtensionCard tone={tone}>
      <div className="card-heading"><h2>{command.metadata.jobTitle}</h2><ExtensionBadge tone={copy.tone}>{copy.label}</ExtensionBadge></div>
      <p>{copy.description}</p>
      {command.result.filledCount > 0 && <p className="command-summary">Заполнено: {command.result.filledCount}. Проверить: {command.result.attentionCount}.</p>}
      <ExtensionButton onClick={() => void message({ type: "OPEN_ACTIVE_FORM" })}>Открыть форму <ExternalLink size={18} /></ExtensionButton>
    </ExtensionCard>
  );
}

function commandCopy(status: string, attention: number): { label: string; description: string; tone: "blue" | "yellow" | "mint" | "pink" } {
  if (status === "waiting_for_auth") return { label: "Нужен вход", description: "Войдите на площадку. Продолжим после авторизации.", tone: "yellow" };
  if (status === "partially_filled") return { label: "Проверьте поля", description: `Осталось заполнить вручную: ${attention}.`, tone: "pink" };
  if (status === "ready_for_review") return { label: "Готово", description: "Проверьте форму и отправьте отклик на площадке.", tone: "mint" };
  if (status === "submitted") return { label: "Отправлено", description: "Площадка подтвердила отправку.", tone: "mint" };
  if (status === "failed") return { label: "Не готово", description: "Откройте форму и повторите подготовку.", tone: "pink" };
  return { label: "Готовим", description: "Открываем страницу и заполняем известные поля.", tone: "blue" };
}

function sourceLabel(source: string | null, auth: StoredState["marketplaceAuthState"]): string {
  if (auth === "UNSUPPORTED") return "Текущая страница не поддерживается.";
  if (!source) return "Откройте заказ на поддерживаемой площадке.";
  if (auth === "AUTH_REQUIRED") return "На текущей площадке нужно войти в аккаунт.";
  return `Текущая площадка: ${source.replaceAll("_", ".")}.`;
}

async function message<T = unknown>(payload: BackgroundMessage): Promise<T> {
  const response = await chrome.runtime.sendMessage(payload) as T & { ok?: boolean; error?: string };
  if (response && typeof response === "object" && "ok" in response && response.ok === false) {
    throw new Error(response.error || "Операция не выполнена");
  }
  return response;
}

createRoot(document.getElementById("root")!).render(<StrictMode><Popup /></StrictMode>);
