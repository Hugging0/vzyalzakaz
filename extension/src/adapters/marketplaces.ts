import { createMarketplaceAdapter } from "./factory";

const safeCapabilities = ["browser_autofill", "custom_questions", "requires_auth", "requires_confirmation"] as const;

export const freelancerAdapter = createMarketplaceAdapter({
  id: "freelancer_com",
  displayName: "Freelancer",
  version: "1.0.0",
  hosts: ["freelancer.com"],
  jobPaths: [/^\/projects\//i],
  loginPaths: [/^\/login/i],
  authSelectors: ["[data-testid='user-menu']", "app-user-card", "a[href*='/dashboard']"],
  unauthSelectors: ["form[action*='login']", "a[href*='/login']"],
  formSelectors: ["form[data-testid*='bid' i]", "form[action*='bid' i]", "app-project-view-submit-bid form", "[data-testid='bid-form']"],
  applySelectors: ["[data-testid='place-bid-button']", "button[data-action='bid']"],
  applyLabels: [/place\s+(a\s+)?bid/i, /bid\s+on\s+this/i, /submit\s+proposal/i],
  successSelectors: ["[data-testid='bid-success']", "app-bid-award-status"],
  successLabels: [/your bid has been placed/i, /bid submitted successfully/i],
  fields: [
    { key: "cover_letter", title: "Текст отклика", selectors: ["textarea[data-testid='bid-description']", "textarea[name='description']"], labels: [] },
    { key: "rate", title: "Ставка", selectors: ["input[data-testid='bid-amount']", "input[name='bidAmount']"], labels: [] },
  ],
  capabilities: safeCapabilities,
});

export const freelanceRuAdapter = createMarketplaceAdapter({
  id: "freelance_ru",
  displayName: "Freelance.ru",
  version: "1.0.0",
  hosts: ["freelance.ru"],
  jobPaths: [/^\/task\//i, /^\/projects\//i],
  loginPaths: [/^\/login/i, /^\/users\/login/i],
  authSelectors: ["a[href*='/users/logout']", ".user-profile", "[data-user-id]"],
  unauthSelectors: ["form[action*='login']", "a[href*='/login']"],
  formSelectors: ["form[action*='proposal']", "form[action*='offer']", ".bargain-form form", "#offer-form"],
  applySelectors: ["a[href*='proposal']", "button[data-action='respond']"],
  applyLabels: [/откликнуться/i, /предложить\s+услуги/i, /оставить\s+предложение/i],
  successSelectors: [".alert-success", ".proposal-success"],
  successLabels: [/предложение\s+отправлено/i, /отклик\s+размещён/i],
  fields: [
    { key: "cover_letter", title: "Текст отклика", selectors: ["textarea[name='comment']", "textarea[name='proposal']"], labels: [] },
    { key: "rate", title: "Стоимость", selectors: ["input[name='price']", "input[name='budget']"], labels: [] },
  ],
  capabilities: [...safeCapabilities, "attachments"],
});

export const flRuAdapter = createMarketplaceAdapter({
  id: "fl_ru",
  displayName: "FL.ru",
  version: "1.0.0",
  hosts: ["fl.ru"],
  jobPaths: [/^\/projects\//i],
  loginPaths: [/^\/login/i],
  authSelectors: ["a[href*='/logout']", ".b-user-block", "[data-id-user]"],
  unauthSelectors: ["form[action*='login']", "a[href*='/login']"],
  formSelectors: ["form[action*='/projects/']", "#project-offer-form", ".b-layout__txt_padbot_20 form"],
  applySelectors: ["a[href*='offer']", "button[data-action='offer']"],
  applyLabels: [/ответить\s+на\s+проект/i, /оставить\s+предложение/i, /откликнуться/i],
  successSelectors: [".b-fon_bg_green", ".project-offer-success"],
  successLabels: [/ваше\s+предложение\s+опубликовано/i, /отклик\s+отправлен/i],
  fields: [
    { key: "cover_letter", title: "Текст отклика", selectors: ["textarea[name='descr']", "textarea[name='message']"], labels: [] },
    { key: "rate", title: "Стоимость", selectors: ["input[name='cost']", "input[name='price']"], labels: [] },
  ],
  capabilities: [...safeCapabilities, "attachments"],
});

export const kworkAdapter = createMarketplaceAdapter({
  id: "kwork_projects",
  displayName: "Kwork",
  version: "1.0.0",
  hosts: ["kwork.ru"],
  jobPaths: [/^\/projects\//i, /^\/project\//i],
  loginPaths: [/^\/login/i],
  authSelectors: ["a[href*='/user/']", ".user-avatar", "[data-user-id]"],
  unauthSelectors: ["form[action*='login']", "a[href*='/login']"],
  formSelectors: ["form[action*='offer']", ".offer-form", "#offer-form"],
  applySelectors: ["button[data-action='offer']", "a[href*='offer']"],
  applyLabels: [/предложить\s+услуги/i, /откликнуться/i, /подать\s+предложение/i],
  successSelectors: [".offer-success", ".alert-success"],
  successLabels: [/предложение\s+отправлено/i, /отклик\s+отправлен/i],
  fields: [
    { key: "cover_letter", title: "Текст отклика", selectors: ["textarea[name='comment']", "textarea[name='description']"], labels: [] },
    { key: "rate", title: "Стоимость", selectors: ["input[name='price']", "input[name='budget']"], labels: [] },
  ],
  capabilities: [...safeCapabilities, "attachments"],
});

export const hhAdapter = createMarketplaceAdapter({
  id: "hh",
  displayName: "HH",
  version: "1.0.0",
  hosts: ["hh.ru"],
  jobPaths: [/^\/vacancy\//i],
  loginPaths: [/^\/account\/login/i, /^\/login/i],
  authSelectors: ["[data-qa='mainmenu_applicantProfile']", "a[href*='/applicant/resumes']"],
  unauthSelectors: ["form[action*='login']", "[data-qa='login']", "a[href*='/account/login']"],
  formSelectors: ["form[data-qa*='vacancy-response' i]", "[data-qa='vacancy-response-popup'] form", "form[action*='negotiation']"],
  applySelectors: ["[data-qa='vacancy-response-link-top']", "[data-qa='vacancy-response-link-bottom']", "[data-qa='vacancy-response-link']"],
  applyLabels: [/откликнуться/i, /respond/i],
  successSelectors: ["[data-qa='vacancy-response-link-view-topic']", "[data-qa='vacancy-response-success']"],
  successLabels: [/отклик\s+отправлен/i, /вы\s+откликнулись/i, /response\s+sent/i],
  fields: [
    { key: "cover_letter", title: "Сопроводительное письмо", selectors: ["textarea[data-qa*='response' i]", "textarea[name='message']"], labels: [] },
  ],
  capabilities: safeCapabilities,
});

export const adapters = [freelancerAdapter, freelanceRuAdapter, flRuAdapter, kworkAdapter, hhAdapter] as const;

export function adapterForUrl(url: URL) {
  return adapters.find((adapter) => adapter.supports(url)) ?? null;
}

export function adapterForId(id: string) {
  return adapters.find((adapter) => adapter.id === id) ?? null;
}
