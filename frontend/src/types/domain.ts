export type LeadStatus = "recommended" | "approved" | "contacted" | "replied" | "interview" | "won" | "lost" | "skipped";

export interface MatchEvidence {
  text: string;
  sourceFacts: string[];
  profileFacts: string[];
}

export interface MatchDimension {
  score: number;
  label: string;
  sourceFacts: string[];
  profileFacts: string[];
}

export interface Lead {
  id: number;
  opportunityId: string;
  title: string;
  description: string;
  source: string;
  sourceUrl: string | null;
  budgetLabel: string;
  economics: {
    normalizedLabel: string | null;
    fxStatus: string;
    fxRate: number | null;
    fxRateDate: string | null;
    fxRateSource: string | null;
    requiresCheck: boolean;
  };
  matchScore: number;
  strengthLabel: string;
  matchConfidence: number;
  dimensions: Record<string, MatchDimension>;
  recommendationReasons: MatchEvidence[];
  checks: MatchEvidence[];
  rankingVersion: string;
  reranked: boolean;
  retrieval: { method: string; score: number; fallbackUsed: boolean };
  fitReasons: string[];
  requiredSkills: string[];
  risks: string[];
  portfolioItem: string | null;
  proposal: string | null;
  status: LeadStatus;
  publishedAt: string | null;
  createdAt: string;
  contactedAt: string | null;
  applyMode: "draft_only" | "send_allowed" | "api_allowed";
}

export interface Profile {
  firstName: string | null;
  isActive: boolean;
  skills: string[];
  languages: string[];
  about: string;
  minimumBudget: number;
  hourlyRate: number;
  matchThreshold: number;
  specialties: string[];
  projectTypes: string[];
  excludedKeywords: string[];
  preferredSources: string[];
  automationLevel: "manual" | "drafts";
  notifications: { strongMatches: boolean; replies: boolean; connectionIssues: boolean };
  onboardingCompleted: boolean;
}

export interface PortfolioCase { slug: string; title: string; description: string; skills: string[]; url: string | null; }

export interface PersonalAnalytics {
  scanned: number;
  relevant: number;
  approved: number;
  sent: number;
  replied: number;
  interviews: number;
  won: number;
  lost: number;
  pendingActions: number;
  responseRate: number;
  estimatedTimeSavedMinutes: number;
  topSources: { source: string; count: number }[];
}

export interface ApplicationEvent {
  id: number;
  event: string;
  detail: string | null;
  actor: "web" | "telegram" | string;
  createdAt: string;
}

export interface SourceConnection {
  name: string;
  displayName: string;
  sourceType: "telegram" | "web" | "rss" | "api";
  enabled: boolean;
  connectionStatus: "connected" | "syncing" | "attention" | "available" | "planned";
  submissionType: "manual" | "api" | "browser_extension";
  capabilities: ("collect" | "quick_apply" | "browser_autofill" | "attachments" | "custom_questions" | "requires_auth" | "requires_confirmation")[];
  lastRunAt: string | null;
  lastError: string | null;
}

export type ExtensionConnectionState = "CONNECTED" | "OFFLINE" | "NOT_DETECTED" | "ERROR";

export interface ExtensionInstallation {
  id: string;
  installationId: string;
  browser: string;
  version: string;
  state: "CONNECTED" | "OFFLINE";
  activeSourceId: string | null;
  marketplaceAuthState: "AUTHENTICATED" | "AUTH_REQUIRED" | "UNKNOWN" | "UNSUPPORTED" | null;
  lastErrorCode: string | null;
  lastSeenAt: string;
  expiresAt: string;
}

export interface ExtensionStatus {
  state: ExtensionConnectionState;
  installations: ExtensionInstallation[];
}

export type ApplicationCommandStatus = "queued" | "delivered" | "opening_page" | "waiting_for_auth" | "page_ready" | "form_found" | "filling" | "partially_filled" | "ready_for_review" | "submitted" | "failed" | "cancelled" | "expired";

export interface ApplicationCommand {
  id: string;
  applicationId: number;
  sourceId: string;
  jobUrl: string;
  status: ApplicationCommandStatus;
  expiresAt: string;
  result: { adapterVersion?: string; filledCount: number; attentionCount: number; filledFields: string[]; attentionFields: string[] };
  error: { code: string; message: string | null } | null;
}

export interface ApplicationAction {
  provider: "hh" | "browser_extension" | "manual";
  status: "ready" | "connection_required" | "resume_required" | "proposal_required" | "processing" | "submitted" | "already_applied" | "external_action_required" | "failed" | "uncertain" | "manual_only" | ApplicationCommandStatus;
  title: string;
  message: string;
  external_url: string | null;
  resume_title: string | null;
  command: ApplicationCommand | null;
  error_code: string | null;
}

export interface HHResume {
  id: string;
  title: string;
  status: string;
  url: string | null;
  updatedAt: string | null;
}

export interface HHConnection {
  configured: boolean;
  status: "not_connected" | "connected" | "reauth_required" | "error";
  accountName: string | null;
  resumes: HHResume[];
  selectedResumeId: string | null;
  lastErrorCode: string | null;
}

export interface BillingStatus {
  available: boolean;
  checkout_available: boolean;
  status: "pending" | "waiting_for_capture" | "succeeded" | "canceled" | null;
  plan: string | null;
  amount_rub?: string;
  confirmation_url?: string | null;
  active_until: string | null;
}
