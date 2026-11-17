"""OutreachDraftingAgent: drafts personalized outreach emails via a mocked LLM."""
import random
import time
from typing import Dict, Any, List, Optional
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.data.store import LeadStore


# ---------------------------------------------------------------------------
# Pre-written email draft templates keyed by industry / persona
# ---------------------------------------------------------------------------

_DRAFTS: Dict[str, Dict[str, str]] = {
    "SaaS / Cloud Infrastructure": {
        "subject": "Scaling {company}'s infrastructure without the growing pains",
        "body": (
            "Hi {first_name},\n\n"
            "I came across {company} and was impressed by what you're building in the "
            "cloud-native infrastructure space — the {tech_stack_snippet} stack you're "
            "running is exactly the kind of environment our platform thrives in.\n\n"
            "As {title} at a {company_size}-person company, I imagine keeping reliability "
            "high while the team scales is a constant balancing act. We've helped similar "
            "teams cut incident response time by 40% and reduce infra costs by up to 25%.\n\n"
            "Would you be open to a 20-minute call this week to explore whether there's a fit?\n\n"
            "Best,\n"
            "[Your Name]\n"
            "[Your Title] | [Company]\n"
            "[Phone] | [Website]"
        ),
    },
    "Marketing Technology": {
        "subject": "How {company} could unlock another revenue channel in Q3",
        "body": (
            "Hi {first_name},\n\n"
            "I've been following {company}'s growth — the work you're doing in the "
            "marketing technology space is impressive, especially at the {company_size} "
            "headcount stage.\n\n"
            "As {title}, you're likely focused on attributing revenue across a complex "
            "martech stack ({tech_stack_snippet}). We've worked with similar teams to "
            "surface hidden pipeline and improve MQL-to-SQL conversion by 30%+.\n\n"
            "I'd love to share a quick case study that's directly relevant to {company}. "
            "Would 15 minutes Thursday or Friday work?\n\n"
            "Best,\n"
            "[Your Name]\n"
            "[Your Title] | [Company]"
        ),
    },
    "Artificial Intelligence": {
        "subject": "Helping {company} move AI from prototype to production faster",
        "body": (
            "Hi {first_name},\n\n"
            "Your work at {company} on AI products caught my attention — building "
            "production-grade AI with a lean team ({company_size}) is genuinely hard, "
            "especially when you're running {tech_stack_snippet}.\n\n"
            "We specialize in helping AI-first companies like yours reduce model deployment "
            "cycles by 50% and build robust feedback loops so models keep improving "
            "post-launch.\n\n"
            "Given your role as {title}, I think you'd find our approach pretty refreshing. "
            "Worth a 20-minute conversation?\n\n"
            "Warm regards,\n"
            "[Your Name]\n"
            "[Your Title] | [Company]"
        ),
    },
    "Business Consulting": {
        "subject": "A growth lever most consulting firms overlook — thoughts for {company}",
        "body": (
            "Hi {first_name},\n\n"
            "I know your calendar is packed — so I'll keep this brief.\n\n"
            "{company} is at an interesting inflection point for a consulting firm your "
            "size ({company_size}). The firms that break through to the next tier "
            "consistently do one thing differently: they systematize their client "
            "development process.\n\n"
            "As {title}, that probably falls squarely on your plate. We've helped "
            "boutique consulting firms double their qualified pipeline in under 90 days "
            "without adding headcount.\n\n"
            "Happy to share specifics on a quick call — would next Tuesday work?\n\n"
            "Best,\n"
            "[Your Name]\n"
            "[Your Title] | [Company]"
        ),
    },
    "Data & Analytics": {
        "subject": "Turning {company}'s data investments into measurable revenue",
        "body": (
            "Hi {first_name},\n\n"
            "I noticed {company} has built a sophisticated data stack "
            "({tech_stack_snippet}) — that's a serious investment, and one that should "
            "be paying dividends across the business.\n\n"
            "As {title} at a {company_size}-person organization, I'd imagine the pressure "
            "to show ROI on that infrastructure is real. We help data-driven companies "
            "connect their analytics layer directly to revenue outcomes — not just "
            "dashboards.\n\n"
            "I'd love to show you what that looks like in practice. Do you have 20 "
            "minutes this week?\n\n"
            "Thanks,\n"
            "[Your Name]\n"
            "[Your Title] | [Company]"
        ),
    },
    "default": {
        "subject": "Quick idea for {company}",
        "body": (
            "Hi {first_name},\n\n"
            "I've been researching companies in the {industry} space and {company} "
            "stood out — particularly given your focus and growth trajectory.\n\n"
            "As {title}, I imagine you're always looking for ways to move faster and "
            "convert more of your pipeline. We've helped teams at similar stages do "
            "exactly that.\n\n"
            "Would you have 15–20 minutes this week for a quick call?\n\n"
            "Best,\n"
            "[Your Name]\n"
            "[Your Title] | [Company]"
        ),
    },
}


def _build_tech_stack_snippet(tech_stack: Optional[List[str]]) -> str:
    """Return a readable snippet of up to 3 tech stack items."""
    if not tech_stack:
        return "your current stack"
    sample = tech_stack[:3]
    return ", ".join(sample)


def _mock_llm(prompt: str, industry: str, lead_context: Dict[str, Any]) -> Dict[str, str]:
    """
    Simulated LLM call.  In production this would call OpenAI / Anthropic.
    Here we select a pre-written draft and interpolate lead-specific variables.
    """
    # Simulate LLM latency
    time.sleep(random.uniform(0.05, 0.2))

    template = _DRAFTS.get(industry, _DRAFTS["default"])

    tech_snippet = _build_tech_stack_snippet(lead_context.get("tech_stack"))

    subject = template["subject"].format(
        first_name=lead_context["first_name"],
        company=lead_context["company"],
        title=lead_context["title"],
        industry=lead_context["industry"],
        company_size=lead_context["company_size"] or "growing",
        tech_stack_snippet=tech_snippet,
    )

    body = template["body"].format(
        first_name=lead_context["first_name"],
        company=lead_context["company"],
        title=lead_context["title"],
        industry=lead_context["industry"],
        company_size=lead_context["company_size"] or "growing",
        tech_stack_snippet=tech_snippet,
    )

    return {
        "subject": subject,
        "body": body,
        "model": "mock-llm-v1",
        "industry_template_used": industry if industry in _DRAFTS else "default",
    }


def _build_prompt(lead: Lead) -> str:
    """Build a structured prompt string describing the lead for the LLM."""
    tech = ", ".join(lead.tech_stack) if lead.tech_stack else "N/A"
    return (
        f"Draft a personalized B2B outreach email for the following lead:\n"
        f"  Name       : {lead.first_name} {lead.last_name}\n"
        f"  Title      : {lead.title}\n"
        f"  Company    : {lead.company}\n"
        f"  Industry   : {lead.industry}\n"
        f"  Size       : {lead.company_size}\n"
        f"  Revenue    : {lead.annual_revenue}\n"
        f"  Location   : {lead.hq_location}\n"
        f"  Tech Stack : {tech}\n"
        f"  LinkedIn   : {lead.linkedin_headline}\n\n"
        f"Requirements: concise subject line, 3-paragraph body, professional tone, "
        f"specific to their industry and tech stack."
    )


class OutreachDraftingAgent:
    """Agent that generates personalized outreach email drafts for enriched leads."""

    def __init__(self, store: LeadStore):
        self.store = store
        self.name = "OutreachDraftingAgent"

    def draft_for_lead(self, lead: Lead) -> Lead:
        """
        Generate a subject line and body copy for a single enriched lead.
        Stores the draft on the lead object and persists to the store.
        """
        print(
            f"  [{self.name}] Drafting outreach for: "
            f"{lead.first_name} {lead.last_name} <{lead.email}>"
        )

        if lead.industry is None:
            raise ValueError(
                f"Lead {lead.id} has not been enriched yet — industry is missing. "
                "Run LeadEnrichmentAgent first."
            )

        prompt = _build_prompt(lead)

        lead_context: Dict[str, Any] = {
            "first_name": lead.first_name,
            "last_name": lead.last_name,
            "company": lead.company,
            "title": lead.title,
            "industry": lead.industry,
            "company_size": lead.company_size,
            "tech_stack": lead.tech_stack,
            "annual_revenue": lead.annual_revenue,
            "hq_location": lead.hq_location,
            "linkedin_headline": lead.linkedin_headline,
        }

        llm_response = _mock_llm(prompt, lead.industry, lead_context)

        lead.outreach_subject = llm_response["subject"]
        lead.outreach_body = llm_response["body"]

        # Persist LLM metadata for audit
        lead.enrichment_data["outreach_draft"] = {
            "prompt": prompt,
            "model": llm_response["model"],
            "industry_template_used": llm_response["industry_template_used"],
        }

        lead.status = LeadStatus.OUTREACH_DRAFTED
        self.store.upsert(lead)

        print(
            f"  [{self.name}] ✓ Draft ready — subject: \"{lead.outreach_subject}\""
        )
        return lead

    def run(self) -> List[Lead]:
        """Draft outreach for all ENRICHED leads in the store."""
        enriched_leads = self.store.get_by_status(LeadStatus.ENRICHED)
        print(
            f"[{self.name}] Found {len(enriched_leads)} enriched lead(s) to draft for."
        )
        drafted = []
        for lead in enriched_leads:
            drafted.append(self.draft_for_lead(lead))
        print(
            f"[{self.name}] Drafting complete. {len(drafted)} draft(s) generated."
        )
        return drafted
