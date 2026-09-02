export type LeadStatus = "recommended" | "approved" | "contacted" | "replied" | "interview" | "won" | "lost" | "skipped";

export interface Lead {
  id: number;
  opportunityId: string;
  title: string;
  description: string;
  source: string;
  sourceUrl: string | null;
  budgetLabel: string;
  matchScore: number;
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
  capabilities: ("collect" | "quick_apply" | "autofill" | "requires_confirmation")[];
  lastRunAt: string | null;
  lastError: string | null;
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
