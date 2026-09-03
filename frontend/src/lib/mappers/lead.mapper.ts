import type { Lead, LeadStatus, MatchDimension, MatchEvidence } from "@/types/domain";

type EvidenceDto = { text?: string; source_facts?: string[]; profile_facts?: string[] };
type DimensionDto = { score?: number; label?: string; source_facts?: string[]; profile_facts?: string[] };

type LeadDto = {
  id: number; opportunity_id: string; title: string; description: string; source: string; source_url: string | null;
  budget_label: string; final_score: number;
  economics?: { normalized_label?: string | null; fx_status?: string; fx_rate?: number | null; fx_rate_date?: string | null; fx_rate_source?: string | null; requires_check?: boolean };
  analysis: { fit_reason?: string; required_skills?: string[]; risks?: string[]; matched_capabilities?: string[] };
  strength_label?: string; match_confidence?: number; dimensions?: Record<string, DimensionDto>;
  why_recommended?: EvidenceDto[]; checks?: EvidenceDto[]; ranking_version?: string; reranked?: boolean;
  retrieval?: { method?: string; score?: number; fallback_used?: boolean };
  portfolio_item: string | null; proposal: string | null; status: LeadStatus; published_at: string | null;
  created_at: string; contacted_at: string | null; apply_mode: Lead["applyMode"];
};

export function mapLeadDtoToLead(dto: LeadDto): Lead {
  const evidence = (items: EvidenceDto[] = []): MatchEvidence[] => items
    .filter((item) => Boolean(item.text?.trim()))
    .map((item) => ({ text: item.text!.trim(), sourceFacts: item.source_facts ?? [], profileFacts: item.profile_facts ?? [] }));
  const dimensions = Object.fromEntries(Object.entries(dto.dimensions ?? {}).map(([key, item]): [string, MatchDimension] => [key, {
    score: Math.round(item.score ?? 0), label: item.label ?? "Нужно проверить",
    sourceFacts: item.source_facts ?? [], profileFacts: item.profile_facts ?? [],
  }]));
  const recommendationReasons = evidence(dto.why_recommended);
  const checks = evidence(dto.checks);
  const legacyReason = dto.analysis.fit_reason?.trim();
  const fitReasons = recommendationReasons.map((item) => item.text);
  if (!fitReasons.length) fitReasons.push(legacyReason || "Оценка собрана из заказа и вашего профиля.");
  return {
    id: dto.id, opportunityId: dto.opportunity_id, title: dto.title, description: dto.description,
    source: dto.source, sourceUrl: dto.source_url, budgetLabel: dto.budget_label, matchScore: Math.round(dto.final_score),
    economics: {
      normalizedLabel: dto.economics?.normalized_label ?? null,
      fxStatus: dto.economics?.fx_status ?? "missing",
      fxRate: dto.economics?.fx_rate ?? null,
      fxRateDate: dto.economics?.fx_rate_date ?? null,
      fxRateSource: dto.economics?.fx_rate_source ?? null,
      requiresCheck: dto.economics?.requires_check ?? false,
    },
    strengthLabel: dto.strength_label || "Стоит проверить", matchConfidence: dto.match_confidence ?? 0,
    dimensions, recommendationReasons, checks, rankingVersion: dto.ranking_version || "legacy",
    reranked: dto.reranked ?? false,
    retrieval: {
      method: dto.retrieval?.method ?? "lexical_fallback",
      score: Math.round(dto.retrieval?.score ?? 0),
      fallbackUsed: dto.retrieval?.fallback_used ?? true,
    },
    fitReasons,
    requiredSkills: dto.analysis.matched_capabilities ?? dto.analysis.required_skills ?? [],
    risks: checks.map((item) => item.text).length ? checks.map((item) => item.text) : (dto.analysis.risks ?? []), portfolioItem: dto.portfolio_item,
    proposal: dto.proposal, status: dto.status, publishedAt: dto.published_at,
    createdAt: dto.created_at, contactedAt: dto.contacted_at, applyMode: dto.apply_mode,
  };
}
