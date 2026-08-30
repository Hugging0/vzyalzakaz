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
  onboardingCompleted: boolean;
}

export interface PortfolioCase { slug: string; title: string; description: string; skills: string[]; url: string | null; }

export interface PersonalAnalytics { relevant: number; approved: number; sent: number; replied: number; won: number; }
