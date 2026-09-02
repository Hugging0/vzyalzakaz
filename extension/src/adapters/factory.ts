import type { AdapterContext, SiteAdapter } from "../contracts";
import {
  buttonByText,
  fillKnownFields,
  queryAny,
  waitForElement,
  type FieldDefinition,
} from "./form";

export interface MarketplaceAdapterConfig {
  id: string;
  displayName: string;
  version: string;
  hosts: readonly string[];
  jobPaths: readonly RegExp[];
  loginPaths: readonly RegExp[];
  authSelectors: readonly string[];
  unauthSelectors: readonly string[];
  formSelectors: readonly string[];
  applySelectors: readonly string[];
  applyLabels: readonly RegExp[];
  successSelectors: readonly string[];
  successLabels: readonly RegExp[];
  fields: readonly FieldDefinition[];
  capabilities: readonly string[];
}

export function createMarketplaceAdapter(config: MarketplaceAdapterConfig): SiteAdapter {
  return {
    id: config.id,
    displayName: config.displayName,
    version: config.version,
    hosts: config.hosts,
    supports(url) {
      const host = url.hostname.toLocaleLowerCase();
      return url.protocol === "https:" && config.hosts.some((item) => host === item || host.endsWith(`.${item}`));
    },
    detectPage({ document, url }) {
      if (config.loginPaths.some((pattern) => pattern.test(url.pathname))) return "login";
      if (queryAny(document, config.formSelectors)) return "application";
      if (config.jobPaths.some((pattern) => pattern.test(url.pathname))) return "job";
      return "unsupported";
    },
    detectAuthState({ document }) {
      if (queryAny(document, config.authSelectors)) return "AUTHENTICATED";
      if (queryAny(document, config.unauthSelectors)) return "AUTH_REQUIRED";
      return "UNKNOWN";
    },
    detectApplicationForm({ document }) {
      return queryAny(document, config.formSelectors);
    },
    async openApplicationForm(context) {
      const existing = this.detectApplicationForm(context);
      if (existing) return existing;
      const trigger = queryAny(context.document, config.applySelectors)
        ?? buttonByText(context.document, config.applyLabels);
      if (!trigger || !(trigger instanceof HTMLElement)) return null;
      trigger.click();
      return waitForElement(context.document, config.formSelectors);
    },
    fillApplication(context, form) {
      return fillKnownFields(form, context.command, config.fields, config.version);
    },
    detectSubmissionResult({ document }) {
      if (queryAny(document, config.successSelectors)) return true;
      const notifications = [...document.querySelectorAll<HTMLElement>(
        "[role='alert'], [role='status'], .alert, .notification, .toast",
      )];
      return notifications.some((element) => {
        const style = getComputedStyle(element);
        if (style.display === "none" || style.visibility === "hidden" || element.hidden) return false;
        const text = (element.textContent || "").replace(/\s+/g, " ").trim();
        return config.successLabels.some((pattern) => pattern.test(text));
      });
    },
    getCapabilities() {
      return config.capabilities;
    },
  };
}
