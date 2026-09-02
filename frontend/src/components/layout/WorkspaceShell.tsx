"use client";

import { useQueryClient } from "@tanstack/react-query";
import { BarChart3, BellRing, BriefcaseBusiness, Cable, FolderKanban, LayoutDashboard, LogOut, Menu, Search, Settings2, UserRound, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useState, type ReactNode } from "react";

import { AppLogo } from "@/components/ui/AppLogo";
import { miniAppApi } from "@/lib/api/client";
import type { Profile } from "@/types/domain";

const navigation = [
  { href: "/app/today", label: "Главная", Icon: LayoutDashboard },
  { href: "/app/orders", label: "Заказы", Icon: Search },
  { href: "/app/applications", label: "Отклики", Icon: BriefcaseBusiness },
  { href: "/app/portfolio", label: "Портфолио", Icon: FolderKanban },
  { href: "/app/connections", label: "Площадки", Icon: Cable },
  { href: "/app/analytics", label: "Статистика", Icon: BarChart3 },
  { href: "/app/profile", label: "Профиль", Icon: UserRound },
  { href: "/app/settings", label: "Настройки агента", Icon: Settings2 },
] as const;

function isActive(pathname: string, href: string): boolean {
  return pathname === href || (href !== "/app/today" && pathname.startsWith(`${href}/`));
}

export function WorkspaceShell({ profile, children }: { profile: Profile; children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const client = useQueryClient();
  const [mobileMenu, setMobileMenu] = useState(false);
  const logout = async () => {
    await miniAppApi.logout();
    client.clear();
    router.replace("/login");
  };
  return (
    <div className="workspace-shell">
      <aside className="desktop-sidebar">
        <Link className="brand-link" href="/app/today" aria-label="ВзялЗаказ, главная"><AppLogo /></Link>
        <nav className="side-nav" aria-label="Основная навигация">
          {navigation.map(({ href, label, Icon }) => <Link key={href} href={href} data-active={isActive(pathname, href)}><Icon size={20} /><span>{label}</span></Link>)}
        </nav>
        <div className="sidebar-footer">
          <div className="agent-compact"><BellRing size={18} /><span><strong>{profile.isActive ? "Агент работает" : "Агент на паузе"}</strong><small>{profile.matchThreshold}% для уведомлений</small></span></div>
          <button className="nav-action" type="button" onClick={() => void logout()}><LogOut size={18} /><span>Выйти</span></button>
        </div>
      </aside>
      <div className="workspace-main">
        <header className="mobile-masthead"><Link href="/app/today" aria-label="ВзялЗаказ, главная"><AppLogo /></Link><button type="button" aria-label={mobileMenu ? "Закрыть меню" : "Открыть меню"} onClick={() => setMobileMenu((value) => !value)}>{mobileMenu ? <X size={22} /> : <Menu size={22} />}</button></header>
        {mobileMenu && <nav className="mobile-menu" aria-label="Все разделы">{navigation.slice(3).map(({ href, label, Icon }) => <Link key={href} href={href} data-active={isActive(pathname, href)} onClick={() => setMobileMenu(false)}><Icon size={20} />{label}</Link>)}<button type="button" onClick={() => void logout()}><LogOut size={20} />Выйти</button></nav>}
        <main id="main-content" className="workspace-content">{children}</main>
      </div>
      <nav className="mobile-bottom-nav" aria-label="Быстрая навигация">
        {navigation.slice(0, 3).map(({ href, label, Icon }) => <Link key={href} href={href} data-active={isActive(pathname, href)}><Icon size={20} /><span>{label}</span></Link>)}
        <button type="button" data-active={mobileMenu} onClick={() => setMobileMenu((value) => !value)}><Menu size={20} /><span>Ещё</span></button>
      </nav>
    </div>
  );
}
