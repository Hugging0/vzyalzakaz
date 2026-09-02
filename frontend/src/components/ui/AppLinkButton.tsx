import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

type Variant = "primary" | "secondary" | "ghost" | "success" | "danger";
type Props = ComponentProps<typeof Link> & { variant?: Variant; children: ReactNode };

export function AppLinkButton({ variant = "primary", className = "", children, ...props }: Props) {
  return <Link className={`app-button app-button--${variant} ${className}`} {...props}>{children}</Link>;
}
