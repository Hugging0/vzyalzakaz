import type { ApplicationAction, ApplicationCommand, ApplicationEvent, BillingStatus, ExtensionStatus, HHConnection, LeadStatus, PersonalAnalytics, PortfolioCase, Profile, SourceConnection } from "@/types/domain";

const sessionKey = "hunt-agent-session";

export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

export function getSessionToken(): string | null { return window.sessionStorage.getItem(sessionKey); }
export function setSessionToken(token: string): void { window.sessionStorage.setItem(sessionKey, token); }
export function clearSessionToken(): void { window.sessionStorage.removeItem(sessionKey); }

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = getSessionToken();
  const response = await fetch(path, {
    ...init,
    credentials: "include",
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
  bootstrapWebSession: () => request<{ authenticated: boolean }>("/api/web/auth/bootstrap", { method: "POST" }),
  exchangeWebTicket: (ticket: string) => request<{ authenticated: boolean }>("/api/web/auth/exchange", { method: "POST", body: JSON.stringify({ ticket }) }),
  logout: () => request<{ authenticated: boolean }>("/api/web/auth/logout", { method: "POST" }),
  me: () => request<Profile>("/api/app/me"),
  completeOnboarding: (payload: { about: string; minimumBudget?: number }) => request<Profile>("/api/app/onboarding", { method: "POST", body: JSON.stringify(payload) }),
  updateProfile: (payload: Partial<Profile>) => request<Profile>("/api/app/me", { method: "PATCH", body: JSON.stringify(payload) }),
  leads: (filters: { status?: LeadStatus; minimumScore?: number; source?: string; limit?: number; offset?: number } = {}) => {
    const params = new URLSearchParams();
    if (filters.status) params.set("status", filters.status);
    if (filters.minimumScore) params.set("minimum_score", String(filters.minimumScore));
    if (filters.source) params.set("source", filters.source);
    params.set("limit", String(filters.limit ?? 200));
    if (filters.offset) params.set("offset", String(filters.offset));
    const query = params.size ? `?${params.toString()}` : "";
    return request<unknown[]>(`/api/app/leads${query}`);
  },
  lead: (id: number) => request<unknown>(`/api/app/leads/${id}`),
  leadEvents: (id: number) => request<ApplicationEvent[]>(`/api/app/leads/${id}/events`),
  skipLead: (id: number) => request<void>(`/api/app/leads/${id}/skip`, { method: "POST" }),
  prepareProposal: (id: number) => request<{ proposal: string }>(`/api/app/leads/${id}/proposal`, { method: "POST" }),
  updateProposal: (id: number, proposal: string) => request<{ proposal: string }>(`/api/app/leads/${id}/proposal`, { method: "PATCH", body: JSON.stringify({ proposal }) }),
  markSent: (id: number) => request<void>(`/api/app/leads/${id}/contacted`, { method: "POST" }),
  updateLeadStatus: (id: number, status: LeadStatus, detail?: string) => request<{ status: LeadStatus }>(`/api/app/leads/${id}/status`, { method: "PATCH", body: JSON.stringify({ status, detail }) }),
  analytics: () => request<PersonalAnalytics>("/api/app/analytics"),
  portfolio: () => request<PortfolioCase[]>("/api/app/portfolio"),
  addPortfolio: (item: Omit<PortfolioCase, "slug">) => request<PortfolioCase>("/api/app/portfolio", { method: "POST", body: JSON.stringify(item) }),
  updatePortfolio: (slug: string, item: Partial<Omit<PortfolioCase, "slug">>) => request<PortfolioCase>(`/api/app/portfolio/${encodeURIComponent(slug)}`, { method: "PATCH", body: JSON.stringify(item) }),
  deletePortfolio: (slug: string) => request<{ deleted: boolean }>(`/api/app/portfolio/${encodeURIComponent(slug)}`, { method: "DELETE" }),
  sources: () => request<SourceConnection[]>("/api/app/sources"),
  extensionStatus: () => request<ExtensionStatus>("/api/app/extension/status"),
  createExtensionLink: () => request<{ code: string; expiresAt: string }>("/api/app/extension/link-tickets", { method: "POST" }),
  disconnectExtension: (installationId: string) => request<{ disconnected: boolean }>(`/api/app/extension/installations/${encodeURIComponent(installationId)}`, { method: "DELETE" }),
  queueApplication: (id: number, idempotencyKey: string) => request<ApplicationCommand>(`/api/app/leads/${id}/application-command`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey } }),
  applicationCommand: (id: number) => request<ApplicationCommand | null>(`/api/app/leads/${id}/application-command`),
  application: (id: number) => request<ApplicationAction>(`/api/app/leads/${id}/application`),
  submitApplication: (id: number, idempotencyKey: string) => request<ApplicationAction>(`/api/app/leads/${id}/application`, { method: "POST", headers: { "Idempotency-Key": idempotencyKey } }),
  hhConnection: () => request<HHConnection>("/api/app/connections/hh"),
  startHHOAuth: (agreementAccepted: boolean) => request<{ authorizeUrl: string }>("/api/app/connections/hh/oauth/start", { method: "POST", body: JSON.stringify({ agreement_accepted: agreementAccepted }) }),
  refreshHHResumes: () => request<HHConnection>("/api/app/connections/hh/resumes/refresh", { method: "POST" }),
  selectHHResume: (resumeId: string) => request<HHConnection>("/api/app/connections/hh/resume", { method: "PATCH", body: JSON.stringify({ resume_id: resumeId }) }),
  disconnectHH: () => request<HHConnection>("/api/app/connections/hh", { method: "DELETE" }),
  setAgentActive: (isActive: boolean) => request<Profile>("/api/app/agent", { method: "PATCH", body: JSON.stringify({ is_active: isActive }) }),
  billing: () => request<BillingStatus>("/api/app/billing"),
  createCheckout: (idempotencyKey: string) => request<BillingStatus>("/api/app/billing/checkout", { method: "POST", headers: { "Idempotency-Key": idempotencyKey } }),
  refreshBilling: () => request<BillingStatus>("/api/app/billing/refresh", { method: "POST" }),
};
