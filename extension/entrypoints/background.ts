import {
  asBackendError,
  exchangeLink,
  heartbeat,
  isSessionError,
  nextCommand,
  patchCommand,
  revokeSession,
  sendDiagnostic,
} from "../src/api";
import { adapterForUrl } from "../src/adapters/marketplaces";
import { validateCommand } from "../src/command";
import type {
  ApplicationCommand,
  BackgroundMessage,
  ContentMessage,
  StoredState,
} from "../src/contracts";
import { clearSession, getState, updateState } from "../src/storage";

const SYNC_ALARM = "vzyalzakaz-sync";
const APP_URL = "https://vzyalzakaz.ru/app";
const ALLOWED_APP_ORIGINS = new Set([
  "https://vzyalzakaz.ru",
  "http://localhost",
  "http://127.0.0.1",
]);

export default defineBackground(() => {
  chrome.runtime.onInstalled.addListener(() => void initialize());
  chrome.runtime.onStartup.addListener(() => void initialize());
  chrome.alarms.onAlarm.addListener((alarm) => {
    if (alarm.name === SYNC_ALARM) void sync();
  });
  chrome.runtime.onMessage.addListener((message: BackgroundMessage, _sender, respond) => {
    void handleMessage(message).then(respond).catch((error) => respond({ ok: false, error: safeMessage(error) }));
    return true;
  });
  chrome.runtime.onMessageExternal.addListener((message: BackgroundMessage, sender, respond) => {
    if (!isAllowedAppSender(sender.url)) {
      respond({ ok: false, error: "Источник запроса не разрешён" });
      return false;
    }
    if (message.type !== "LINK" && message.type !== "CHECK_NOW") {
      respond({ ok: false, error: "Команда недоступна для сайта" });
      return false;
    }
    const action = message.type === "LINK" ? link(message.code) : sync();
    void action
      .then(() => respond({ ok: true }))
      .catch((error) => respond({ ok: false, error: safeMessage(error) }));
    return true;
  });
  void initialize();
});

async function initialize(): Promise<void> {
  await getState();
  await chrome.alarms.create(SYNC_ALARM, { periodInMinutes: 0.5 });
  await sync();
}

async function handleMessage(message: BackgroundMessage): Promise<unknown> {
  if (message.type === "GET_STATE") {
    await refreshActivePageContext();
    return getState();
  }
  if (message.type === "LINK") return link(message.code);
  if (message.type === "DISCONNECT") {
    const state = await getState();
    if (state.token) {
      try { await revokeSession(state.token); } catch { /* Local disconnect must still complete. */ }
    }
    return clearSession();
  }
  if (message.type === "CHECK_NOW") return sync();
  if (message.type === "OPEN_ACTIVE_FORM") return focusActiveForm();
  if (message.type === "CONTENT_CONTEXT") {
    return updateState({
      activeSourceId: message.sourceId,
      marketplaceAuthState: message.authState,
    });
  }
  if (message.type === "CONTENT_STATUS") return receiveContentStatus(message);
  return { ok: false };
}

async function link(code: string): Promise<{ ok: true; state: StoredState }> {
  const current = await getState();
  const { token } = await exchangeLink(code.trim(), current);
  const state = await updateState({
    token,
    connection: "CONNECTED",
    lastError: null,
  });
  recordDiagnostic(token, "extension_connected", {
    extensionVersion: chrome.runtime.getManifest().version,
  });
  void sync();
  return { ok: true, state };
}

async function sync(): Promise<{ ok: boolean; state: StoredState }> {
  let state = await getState();
  if (!state.token) return { ok: true, state };
  const token = state.token;
  try {
    await heartbeat(state);
    state = await updateState({
      connection: "CONNECTED",
      lastHeartbeatAt: new Date().toISOString(),
      lastError: null,
    });
    const previousCommandId = state.activeCommand?.id;
    const command = await nextCommand(token);
    if (!command) {
      state = await updateState({ activeCommand: null });
      return { ok: true, state };
    }
    state = await updateState({ activeCommand: command });
    if (command.id !== previousCommandId) {
      recordDiagnostic(token, "command_received", { sourceId: command.sourceId }, command.id);
      recordDiagnostic(token, "adapter_selected", { adapterId: command.sourceId }, command.id);
    }
    await dispatchCommand(command);
    return { ok: true, state: await getState() };
  } catch (error) {
    if (isSessionError(error)) {
      const expired = await clearSession();
      return { ok: false, state: await updateState({ ...expired, connection: "SESSION_EXPIRED" }) };
    }
    const failure = asBackendError(error);
    return {
      ok: false,
      state: await updateState({ connection: "REAUTH_REQUIRED", lastError: failure }),
    };
  }
}

async function dispatchCommand(command: ApplicationCommand): Promise<void> {
  const validation = validateCommand(command);
  if (!validation.ok) {
    await reportCommand(command, validation.code === "COMMAND_EXPIRED" ? "expired" : "failed", undefined, {
      code: validation.code === "COMMAND_EXPIRED" ? "COMMAND_EXPIRED" : "UNSUPPORTED_SOURCE",
      message: validation.message,
    });
    return;
  }
  const { url } = validation;

  try {
    const stableStates = new Set(["partially_filled", "ready_for_review"]);
    if (stableStates.has(command.status)) {
      const tab = await findMatchingTab(url);
      if (!tab?.id) return;
      await sendToTab(tab.id, { type: "MONITOR_APPLICATION", command });
      return;
    }
    if (command.status === "waiting_for_auth") {
      const tab = await findMatchingTab(url);
      if (!tab?.id) return;
      await sendToTab(tab.id, { type: "RUN_APPLICATION", command });
      return;
    }
    const tab = await findOrOpenTab(url, command.status === "delivered");
    if (!tab.id) throw new Error("Не удалось открыть вкладку площадки");
    if (command.status !== "opening_page" && command.status !== "page_ready" && command.status !== "form_found" && command.status !== "filling") {
      command = await patchCommand((await getState()).token!, command.id, "opening_page");
      await updateState({ activeCommand: command });
    }
    await waitForTab(tab.id, 20_000);
    await sendToTab(tab.id, { type: "RUN_APPLICATION", command });
  } catch (error) {
    await reportCommand(command, "failed", undefined, {
      code: "PAGE_LOAD_FAILED",
      message: safeMessage(error),
    });
  }
}

async function receiveContentStatus(message: Extract<BackgroundMessage, { type: "CONTENT_STATUS" }>): Promise<unknown> {
  const state = await getState();
  const command = state.activeCommand;
  if (!state.token || !command) return { ok: false };
  try {
    const updated = await patchCommand(state.token, command.id, message.status, message.result, message.error);
    await updateState({
      activeCommand: updated,
      lastError: message.error ?? null,
    });
    const event = message.status === "submitted"
      ? "application_submitted"
      : message.status === "failed"
        ? "application_failed"
        : message.status === "waiting_for_auth"
          ? "auth_required"
          : message.status === "form_found"
            ? "form_detected"
        : message.status === "ready_for_review" || message.status === "partially_filled"
          ? "application_ready"
          : null;
    if (event) {
      recordDiagnostic(state.token, event, {
        adapterId: command.sourceId,
        adapterVersion: message.result?.adapterVersion ?? null,
        filledCount: message.result?.filledCount ?? 0,
        attentionCount: message.result?.attentionCount ?? 0,
        errorCode: message.error?.code ?? null,
      }, command.id, message.status === "failed" ? "error" : "info");
    }
    if (message.result?.filledCount) {
      recordDiagnostic(state.token, "field_fill_success", {
        adapterId: command.sourceId,
        adapterVersion: message.result.adapterVersion ?? null,
        filledCount: message.result.filledCount,
        attentionCount: message.result.attentionCount,
      }, command.id);
    }
    return { ok: true, command: updated };
  } catch (error) {
    if (isSessionError(error)) await updateState({ connection: "SESSION_EXPIRED", token: null });
    return { ok: false, error: safeMessage(error) };
  }
}

async function reportCommand(
  command: ApplicationCommand,
  status: "failed" | "expired",
  result?: undefined,
  error?: { code: "UNSUPPORTED_SOURCE" | "PAGE_LOAD_FAILED" | "COMMAND_EXPIRED"; message: string },
): Promise<void> {
  const state = await getState();
  if (!state.token) return;
  const updated = await patchCommand(state.token, command.id, status, result, error);
  await updateState({ activeCommand: updated, lastError: error ?? null });
}

async function findMatchingTab(url: URL): Promise<chrome.tabs.Tab | undefined> {
  const tabs = await chrome.tabs.query({});
  return tabs.find((tab) => {
    if (!tab.url) return false;
    const current = safeUrl(tab.url);
    return current?.origin === url.origin && current.pathname === url.pathname;
  });
}

async function findOrOpenTab(url: URL, focusExisting = true): Promise<chrome.tabs.Tab> {
  const existing = await findMatchingTab(url);
  if (existing?.id) {
    if (focusExisting) {
      await chrome.tabs.update(existing.id, { active: true });
      if (existing.windowId) await chrome.windows.update(existing.windowId, { focused: true });
    }
    return existing;
  }
  return chrome.tabs.create({ url: url.toString(), active: true });
}

async function focusActiveForm(): Promise<{ ok: boolean }> {
  const state = await getState();
  if (!state.activeCommand) return { ok: false };
  const url = safeUrl(state.activeCommand.jobUrl);
  if (!url || !adapterForUrl(url)) return { ok: false };
  const tab = await findOrOpenTab(url);
  if (!tab.id) return { ok: false };
  await waitForTab(tab.id, 12_000);
  await sendToTab(tab.id, { type: "FOCUS_ATTENTION_FIELD" });
  return { ok: true };
}

async function refreshActivePageContext(): Promise<void> {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab?.url ? safeUrl(tab.url) : null;
  const adapter = url ? adapterForUrl(url) : null;
  if (!adapter || !tab?.id) {
    await updateState({ activeSourceId: null, marketplaceAuthState: "UNSUPPORTED" });
    return;
  }
  try {
    const context = await chrome.tabs.sendMessage(tab.id, { type: "GET_PAGE_CONTEXT" } satisfies ContentMessage) as {
      sourceId: string | null;
      authState: StoredState["marketplaceAuthState"];
    };
    await updateState({ activeSourceId: context.sourceId, marketplaceAuthState: context.authState });
  } catch {
    await updateState({ activeSourceId: adapter.id, marketplaceAuthState: "UNKNOWN" });
  }
}

async function waitForTab(tabId: number, timeoutMs: number): Promise<void> {
  const current = await chrome.tabs.get(tabId);
  if (current.status === "complete") return;
  await new Promise<void>((resolve, reject) => {
    const timeout = setTimeout(() => finish(new Error("Страница площадки загружается слишком долго")), timeoutMs);
    const listener = (changedId: number, change: { status?: string }) => {
      if (changedId === tabId && change.status === "complete") finish();
    };
    const finish = (error?: Error) => {
      clearTimeout(timeout);
      chrome.tabs.onUpdated.removeListener(listener);
      if (error) reject(error);
      else resolve();
    };
    chrome.tabs.onUpdated.addListener(listener);
  });
}

async function sendToTab(tabId: number, message: ContentMessage): Promise<unknown> {
  try {
    return await chrome.tabs.sendMessage(tabId, message);
  } catch {
    throw new Error("Расширение не получило доступ к странице. Обновите вкладку и повторите.");
  }
}

function safeUrl(value: string): URL | null {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password ? url : null;
  } catch {
    return null;
  }
}

function isAllowedAppSender(senderUrl?: string): boolean {
  if (!senderUrl) return false;
  try {
    return ALLOWED_APP_ORIGINS.has(new URL(senderUrl).origin);
  } catch {
    return false;
  }
}

function safeMessage(error: unknown): string {
  return error instanceof Error ? error.message.slice(0, 180) : "Неизвестная ошибка";
}

function recordDiagnostic(
  token: string,
  event: Parameters<typeof sendDiagnostic>[1],
  metadata: Parameters<typeof sendDiagnostic>[2],
  commandId?: string,
  level: "info" | "warning" | "error" = "info",
): void {
  void sendDiagnostic(token, event, metadata, commandId, level).catch(() => undefined);
}

export { APP_URL };
