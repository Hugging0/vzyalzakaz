import type { ButtonHTMLAttributes, ReactNode } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "ghost" | "success" | "danger"; children: ReactNode };
export function AppButton({ variant = "primary", className = "", children, ...props }: Props) {
  return <button className={`app-button app-button--${variant} ${className}`} {...props}>{children}</button>;
}
