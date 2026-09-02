export const commandStatuses = [
  "queued",
  "delivered",
  "opening_page",
  "waiting_for_auth",
  "page_ready",
  "form_found",
  "filling",
  "partially_filled",
  "ready_for_review",
  "submitted",
  "failed",
  "cancelled",
  "expired",
] as const;

export type ApplicationCommandStatus = (typeof commandStatuses)[number];
export type ExtensionConnectionState = "DISCONNECTED" | "CONNECTED" | "SESSION_EXPIRED" | "REAUTH_REQUIRED";
export type MarketplaceAuthState = "AUTHENTICATED" | "AUTH_REQUIRED" | "UNKNOWN" | "UNSUPPORTED";
export type ApplicationErrorCode =
  | "UNSUPPORTED_SOURCE"
  | "UNSUPPORTED_PAGE"
  | "AUTH_REQUIRED"
  | "FORM_NOT_FOUND"
  | "FORM_CHANGED"
  | "FIELD_NOT_FOUND"
  | "FIELD_VALIDATION_FAILED"
  | "PAGE_LOAD_FAILED"
  | "COMMAND_EXPIRED"
  | "COMMAND_ALREADY_PROCESSED"
  | "EXTENSION_OFFLINE"
  | "BACKEND_UNAVAILABLE";

export interface PortfolioCase {
  slug: string;
  title: string;
  description: string;
  skills: string[];
  url: string | null;
}

export interface ApplicationCommand {
  id: string;
  applicationId: number;
  sourceId: string;
  jobUrl: string;
  coverLetter: string;
  selectedPortfolioCase: PortfolioCase | null;
  knownAnswers: Record<string, string | number | boolean | null>;
  attachments: { name: string; url: string }[];
  metadata: {
    jobTitle: string;
    sourceName: string;
    requiresConfirmation: boolean;
    canSubmit: boolean;
  };
  status: ApplicationCommandStatus;
  expiresAt: string;
  result: ApplicationResult;
  error: { code: ApplicationErrorCode; message: string | null } | null;
}

export interface ApplicationResult {
  adapterVersion?: string;
  filledCount: number;
  attentionCount: number;
  filledFields: string[];
  attentionFields: string[];
}

export interface AdapterContext {
  command: ApplicationCommand;
  document: Document;
  url: URL;
}

export interface AdapterExecutionResult extends ApplicationResult {
  status: "ready_for_review" | "partially_filled";
}

export interface SiteAdapter {
  id: string;
  displayName: string;
  version: string;
  hosts: readonly string[];
  supports(url: URL): boolean;
  detectPage(context: AdapterContext): "job" | "application" | "login" | "unsupported";
  detectAuthState(context: AdapterContext): MarketplaceAuthState;
  detectApplicationForm(context: AdapterContext): Element | null;
  openApplicationForm(context: AdapterContext): Promise<Element | null>;
  fillApplication(context: AdapterContext, form: Element): Promise<AdapterExecutionResult>;
  detectSubmissionResult(context: AdapterContext): boolean;
  getCapabilities(): readonly string[];
}

export interface StoredState {
  installationId: string;
  token: string | null;
  connection: ExtensionConnectionState;
  lastHeartbeatAt: string | null;
  activeSourceId: string | null;
  marketplaceAuthState: MarketplaceAuthState;
  activeCommand: ApplicationCommand | null;
  lastError: { code: ApplicationErrorCode; message: string } | null;
}

export type BackgroundMessage =
  | { type: "GET_STATE" }
  | { type: "LINK"; code: string }
  | { type: "DISCONNECT" }
  | { type: "CHECK_NOW" }
  | { type: "OPEN_ACTIVE_FORM" }
  | { type: "CONTENT_STATUS"; status: ApplicationCommandStatus; result?: ApplicationResult; error?: { code: ApplicationErrorCode; message: string } }
  | { type: "CONTENT_CONTEXT"; sourceId: string | null; authState: MarketplaceAuthState };

export type ContentMessage =
  | { type: "RUN_APPLICATION"; command: ApplicationCommand }
  | { type: "MONITOR_APPLICATION"; command: ApplicationCommand }
  | { type: "FOCUS_ATTENTION_FIELD" }
  | { type: "GET_PAGE_CONTEXT" };
