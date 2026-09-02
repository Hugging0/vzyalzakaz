import { ArrowUpRight } from "lucide-react";
import type { ButtonHTMLAttributes, HTMLAttributes, ReactNode } from "react";

export function ExtensionLogo() {
  return <span className="ext-logo" aria-hidden="true"><ArrowUpRight /></span>;
}

export function ExtensionButton({
  children,
  variant = "primary",
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "danger";
}) {
  return <button className={`ext-button ext-button--${variant} ${className}`} {...props}>{children}</button>;
}

export function ExtensionCard({
  children,
  tone = "paper",
  className = "",
  ...props
}: HTMLAttributes<HTMLElement> & {
  children: ReactNode;
  tone?: "paper" | "blue" | "yellow" | "mint";
}) {
  return <section className={`ext-card ext-card--${tone} ${className}`} {...props}>{children}</section>;
}

export function ExtensionBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "blue" | "yellow" | "mint" | "pink";
}) {
  return <span className={`ext-badge ext-badge--${tone}`}>{children}</span>;
}

export function ExtensionNotice({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: "neutral" | "warning" | "success" | "danger";
}) {
  return <div className={`ext-notice ext-notice--${tone}`} role={tone === "danger" ? "alert" : "status"}>{children}</div>;
}
