import type {
  ApplicationCommand,
  ApplicationCommandStatus,
  ApplicationErrorCode,
  ApplicationResult,
  MarketplaceAuthState,
  StoredState,
} from "./contracts";

const API_BASE = (import.meta.env.WXT_API_BASE_URL || "https://vzyalzakaz.ru").replace(/\/$/, "");

export class ExtensionApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, token: string | null, init: RequestInit = {}): Promise<T | null> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (response.status === 204) return null;
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Backend unavailable" })) as { detail?: string };
    throw new ExtensionApiError(body.detail || "Backend unavailable", response.status);
  }
  return response.json() as Promise<T>;
}

export async function exchangeLink(code: string, state: StoredState): Promise<{ token: string }> {
  const manifest = chrome.runtime.getManifest();
  return (await request<{ token: string }>("/api/extension/auth/exchange", null, {
    method: "POST",
    body: JSON.stringify({
      code,
      installationId: state.installationId,
      browser: detectBrowser(),
      version: manifest.version,
    }),
  }))!;
}

export async function heartbeat(state: StoredState): Promise<void> {
  await request("/api/extension/heartbeat", state.token, {
    method: "POST",
    body: JSON.stringify({
      version: chrome.runtime.getManifest().version,
      activeSourceId: state.activeSourceId,
      marketplaceAuthState: state.marketplaceAuthState,
      lastErrorCode: state.lastError?.code ?? null,
    }),
  });
}

export async function revokeSession(token: string): Promise<void> {
  await request("/api/extension/session", token, { method: "DELETE" });
}

export async function nextCommand(token: string): Promise<ApplicationCommand | null> {
  return request<ApplicationCommand>("/api/extension/commands/next", token);
}

export async function patchCommand(
  token: string,
  commandId: string,
  status: ApplicationCommandStatus,
  result?: ApplicationResult,
  error?: { code: ApplicationErrorCode; message: string },
): Promise<ApplicationCommand> {
  return (await request<ApplicationCommand>(`/api/extension/commands/${commandId}`, token, {
    method: "PATCH",
    body: JSON.stringify({
      status,
      result,
      errorCode: error?.code,
      errorDetail: error?.message,
    }),
  }))!;
}

export async function sendDiagnostic(
  token: string,
  event: string,
  metadata: Record<string, string | number | boolean | null>,
  commandId?: string,
  level: "info" | "warning" | "error" = "info",
): Promise<void> {
  await request("/api/extension/diagnostics", token, {
    method: "POST",
    body: JSON.stringify({ events: [{ event, level, commandId, metadata }] }),
  });
}

function detectBrowser(): "chrome" | "edge" | "brave" | "yandex" | "chromium" {
  const ua = navigator.userAgent;
  if (ua.includes("Edg/")) return "edge";
  if (ua.includes("YaBrowser/")) return "yandex";
  if ((navigator as Navigator & { brave?: unknown }).brave) return "brave";
  if (ua.includes("Chrome/")) return "chrome";
  return "chromium";
}

export function isSessionError(error: unknown): boolean {
  return error instanceof ExtensionApiError && error.status === 401;
}

export function asBackendError(error: unknown): { code: ApplicationErrorCode; message: string } {
  return {
    code: "BACKEND_UNAVAILABLE",
    message: error instanceof Error ? error.message : "Сервис временно недоступен",
  };
}

export type HeartbeatContext = {
  sourceId: string | null;
  authState: MarketplaceAuthState;
};
