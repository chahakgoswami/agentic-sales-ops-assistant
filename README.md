# Agentic Sales Ops Assistant

Agentic Sales Ops Assistant that enriches leads, drafts outreach, syncs CRM, and tracks forecasts.

**Domain:** Agentic AI  
**Language:** Python 3.10+  
**Demonstrates:** Connecting agents to revenue, not just demos.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Orchestrator                             │
│  OrchestratorConfig → configurable run-loop (N iterations)      │
│                                                                 │
│  ┌───────────────┐  ┌────────────────┐  ┌──────────────────┐   │
│  │LeadEnrichment │→ │OutreachDrafting│→ │   CRMSyncAgent   │   │
│  │    Agent      │  │    Agent       │  │  (HITL confirms) │   │
│  └───────────────┘  └────────────────┘  └──────────────────┘   │
│          │                  │                    │               │
│          ▼                  ▼                    ▼               │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   LeadStore (in-memory)                   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                    │                             │
│  ┌─────────────────┐  ┌────────────▼─────────────────────────┐  │
│  │ReplyTrackerAgent│← │   MockIMAPClient (synthetic replies)  │  │
│  │  + classifier   │  └──────────────────────────────────────┘  │
│  └────────┬────────┘                                            │
│           │                                                      │
│  ┌────────▼──────────┐  ┌──────────────────────────────────┐   │
│  │ForecastUpdateAgent│  │  MockCRMConnector (HubSpot-style) │   │
│  │  weighted pipeline│← │  Contacts + Deals  (in-memory)   │   │
│  │  → forecast.json  │  └──────────────────────────────────┘   │
│  └───────────────────┘                                          │
└─────────────────────────────────────────────────────────────────┘
                │
                ▼
     ┌──────────────────┐
     │  Rich Dashboard  │  (CLI: sales-ops-dashboard)
     │  • Lead statuses │
     │  • Draft previews│
     │  • CRM sync state│
     │  • Reply classes │
     │  • Forecast summ.│
     └──────────────────┘
```

---

## Quick Start

```bash
# 1. Install
pip install -e ".[dev]"

# 2. Configure (optional)
cp .env.example .env
# edit .env as needed

# 3. Run the full pipeline + dashboard
sales-ops-dashboard --auto-confirm

# 4. Or use the step-by-step CLI
sales-ops leads
sales-ops enrich
sales-ops draft
sales-ops show <lead-id>

# 5. Run tests
pytest
```

---

## Project Structure

```
sales_ops/
├── __init__.py
├── cli.py              # argparse CLI entry point
├── config.py           # dotenv-based Settings singleton
├── dashboard.py        # Rich-based CLI dashboard
├── logging_config.py   # Structured logging setup
├── orchestrator.py     # Orchestrator + OrchestratorConfig + PipelineRunResult
├── agents/
│   ├── enrichment.py   # LeadEnrichmentAgent (stubbed Clearbit / LinkedIn APIs)
│   ├── drafting.py     # OutreachDraftingAgent (mocked LLM)
│   ├── crm_sync.py     # CRMSyncAgent (HITL-gated CRM writes)
│   ├── reply_tracker.py# ReplyTrackerAgent + MockIMAPClient
│   └── forecast.py     # ForecastUpdateAgent + weighted pipeline calc
├── crm/
│   └── connector.py    # MockCRMConnector, CRMContact, CRMDeal, DealStage
└── data/
    ├── models.py        # Lead, LeadStatus dataclasses
    └── store.py         # LeadStore + 5 sample leads

tests/
├── test_store.py
├── test_enrichment.py
├── test_drafting.py
├── test_crm_connector.py
├── test_crm_sync.py
├── test_reply_tracker.py
├── test_forecast.py
├── test_orchestrator.py
├── test_logging_config.py
└── test_integration.py  # end-to-end headless integration test
```

---

## Configuration (`.env`)

| Variable | Default | Description |
|---|---|---|
| `SALES_OPS_LOG_LEVEL` | `INFO` | Python logging level |
| `SALES_OPS_FORECAST_PATH` | `forecast_report.json` | Forecast output path |
| `SALES_OPS_AUTO_CONFIRM` | `false` | Bypass HITL prompts |
| `SALES_OPS_IMAP_SEED` | `42` | RNG seed for mock IMAP |
| `SALES_OPS_MAX_PIPELINE_LOOPS` | `1` | Pipeline loop count |
| `SALES_OPS_LOOP_DELAY_SECONDS` | `0.0` | Delay between loops |

---

## 7-Day Build Plan

- [x] Day 1: Scaffold project, mock data layer, LeadEnrichmentAgent
- [x] Day 2: OutreachDraftingAgent with mocked LLM
- [x] Day 3: MockCRMConnector + CRMSyncAgent with HITL
- [x] Day 4: ReplyTrackerAgent + MockIMAPClient
- [x] Day 5: ForecastUpdateAgent + weighted pipeline
- [x] Day 6: Orchestrator, structured logging, pytest suite
- [x] Day 7: Rich CLI dashboard, pyproject.toml, dotenv config, e2e integration test
