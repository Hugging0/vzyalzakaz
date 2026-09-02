import { adapterForId } from "./adapters/marketplaces";
import type { ApplicationCommand, ApplicationErrorCode, SiteAdapter } from "./contracts";

export type CommandValidation =
  | { ok: true; adapter: SiteAdapter; url: URL }
  | { ok: false; code: ApplicationErrorCode; message: string };

export function validateCommand(command: ApplicationCommand, now = Date.now()): CommandValidation {
  if (!command.id || !Number.isInteger(command.applicationId) || command.applicationId <= 0) {
    return { ok: false, code: "COMMAND_ALREADY_PROCESSED", message: "Команда имеет некорректный идентификатор" };
  }
  if (!command.expiresAt || Date.parse(command.expiresAt) <= now) {
    return { ok: false, code: "COMMAND_EXPIRED", message: "Срок подготовки отклика истёк" };
  }
  let url: URL;
  try {
    url = new URL(command.jobUrl);
  } catch {
    return { ok: false, code: "UNSUPPORTED_PAGE", message: "Адрес заказа некорректен" };
  }
  const adapter = adapterForId(command.sourceId);
  if (!adapter || !adapter.supports(url) || url.username || url.password) {
    return { ok: false, code: "UNSUPPORTED_SOURCE", message: "Площадка или адрес заказа не поддерживается" };
  }
  return { ok: true, adapter, url };
}
