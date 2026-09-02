import type { Metadata } from "next";
import { Golos_Text, Unbounded } from "next/font/google";

import { AppProviders } from "@/components/providers/AppProviders";
import { PwaRegistration } from "@/components/pwa/PwaRegistration";
import "./globals.css";

const golos = Golos_Text({
  subsets: ["latin", "cyrillic"],
  weight: "variable",
  display: "swap",
});

const unbounded = Unbounded({
  subsets: ["latin", "cyrillic"],
  weight: ["600", "700"],
  display: "swap",
  variable: "--font-display",
});

export const metadata: Metadata = {
  applicationName: "ВзялЗаказ",
  title: { default: "ВзялЗаказ", template: "%s | ВзялЗаказ" },
  description: "Подходящие проекты без лишнего шума",
  manifest: "/manifest.webmanifest",
  appleWebApp: { capable: true, statusBarStyle: "default", title: "ВзялЗаказ" },
  icons: { icon: "/icon.svg", apple: "/icon-192.png" },
};

export const viewport = {
  width: "device-width",
  initialScale: 1,
  viewportFit: "cover" as const,
  themeColor: "#F6F3EC",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body className={`${golos.className} ${unbounded.variable}`}>
        <AppProviders>
          <PwaRegistration />
          {children}
        </AppProviders>
      </body>
    </html>
  );
}
