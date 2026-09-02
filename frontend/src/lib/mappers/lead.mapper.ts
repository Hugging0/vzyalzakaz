import type { Lead, LeadStatus } from "@/types/domain";

type LeadDto = {
  id: number; opportunity_id: string; title: string; description: string; source: string; source_url: string | null;
  budget_label: string; final_score: number; analysis: { fit_reason?: string; required_skills?: string[]; risks?: string[] };
  portfolio_item: string | null; proposal: string | null; status: LeadStatus; published_at: string | null;
  created_at: string; contacted_at: string | null; apply_mode: Lead["applyMode"];
};

export function mapLeadDtoToLead(dto: LeadDto): Lead {
  const reason = dto.analysis.fit_reason?.trim();
  return {
    id: dto.id, opportunityId: dto.opportunity_id, title: dto.title, description: dto.description,
    source: dto.source, sourceUrl: dto.source_url, budgetLabel: dto.budget_label, matchScore: Math.round(dto.final_score),
    fitReasons: reason ? [reason] : ["Совпадение рассчитано по вашему профилю."],
    requiredSkills: dto.analysis.required_skills ?? [], risks: dto.analysis.risks ?? [], portfolioItem: dto.portfolio_item,
    proposal: dto.proposal, status: dto.status, publishedAt: dto.published_at,
    createdAt: dto.created_at, contactedAt: dto.contacted_at, applyMode: dto.apply_mode,
  };
}
