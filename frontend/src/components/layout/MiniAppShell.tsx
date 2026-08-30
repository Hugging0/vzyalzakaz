import { BarChart3, BriefcaseBusiness, Rss, UserRound } from "lucide-react";
import type { ReactNode } from "react";

type Tab = "feed" | "applications" | "analytics" | "profile";
const tabs = [
  { id: "feed" as const, label: "Лента", Icon: Rss },
  { id: "applications" as const, label: "Отклики", Icon: BriefcaseBusiness },
  { id: "analytics" as const, label: "Статистика", Icon: BarChart3 },
  { id: "profile" as const, label: "Профиль", Icon: UserRound },
];

export function MiniAppShell({ activeTab, onTabChange, children }: { activeTab: Tab; onTabChange: (tab: Tab) => void; children: ReactNode }) {
  return <main className="app-shell"><div className="app-content">{children}</div><nav className="bottom-nav" aria-label="Основная навигация"><div className="bottom-nav-inner">
    {tabs.map(({ id, label, Icon }) => <button key={id} type="button" data-active={activeTab === id} onClick={() => onTabChange(id)}><Icon size={19} strokeWidth={activeTab === id ? 2.4 : 2} /><span>{label}</span></button>)}
  </div></nav></main>;
}
