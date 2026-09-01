import type { BillingStatus, PersonalAnalytics, PortfolioCase, Profile } from "@/types/domain";

const sessionKey = "hunt-agent-session";

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

export function getSessionToken(): string | null { return window.sessionStorage.getItem(sessionKey); }
export function setSessionToken(token: string): void { window.sessionStorage.setItem(sessionKey, token); }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getSessionToken();
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}), ...init.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ detail: "Не удалось выполнить запрос" }));
    throw new ApiError(typeof body.detail === "string" ? body.detail : "Не удалось выполнить запрос", response.status);
  }
  return response.json() as Promise<T>;
}

export const miniAppApi = {
  auth: (initData: string) => request<{ token: string }>("/api/mini-app/auth", { method: "POST", body: JSON.stringify({ init_data: initData }) }),
  devAuth: () => request<{ token: string }>("/api/mini-app/auth/dev", { method: "POST" }),
  me: () => request<Profile>("/api/app/me"),
  completeOnboarding: (payload: { about: string; minimumBudget?: number }) => request<Profile>("/api/app/onboarding", { method: "POST", body: JSON.stringify(payload) }),
  updateProfile: (payload: Partial<Profile>) => request<Profile>("/api/app/me", { method: "PATCH", body: JSON.stringify(payload) }),
  leads: () => request<unknown[]>("/api/app/leads"),
  skipLead: (id: number) => request<void>(`/api/app/leads/${id}/skip`, { method: "POST" }),
  prepareProposal: (id: number) => request<{ proposal: string }>(`/api/app/leads/${id}/proposal`, { method: "POST" }),
  updateProposal: (id: number, proposal: string) => request<{ proposal: string }>(`/api/app/leads/${id}/proposal`, { method: "PATCH", body: JSON.stringify({ proposal }) }),
  markSent: (id: number) => request<void>(`/api/app/leads/${id}/contacted`, { method: "POST" }),
  analytics: () => request<PersonalAnalytics>("/api/app/analytics"),
  portfolio: () => request<PortfolioCase[]>("/api/app/portfolio"),
  addPortfolio: (item: Omit<PortfolioCase, "slug">) => request<PortfolioCase>("/api/app/portfolio", { method: "POST", body: JSON.stringify(item) }),
  setAgentActive: (isActive: boolean) => request<Profile>("/api/app/agent", { method: "PATCH", body: JSON.stringify({ is_active: isActive }) }),
  billing: () => request<BillingStatus>("/api/app/billing"),
  createCheckout: (idempotencyKey: string) => request<BillingStatus>("/api/app/billing/checkout", { method: "POST", headers: { "Idempotency-Key": idempotencyKey } }),
  refreshBilling: () => request<BillingStatus>("/api/app/billing/refresh", { method: "POST" }),
};
