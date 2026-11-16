# Agentic Sales Ops Assistant

Agentic Sales Ops Assistant that enriches leads, drafts outreach, syncs CRM, and tracks forecasts.

**Domain:** Agentic AI
**Language:** python
**Demonstrates:** You connect agents to revenue, not just demos.

## 7-day build plan

- [ ] Day 1: Scaffold the project structure with a CLI entry point, mock data layer (in-memory lead store with sample leads), and a LeadEnrichmentAgent that simulates enriching leads with company size, industry, and LinkedIn data via stubbed API calls returning realistic fake payloads.
- [ ] Day 2: Build the OutreachDraftingAgent that takes an enriched lead and uses a templated prompt (calling a mocked LLM function that returns pre-written personalized email drafts) to generate subject lines and body copy, storing drafts alongside each lead in the mock data store.
- [ ] Day 3: Implement the MockCRMConnector simulating a CRM (HubSpot-style) with in-memory contact and deal records, and build the CRMSyncAgent that upserts enriched leads and outreach drafts into the mock CRM with human-in-the-loop confirmation prompts before any write operation.
- [ ] Day 4: Add the ReplyTrackerAgent that polls a simulated email inbox (mock IMAP returning synthetic reply events on a timer), classifies replies as interested/not-interested/no-reply using keyword matching, and updates lead status in both the local store and mock CRM.
- [ ] Day 5: Create the ForecastUpdateAgent that reads deal stages and reply statuses from the mock CRM, applies a weighted pipeline calculation, and produces an updated forecast report stored as JSON, with a human confirmation gate before overwriting the previous forecast.
- [ ] Day 6: Wire all agents into an Orchestrator class with a configurable run-loop that sequences enrichment, drafting, CRM sync, reply tracking, and forecast updates in a single pipeline, add structured logging throughout, and write pytest unit tests covering each agent and the orchestrator flow.
- [ ] Day 7: Add a simple CLI dashboard (using rich) that displays lead statuses, outreach draft previews, CRM sync state, reply classifications, and forecast summary in a formatted live view, then package the project with pyproject.toml, dotenv-based config, and an end-to-end integration test that runs the full pipeline headlessly.

_A comprehensive README with an architecture diagram is generated on Day 7._
