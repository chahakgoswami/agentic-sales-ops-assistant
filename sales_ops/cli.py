"""CLI entry point for the Agentic Sales Ops Assistant."""
import argparse
import sys
from sales_ops.data.store import LeadStore
from sales_ops.agents.enrichment import LeadEnrichmentAgent


def cmd_list_leads(store: LeadStore, args: argparse.Namespace) -> None:
    leads = store.get_all()
    if not leads:
        print("No leads found.")
        return
    print(f"{'ID':<36}  {'Name':<22}  {'Company':<22}  {'Status':<20}")
    print("-" * 106)
    for lead in leads:
        name = f"{lead.first_name} {lead.last_name}"
        print(f"{lead.id:<36}  {name:<22}  {lead.company:<22}  {lead.status.value:<20}")


def cmd_enrich(store: LeadStore, args: argparse.Namespace) -> None:
    agent = LeadEnrichmentAgent(store)
    if args.lead_id:
        lead = store.get(args.lead_id)
        if not lead:
            print(f"Error: lead '{args.lead_id}' not found.")
            sys.exit(1)
        agent.enrich_lead(lead)
    else:
        agent.run()


def cmd_show_lead(store: LeadStore, args: argparse.Namespace) -> None:
    lead = store.get(args.lead_id)
    if not lead:
        print(f"Error: lead '{args.lead_id}' not found.")
        sys.exit(1)
    data = lead.to_dict()
    for key, value in data.items():
        print(f"  {key:<25}: {value}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sales-ops",
        description="Agentic Sales Ops Assistant",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # leads sub-command
    leads_parser = subparsers.add_parser("leads", help="List all leads")
    leads_parser.set_defaults(func=cmd_list_leads)

    # enrich sub-command
    enrich_parser = subparsers.add_parser("enrich", help="Enrich leads")
    enrich_parser.add_argument(
        "--lead-id", default=None, help="Enrich a specific lead by ID (default: all NEW leads)"
    )
    enrich_parser.set_defaults(func=cmd_enrich)

    # show sub-command
    show_parser = subparsers.add_parser("show", help="Show full details for a lead")
    show_parser.add_argument("lead_id", help="Lead ID")
    show_parser.set_defaults(func=cmd_show_lead)

    return parser


def main() -> None:
    store = LeadStore(seed=True)
    parser = build_parser()
    args = parser.parse_args()
    args.func(store, args)


if __name__ == "__main__":
    main()
