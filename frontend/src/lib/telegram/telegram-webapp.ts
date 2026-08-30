export type TelegramColorScheme = "light" | "dark";

type TelegramWebApp = {
  initData?: string;
  initDataUnsafe?: { start_param?: string };
  colorScheme?: TelegramColorScheme;
  viewportHeight?: number;
  ready?: () => void;
  expand?: () => void;
  HapticFeedback?: { notificationOccurred: (type: "success" | "warning" | "error") => void };
};

declare global { interface Window { Telegram?: { WebApp?: TelegramWebApp } } }

function webApp(): TelegramWebApp | undefined { return typeof window === "undefined" ? undefined : window.Telegram?.WebApp; }

export const telegramBridge = {
  isAvailable: () => Boolean(webApp()),
  ready: () => { webApp()?.ready?.(); webApp()?.expand?.(); },
  getInitData: () => webApp()?.initData ?? "",
  getColorScheme: (): TelegramColorScheme => webApp()?.colorScheme ?? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"),
  getStartParam: () => webApp()?.initDataUnsafe?.start_param ?? null,
  getViewportHeight: () => webApp()?.viewportHeight,
  hapticSuccess: () => webApp()?.HapticFeedback?.notificationOccurred("success"),
};
