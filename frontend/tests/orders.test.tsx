import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode, ComponentProps } from "react";
import { WorkspaceShell } from "@/components/layout/WorkspaceShell";
import { OrdersView } from "@/components/features/orders/OrdersView";
import { OrderDetailsPage } from "@/components/features/orders/OrderDetailsPage";
import { AgentSettingsView } from "@/components/features/settings/AgentSettingsView";
import { miniAppApi } from "@/lib/api/client";
import type { Profile } from "@/types/domain";

const navigation = vi.hoisted(() => ({ path: "/app/orders", search: "", push: vi.fn(), replace: vi.fn() }));
vi.mock("next/navigation", () => ({ usePathname: () => navigation.path, useSearchParams: () => new URLSearchParams(navigation.search), useRouter: () => navigation }));
vi.mock("next/link", () => ({ default: ({ children, onClick, ...props }: ComponentProps<"a">) => <a {...props} onClick={(event) => { event.preventDefault(); onClick?.(event); }}>{children}</a> }));
vi.mock("@/lib/api/client", () => ({ miniAppApi: { leads: vi.fn(), lead: vi.fn(), prepareProposal: vi.fn(), skipLead: vi.fn(), sources: vi.fn(), extensionStatus: vi.fn(), applicationCommand: vi.fn(), updateProfile: vi.fn(), setAgentActive: vi.fn() } }));

const profile: Profile = { firstName: "Тест", isActive: true, skills: ["Python"], languages: ["ru"], about: "Разрабатываю ботов и парсеры на Python", minimumBudget: 0, hourlyRate: 0, matchThreshold: 70, specialties: [], projectTypes: [], excludedKeywords: [], preferredSources: [], automationLevel: "drafts", notifications: { strongMatches: true, replies: true, connectionIssues: true }, onboardingCompleted: true };
const lead = { id: 1, opportunity_id: "one", title: "Python-бот и парсер цен", description: "Собирать цены и отправлять уведомления", source: "FL.ru", source_url: "https://example.com/task", budget_label: "10 000 ₽ за проект", final_score: 47.46, analysis: { matched_capabilities: ["Python"] }, dimensions: { skills: { score: 14, label: "Слабо" } }, ranking_version: "hybrid-v4", why_recommended: [{ text: "У вас есть опыт разработки Python-ботов", source_facts: ["task"], profile_facts: ["profile"] }], checks: [], status: "recommended", proposal: null, published_at: "2026-09-09T10:00:00Z", created_at: "2026-09-09T10:00:00Z", apply_mode: "draft_only" };
function wrapper({ children }: { children: ReactNode }) { return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } })}>{children}</QueryClientProvider>; }
afterEach(cleanup);
beforeEach(() => {
  navigation.path = "/app/orders"; navigation.search = "";
  vi.mocked(miniAppApi.leads).mockResolvedValue([lead, { ...lead, id: 2, title: "Скрытый заказ", status: "skipped" }]);
  vi.mocked(miniAppApi.lead).mockResolvedValue(lead);
  vi.mocked(miniAppApi.sources).mockResolvedValue([]);
  vi.mocked(miniAppApi.extensionStatus).mockResolvedValue({ state: "DISCONNECTED" } as never);
  vi.mocked(miniAppApi.applicationCommand).mockResolvedValue(null);
});

describe("orders workflow regressions", () => {
  it("shows a verified recommendation below 60 without rating controls", async () => {
    render(<OrdersView />, { wrapper });
    expect(await screen.findByText(lead.title)).toBeTruthy();
    expect(screen.queryByText("Скрытый заказ")).toBeNull();
    expect(screen.queryByRole("slider")).toBeNull();
    expect(screen.queryByText(/\/100/)).toBeNull();
  });
  it("keeps source and sorting in the detail return link", async () => {
    navigation.search = "source=FL.ru&sort=newest";
    render(<OrdersView />, { wrapper });
    const link = await screen.findByRole("link", { name: "Открыть заказ" });
    expect(link.getAttribute("href")).toContain(encodeURIComponent("/app/orders?source=FL.ru&sort=newest"));
  });
  it("closes mobile menu on bottom navigation, including current route", () => {
    render(<WorkspaceShell profile={profile}><p>Контент</p></WorkspaceShell>, { wrapper });
    const bottom = within(screen.getByRole("navigation", { name: "Быстрая навигация" }));
    for (const name of ["Заказы", "Главная", "Отклики"]) {
      fireEvent.click(bottom.getByRole("button", { name: "Ещё" }));
      expect(screen.getByRole("navigation", { name: "Все разделы" })).toBeTruthy();
      fireEvent.click(bottom.getByRole("link", { name }));
      expect(screen.queryByRole("navigation", { name: "Все разделы" })).toBeNull();
    }
  });
  it("does not resurrect menu after route changes and Back", () => {
    const view = render(<WorkspaceShell profile={profile}><p>Контент</p></WorkspaceShell>, { wrapper });
    fireEvent.click(screen.getByRole("button", { name: "Ещё" }));
    navigation.path = "/app/profile";
    view.rerender(<WorkspaceShell profile={profile}><p>Профиль</p></WorkspaceShell>);
    expect(screen.queryByRole("navigation", { name: "Все разделы" })).toBeNull();
    navigation.path = "/app/orders";
    view.rerender(<WorkspaceShell profile={profile}><p>Заказы</p></WorkspaceShell>);
    expect(screen.queryByRole("navigation", { name: "Все разделы" })).toBeNull();
  });
  it("shows explanation and prepare action, not debug dimensions; handles failure", async () => {
    vi.mocked(miniAppApi.prepareProposal).mockRejectedValue(new Error("Unavailable"));
    render(<OrderDetailsPage id={1} />, { wrapper });
    fireEvent.click(await screen.findByRole("button", { name: "Подготовить отклик" }));
    expect(await screen.findByText("Действие не выполнено. Попробуйте ещё раз.")).toBeTruthy();
    expect(screen.queryByText("Оценка")).toBeNull();
    expect(screen.queryByText(/hybrid|\/100/)).toBeNull();
    expect(navigation.push).not.toHaveBeenCalled();
  });
  it("saves fixed and hourly conditions separately, blank clears a minimum", async () => {
    vi.mocked(miniAppApi.updateProfile).mockResolvedValue(profile);
    render(<AgentSettingsView profile={profile} />, { wrapper });
    fireEvent.change(screen.getByLabelText("Желаемая ставка, ₽/час"), { target: { value: "2000" } });
    fireEvent.click(screen.getByRole("button", { name: "Сохранить настройки" }));
    await screen.findByText("Настройки сохранены.");
    expect(miniAppApi.updateProfile).toHaveBeenCalledWith(expect.objectContaining({ minimumBudget: 0, hourlyRate: 2000 }));
  });
});
