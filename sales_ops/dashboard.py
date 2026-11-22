"""Rich-based CLI dashboard for the Agentic Sales Ops Assistant."""
from __future__ import annotations

import json
import os
import sys
import time
from typing import List, Optional

from rich import box
from rich.columns import Columns
from rich.console import Console
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from sales_ops.agents.reply_tracker import ReplyClassification, ReplyResult
from sales_ops.crm.connector import CRMContact, CRMDeal, DealStage, MockCRMConnector
from sales_ops.data.models import Lead, LeadStatus
from sales_ops.data.store import LeadStore
from sales_ops.orchestrator import OrchestratorConfig, PipelineRunResult


# ---------------------------------------------------------------------------
# Theme / palette
# ---------------------------------------------------------------------------

_THEME = Theme(
    {
        "header": "bold white on dark_blue",
        "status.new": "dim white",
        "status.enriched": "cyan",
        "status.outreach_drafted": "blue",
        "status.contacted": "yellow",
        "status.replied_interested": "bold green",
        "status.replied_not_interested": "bold red",
        "status.no_reply": "dim yellow",
        "status.closed_won": "bold bright_green",
        "status.closed_lost": "bold bright_red",
        "section.title": "bold cyan",
        "money": "bold green",
        "dim_text": "dim white",
        "highlight": "bold yellow",
    }
)

_STATUS_STYLES = {
    LeadStatus.NEW: "status.new",
    LeadStatus.ENRICHED: "status.enriched",
    LeadStatus.OUTREACH_DRAFTED: "status.outreach_drafted",
    LeadStatus.CONTACTED: "status.contacted",
    LeadStatus.REPLIED_INTERESTED: "status.replied_interested",
    LeadStatus.REPLIED_NOT_INTERESTED: "status.replied_not_interested",
    LeadStatus.NO_REPLY: "status.no_reply",
    LeadStatus.CLOSED_WON: "status.closed_won",
    LeadStatus.CLOSED_LOST: "status.closed_lost",
}

_REPLY_STYLES = {
    ReplyClassification.INTERESTED: "bold green",
    ReplyClassification.NOT_INTERESTED: "bold red",
    ReplyClassification.NO_REPLY: "dim yellow",
}

_DEAL_STAGE_STYLES = {
    DealStage.PROSPECTING: "dim white",
    DealStage.QUALIFICATION: "cyan",
    DealStage.PROPOSAL: "blue",
    DealStage.NEGOTIATION: "yellow",
    DealStage.CLOSED_WON: "bold green",
    DealStage.CLOSED_LOST: "bold red",
}


# ---------------------------------------------------------------------------
# Individual section builders
# ---------------------------------------------------------------------------


def build_lead_status_table(leads: List[Lead]) -> Table:
    """Render a table of all leads with their current status."""
    table = Table(
        title="Lead Status",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Name", style="bold", min_width=20)
    table.add_column("Company", min_width=18)
    table.add_column("Title", min_width=20)
    table.add_column("Status", min_width=22)
    table.add_column("Industry", min_width=24)
    table.add_column("Company Size", min_width=12, justify="center")

    for lead in leads:
        style = _STATUS_STYLES.get(lead.status, "")
        table.add_row(
            f"{lead.first_name} {lead.last_name}",
            lead.company,
            lead.title,
            Text(lead.status.value.replace("_", " ").title(), style=style),
            lead.industry or "—",
            lead.company_size or "—",
        )
    return table


def build_outreach_preview_table(leads: List[Lead]) -> Table:
    """Render a table previewing outreach drafts."""
    table = Table(
        title="Outreach Draft Previews",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Name", style="bold", min_width=20)
    table.add_column("Company", min_width=18)
    table.add_column("Subject", min_width=40)
    table.add_column("Body Preview", min_width=50)

    drafted = [
        l for l in leads
        if l.outreach_subject and l.outreach_body
    ]
    for lead in drafted:
        subject = lead.outreach_subject or ""
        body_preview = (lead.outreach_body or "").replace("\n", " ")[:80] + "..."
        table.add_row(
            f"{lead.first_name} {lead.last_name}",
            lead.company,
            subject,
            Text(body_preview, style="dim_text"),
        )
    if not drafted:
        table.add_row(
            Text("No drafts available yet.", style="dim_text"), "", "", ""
        )
    return table


def build_crm_sync_table(crm: MockCRMConnector, store: LeadStore) -> Table:
    """Render a table showing CRM sync state: contacts and their deals."""
    table = Table(
        title=f"CRM Sync State  ({crm.contact_count()} contacts, {crm.deal_count()} deals)",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Contact", style="bold", min_width=22)
    table.add_column("Company", min_width=18)
    table.add_column("CRM Status", min_width=22)
    table.add_column("Deal Stage", min_width=16)
    table.add_column("Amount", min_width=12, justify="right")
    table.add_column("Probability", min_width=12, justify="center")

    contacts = crm.list_contacts()
    if not contacts:
        table.add_row(
            Text("No CRM contacts synced yet.", style="dim_text"),
            "", "", "", "", "",
        )
        return table

    for contact in contacts:
        deal = crm.get_deal_for_contact(contact.id)
        lead_status_text = contact.lead_status.replace("_", " ").title()
        # Derive rich style from lead_status string
        try:
            ls_enum = LeadStatus(contact.lead_status)
            status_style = _STATUS_STYLES.get(ls_enum, "")
        except ValueError:
            status_style = ""

        if deal:
            stage_style = _DEAL_STAGE_STYLES.get(deal.stage, "")
            stage_text = Text(deal.stage.value.replace("_", " ").title(), style=stage_style)
            amount_text = Text(f"${deal.amount:,.0f}", style="money")
            prob_text = Text(f"{deal.probability * 100:.0f}%", style="highlight")
        else:
            stage_text = Text("—", style="dim_text")
            amount_text = Text("—")
            prob_text = Text("—")

        table.add_row(
            f"{contact.first_name} {contact.last_name}",
            contact.company,
            Text(lead_status_text, style=status_style),
            stage_text,
            amount_text,
            prob_text,
        )
    return table


def build_reply_classification_table(
    reply_results: List[ReplyResult],
    no_reply_results: List[ReplyResult],
) -> Table:
    """Render a table of reply classification results."""
    all_results = reply_results + no_reply_results
    table = Table(
        title=f"Reply Classifications  ({len(all_results)} total)",
        box=box.ROUNDED,
        show_header=True,
        header_style="bold cyan",
        expand=True,
    )
    table.add_column("Email", min_width=28)
    table.add_column("Classification", min_width=20)
    table.add_column("New Status", min_width=22)
    table.add_column("Reply Preview", min_width=50)

    if not all_results:
        table.add_row(
            Text("No reply events processed.", style="dim_text"), "", "", ""
        )
        return table

    for r in all_results:
        cls_style = _REPLY_STYLES.get(r.classification, "")
        status_style = _STATUS_STYLES.get(r.new_lead_status, "")
        body_preview = r.reply_body[:70] + "..." if len(r.reply_body) > 70 else r.reply_body or "(none)"
        table.add_row(
            r.lead_email,
            Text(r.classification.value.replace("_", " ").title(), style=cls_style),
            Text(r.new_lead_status.value.replace("_", " ").title(), style=status_style),
            Text(body_preview, style="dim_text"),
        )
    return table


def build_forecast_panel(forecast_path: str) -> Panel:
    """Render a summary panel from the saved forecast JSON."""
    if not os.path.exists(forecast_path):
        return Panel(
            Text("No forecast file found. Run the pipeline first.", style="dim_text"),
            title="[bold cyan]Forecast Summary[/bold cyan]",
            box=box.ROUNDED,
        )

    with open(forecast_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    generated_at = data.get("generated_at", "unknown")
    total = data.get("total_pipeline", 0.0)
    weighted = data.get("weighted_pipeline", 0.0)
    expected = data.get("expected_revenue", 0.0)
    closed_lost = data.get("closed_lost_value", 0.0)
    deals_by_stage: dict = data.get("deals_by_stage", {})
    weighted_by_stage: dict = data.get("weighted_by_stage", {})
    row_count = len(data.get("rows", []))

    # Build the summary table
    summary = Table.grid(padding=(0, 2))
    summary.add_column(justify="right", style="bold")
    summary.add_column()
    summary.add_row("Generated At", generated_at)
    summary.add_row("Total Deals", str(row_count))
    summary.add_row("Total Pipeline", Text(f"${total:,.2f}", style="money"))
    summary.add_row("Weighted Pipeline", Text(f"${weighted:,.2f}", style="highlight"))
    summary.add_row("Expected Revenue (Closed Won)", Text(f"${expected:,.2f}", style="bold green"))
    summary.add_row("Closed Lost Value", Text(f"${closed_lost:,.2f}", style="bold red"))

    # Stage breakdown table
    stage_table = Table(
        box=box.SIMPLE,
        show_header=True,
        header_style="bold",
        padding=(0, 1),
    )
    stage_table.add_column("Stage")
    stage_table.add_column("Deals", justify="right")
    stage_table.add_column("Weighted Value", justify="right")

    for stage_name, count in sorted(deals_by_stage.items()):
        try:
            stage_enum = DealStage(stage_name)
            stage_style = _DEAL_STAGE_STYLES.get(stage_enum, "")
        except ValueError:
            stage_style = ""
        wv = weighted_by_stage.get(stage_name, 0.0)
        stage_table.add_row(
            Text(stage_name.replace("_", " ").title(), style=stage_style),
            str(count),
            Text(f"${wv:,.2f}", style="money"),
        )

    content = Columns([summary, stage_table], equal=False, expand=True)
    return Panel(
        content,
        title="[bold cyan]Forecast Summary[/bold cyan]",
        box=box.ROUNDED,
    )


def build_pipeline_summary_panel(results: List[PipelineRunResult]) -> Panel:
    """Render a compact pipeline run summary panel."""
    if not results:
        return Panel(
            Text("No pipeline runs completed yet.", style="dim_text"),
            title="[bold cyan]Pipeline Run Summary[/bold cyan]",
            box=box.ROUNDED,
        )

    table = Table(box=box.SIMPLE, show_header=True, header_style="bold", expand=True)
    table.add_column("Loop", justify="center", min_width=6)
    table.add_column("Enriched", justify="right")
    table.add_column("Drafted", justify="right")
    table.add_column("CRM Synced", justify="right")
    table.add_column("Replies", justify="right")
    table.add_column("No-Reply", justify="right")
    table.add_column("Forecast Saved", justify="center")
    table.add_column("Duration (s)", justify="right")
    table.add_column("Errors", justify="right")

    for r in results:
        s = r.summary()
        forecast_icon = Text("✓", style="bold green") if s["forecast_saved"] else Text("✗", style="bold red")
        err_count = len(s["errors"])
        err_text = Text(str(err_count), style="bold red" if err_count else "dim_text")
        table.add_row(
            str(s["loop_index"]),
            str(s["enriched"]),
            str(s["drafted"]),
            str(s["crm_synced"]),
            str(s["replies"]),
            str(s["no_replies"]),
            forecast_icon,
            f"{s['duration_seconds']:.3f}",
            err_text,
        )

    return Panel(
        table,
        title="[bold cyan]Pipeline Run Summary[/bold cyan]",
        box=box.ROUNDED,
    )


# ---------------------------------------------------------------------------
# Main dashboard renderer
# ---------------------------------------------------------------------------


def render_dashboard(
    console: Console,
    leads: List[Lead],
    crm: MockCRMConnector,
    reply_results: List[ReplyResult],
    no_reply_results: List[ReplyResult],
    pipeline_results: List[PipelineRunResult],
    forecast_path: str = "forecast_report.json",
) -> None:
    """Render the full dashboard to the console (one-shot, non-live)."""
    console.rule("[header] Agentic Sales Ops Assistant — Dashboard [/header]")
    console.print()

    # 1. Lead Status
    console.print(build_lead_status_table(leads))
    console.print()

    # 2. Outreach Draft Previews
    console.print(build_outreach_preview_table(leads))
    console.print()

    # 3. CRM Sync State
    console.print(build_crm_sync_table(crm, LeadStore(seed=False)))
    console.print()

    # 4. Reply Classifications
    console.print(build_reply_classification_table(reply_results, no_reply_results))
    console.print()

    # 5. Forecast Summary
    console.print(build_forecast_panel(forecast_path))
    console.print()

    # 6. Pipeline Run Summary
    console.print(build_pipeline_summary_panel(pipeline_results))
    console.print()

    console.rule("[dim_text]End of Dashboard[/dim_text]")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> None:  # pragma: no cover
    """Run the full pipeline and display the dashboard."""
    import argparse

    from sales_ops.config import settings
    from sales_ops.logging_config import configure_logging
    from sales_ops.orchestrator import Orchestrator, OrchestratorConfig

    parser = argparse.ArgumentParser(
        prog="sales-ops-dashboard",
        description="Run the Agentic Sales Ops pipeline and display the Rich dashboard.",
    )
    parser.add_argument(
        "--auto-confirm", action="store_true",
        default=settings.auto_confirm,
        help="Bypass all HITL confirmation prompts (default: from .env)",
    )
    parser.add_argument(
        "--imap-seed", type=int, default=settings.imap_seed,
        help="RNG seed for mock IMAP replies",
    )
    parser.add_argument(
        "--forecast-path", default=settings.forecast_path,
        help="Path to write forecast JSON",
    )
    parser.add_argument(
        "--loops", type=int, default=settings.max_pipeline_loops,
        help="Number of pipeline loops to run",
    )
    parser.add_argument(
        "--log-level", default="WARNING",
        help="Log level for console output (default: WARNING to keep dashboard clean)",
    )
    parser.add_argument(
        "--no-run", action="store_true",
        help="Skip the pipeline run; only display dashboard from existing data.",
    )

    args = parser.parse_args(argv)

    import logging
    configure_logging(level=getattr(logging, args.log_level.upper(), logging.WARNING))

    console = Console(theme=_THEME)

    cfg = OrchestratorConfig(
        seed_leads=True,
        auto_confirm=args.auto_confirm,
        imap_seed=args.imap_seed,
        forecast_path=args.forecast_path,
        max_pipeline_loops=args.loops,
        loop_delay_seconds=0.0,
    )

    orch = Orchestrator(cfg)

    pipeline_results: List[PipelineRunResult] = []
    if not args.no_run:
        console.print(Panel(
            "[bold]Running the full pipeline — please wait…[/bold]",
            box=box.ROUNDED,
        ))
        pipeline_results = orch.run()

    # Collect reply events from all loops
    all_reply_results: List[ReplyResult] = []
    all_no_reply_results: List[ReplyResult] = []
    for pr in pipeline_results:
        all_reply_results.extend(pr.reply_results)
        all_no_reply_results.extend(pr.no_reply_results)

    console.clear()
    render_dashboard(
        console=console,
        leads=orch.store.get_all(),
        crm=orch.crm,
        reply_results=all_reply_results,
        no_reply_results=all_no_reply_results,
        pipeline_results=pipeline_results,
        forecast_path=cfg.forecast_path,
    )


if __name__ == "__main__":  # pragma: no cover
    main()
