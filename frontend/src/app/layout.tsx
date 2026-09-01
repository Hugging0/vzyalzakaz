import type { Metadata } from "next";
import { Golos_Text, Unbounded } from "next/font/google";
import Script from "next/script";

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
  title: "Взял заказ",
  description: "Подходящие проекты без лишнего шума",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <body className={`${golos.className} ${unbounded.variable}`}>
        <Script src="https://telegram.org/js/telegram-web-app.js" strategy="beforeInteractive" />
        {children}
      </body>
    </html>
  );
}
