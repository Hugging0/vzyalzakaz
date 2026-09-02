import { adapterForUrl } from "../src/adapters/marketplaces";
import { focusFirstAttentionField } from "../src/adapters/form";
import type {
  AdapterContext,
  ApplicationCommand,
  ApplicationErrorCode,
  BackgroundMessage,
  ContentMessage,
} from "../src/contracts";

const matches = [
  "https://freelancer.com/*",
  "https://*.freelancer.com/*",
  "https://freelance.ru/*",
  "https://*.freelance.ru/*",
  "https://fl.ru/*",
  "https://*.fl.ru/*",
  "https://kwork.ru/*",
  "https://*.kwork.ru/*",
];

export default defineContentScript({
  matches,
  runAt: "document_idle",
  main() {
    let activeCommand: ApplicationCommand | null = null;
    let submissionObserver: MutationObserver | null = null;

    void reportContext();
    chrome.runtime.onMessage.addListener((message: ContentMessage, _sender, respond) => {
      if (message.type === "GET_PAGE_CONTEXT") {
        void pageContext().then(respond);
        return true;
      }
      if (message.type === "FOCUS_ATTENTION_FIELD") {
        respond({ ok: focusAttention(activeCommand) });
        return false;
      }
      activeCommand = message.command;
      if (message.type === "MONITOR_APPLICATION") {
        monitorSubmission(message.command, () => { submissionObserver = null; });
        respond({ ok: true });
        return false;
      }
      void execute(message.command)
        .then(() => {
          monitorSubmission(message.command, () => { submissionObserver = null; });
          respond({ ok: true });
        })
        .catch((error) => {
          const failure = normalizeFailure(error);
          void reportStatus("failed", undefined, failure);
          respond({ ok: false, error: failure.message });
        });
      return true;
    });

    async function execute(command: ApplicationCommand): Promise<void> {
      if (Date.parse(command.expiresAt) <= Date.now()) {
        throw failure("COMMAND_EXPIRED", "Срок подготовки отклика истёк");
      }
      const context = createContext(command);
      const adapter = adapterForUrl(context.url);
      if (!adapter || adapter.id !== command.sourceId) {
        throw failure("UNSUPPORTED_SOURCE", "Эта страница не соответствует площадке заказа");
      }
      await sendContext(adapter.id, adapter.detectAuthState(context));
      const authState = adapter.detectAuthState(context);
      if (authState === "AUTH_REQUIRED" || adapter.detectPage(context) === "login") {
        await reportStatus("waiting_for_auth", undefined, {
          code: "AUTH_REQUIRED",
          message: "Войдите на площадку — после входа продолжим автоматически",
        });
        return;
      }
      if (["delivered", "opening_page", "waiting_for_auth"].includes(command.status)) {
        await reportStatus("page_ready");
      }
      const form = adapter.detectApplicationForm(context) ?? await adapter.openApplicationForm(context);
      if (!form) throw failure("FORM_NOT_FOUND", "Форма отклика не найдена. Возможно, площадка изменила страницу.");
      if (["delivered", "opening_page", "waiting_for_auth", "page_ready"].includes(command.status)) {
        await reportStatus("form_found");
      }
      if (command.status !== "filling") await reportStatus("filling");
      const result = await adapter.fillApplication(context, form);
      await reportStatus(result.status, result);
    }

    function monitorSubmission(command: ApplicationCommand, done: () => void): void {
      submissionObserver?.disconnect();
      const context = createContext(command);
      const adapter = adapterForUrl(context.url);
      if (!adapter) return;
      const check = () => {
        const freshContext = { ...context, url: new URL(location.href) };
        if (!adapter.detectSubmissionResult(freshContext)) return;
        submissionObserver?.disconnect();
        void reportStatus("submitted");
        done();
      };
      submissionObserver = new MutationObserver(check);
      submissionObserver.observe(document.documentElement, { childList: true, subtree: true });
      window.addEventListener("pageshow", check, { once: true });
      check();
    }
  },
});

function createContext(command: ApplicationCommand): AdapterContext {
  return { command, document, url: new URL(location.href) };
}

function focusAttention(command: ApplicationCommand | null): boolean {
  if (!command) return false;
  const context = createContext(command);
  const form = adapterForUrl(context.url)?.detectApplicationForm(context);
  return form ? focusFirstAttentionField(form) : false;
}

async function reportContext(): Promise<void> {
  const context = await pageContext();
  await sendContext(context.sourceId, context.authState);
}

async function pageContext() {
  const url = new URL(location.href);
  const adapter = adapterForUrl(url);
  if (!adapter) return { sourceId: null, authState: "UNSUPPORTED" as const };
  const emptyCommand = { sourceId: adapter.id } as ApplicationCommand;
  const context = { command: emptyCommand, document, url };
  return { sourceId: adapter.id, authState: adapter.detectAuthState(context) };
}

async function sendContext(sourceId: string | null, authState: "AUTHENTICATED" | "AUTH_REQUIRED" | "UNKNOWN" | "UNSUPPORTED"): Promise<void> {
  await chrome.runtime.sendMessage({ type: "CONTENT_CONTEXT", sourceId, authState } satisfies BackgroundMessage);
}

async function reportStatus(
  status: Extract<BackgroundMessage, { type: "CONTENT_STATUS" }>["status"],
  result?: Extract<BackgroundMessage, { type: "CONTENT_STATUS" }>["result"],
  error?: Extract<BackgroundMessage, { type: "CONTENT_STATUS" }>["error"],
): Promise<void> {
  await chrome.runtime.sendMessage({ type: "CONTENT_STATUS", status, result, error } satisfies BackgroundMessage);
}

function failure(code: ApplicationErrorCode, message: string): Error & { code: ApplicationErrorCode } {
  return Object.assign(new Error(message), { code });
}

function normalizeFailure(error: unknown): { code: ApplicationErrorCode; message: string } {
  if (error instanceof Error && "code" in error) {
    return { code: (error as Error & { code: ApplicationErrorCode }).code, message: error.message };
  }
  return { code: "FORM_CHANGED", message: error instanceof Error ? error.message : "Не удалось заполнить форму" };
}
