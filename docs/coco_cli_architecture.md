# CoCo CLI Cognitive Agent Architecture — shared reference

This is shared context for every track's `coco/` subfolder (`tracks/<track_name>/coco/`), pulled
from Snowflake's own "Problem Statement Explainer" session for this hackathon (Deepjyoti Dev,
Senior Data Cloud Architect – GCC, Snowflake). It is not published on the public event page — it
comes from the workshop recording — so treat it as the most authoritative technical description of
"CoCo CLI" available to this repo, and re-verify against the actual workshop materials or the
Snowflake Discourse group before building against it for real.

## What CoCo CLI is, in this context

Across all five problem-statement slides, "What CoCo CLI Makes Possible" follows the same
six-step shape:

1. **Generate synthetic data** — referentially consistent, privacy-safe datasets (transactions,
   IoT sensor streams, EHR/claims, ERP/supply-chain records) with no production data required.
2. **Build semantic views** — governed semantic layers over the raw data (and, for text-heavy
   tracks, over policy/clinical/regulatory documents) so natural-language queries resolve against
   business meaning, not raw columns.
3. **Create Cortex Agent skills** — track-specific skills (fraud signal detection, failure
   prediction, evidence retrieval, ontology-domain skills) that the agent invokes as tools.
4. **Orchestrate the end-to-end flow** — signal/question → evidence → a documented,
   audit-ready/explainable output, driven via the CLI.
5. **Scaffold a Streamlit app** — a role-specific dashboard (compliance officer, care
   coordinator, supply-chain analyst, maintenance/OEE command center) with cited, explainable,
   drill-down-capable outputs.
6. **Connect external systems via MCP** — live policy lookups, ticketing systems (Jira,
   ServiceNow), or other external tools, wired in as MCP servers the agent can call.

Each track's `coco/` subfolder numbers its own files `01`–`06` to match this same shape, so the
mapping from slide bullet → concrete artifact is always 1:1 and easy to audit.

## Cognitive Agent Architecture: Loop Harness (2026–)

The session's own architecture diagram for how a CoCo CLI agent actually runs, reproduced here as
text since it's referenced by every track:

```
┌─ HARNESS ──────────────────────────────────────────────────────────────────┐
│                                                                              │
│  ┌─ EPHEMERAL AGENT RUN (session-based, ephemeral) ──┐    ┌─ LOOP ───────┐  │
│  │                                                     │    │              │  │
│  │  User Prompt ─┐                                     │    │ Agentic Tools│  │
│  │  System Prompt ├─► Context RAM ──────────────────────┼───►│ · Schedule   │  │
│  │  Chat History ─┘                                     │    │   Meeting   │  │
│  │                                                     │    │ · Read/Write │  │
│  │                                                     │    │   CRM       │  │
│  │                                                     │    │ · Fetch      │  │
│  │                              ▲                       │    │   Payment   │  │
│  │                              │ Response              │    │   Info      │  │
│  │                    ┌─────────┴─────────┐             │    └──────┬───────┘  │
│  │                    │   Primary Agent    │◄────────────┼───────────┘ Tool Call│
│  │                    │ (e.g. Claude Opus 5)│─── End Loop Guardrails ──► Reply  │
│  │                    └────────────────────┘             │                      │
│  └─────────────────────────────────────────────────────┘                      │
│                              │  ▲              │  ▲              │  ▲          │
│                     Skill.md │  │      RAG/SQL │  │    Async Save│  │          │
│                              ▼  │              ▼  │              ▼  │          │
│  ┌─ DURABLE LONG-TERM MEMORY ─────────────────────────────────────────────┐   │
│  │  Procedural Memory      Semantic Memory        Episodic Memory        │   │
│  │  (Files, Text,          (Vector Store)          (SQL DB + Vector      │   │
│  │   Skill.md)             · Durable structured     Store)               │   │
│  │  · Defined operational    facts                 · Time-series event   │   │
│  │    skills               · Enriched user            logging            │   │
│  │  · Skill instructions     profiles               · Historical chat    │   │
│  │                                                    archive            │   │
│  │           └──────────────────┬─────────────────────────┘             │   │
│  │                    Fact Distillation Loop                            │   │
│  │        (consolidates episodic logs into semantic facts,              │   │
│  │         asynchronously, using cost-optimized summarizer models)      │   │
│  └────────────────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────────┘
```

Key pieces, in plain terms:

- **Ephemeral agent run** — everything inside a single turn (user prompt, system prompt, chat
  history) is assembled into **Context RAM** and handed to the **Primary Agent** (the slide names
  Claude Opus 5 as the example model). The agent can make **tool calls** into the **Loop**'s
  agentic tools (schedule a meeting, read/write CRM, fetch payment info, etc.) and gets a response
  back, bounded by **End Loop Guardrails** before it becomes the final **Reply**. This part is
  session-scoped and thrown away when the session ends.
- **Durable long-term memory** is what survives across sessions, split into three stores the agent
  reads and writes via different mechanisms:
  - **Procedural memory** (files/text, `Skill.md`) — the defined operational skills and their
    instructions. This is where each track's Cortex Agent skill definitions live.
  - **Semantic memory** (vector store) — durable structured facts and enriched profiles, read via
    top-K RAG search for relevance.
  - **Episodic memory** (SQL DB + vector store) — time-series event logs and historical chat
    archive, read via SQL for recency and RAG for relevance, written via async message save.
- **Fact Distillation Loop** — an offline/asynchronous process that consolidates episodic logs
  into semantic facts using cheaper, cost-optimized summarizer models, so the expensive primary
  agent doesn't have to re-derive the same facts from raw history every turn.

### Why this matters for each track's `coco/` scaffold

- The Streamlit app in each track (item 5 of 6) is the **ephemeral agent run** surface: it collects
  the user's question, assembles Context RAM, and calls the Primary Agent.
- The Cortex Agent skills (item 3 of 6) are **procedural memory** — literally the `Skill.md`-style
  instructions this architecture expects.
- The semantic views (item 2 of 6) double as **semantic memory** for the domain (canonical facts
  and metrics the agent retrieves rather than re-deriving).
- The evidence/finding/report tables each track already has (from the FastAPI prototypes) map onto
  **episodic memory** — a durable, queryable log of what was flagged and why, which the Fact
  Distillation Loop would summarize over time in a full CoCo CLI deployment.
- The MCP connections (item 6 of 6) are the **agentic tools** in the Loop.

## Source

Screenshots from the "Problem Statement Explainer (Intro) Session" recording, Deepjyoti Dev
(Senior Data Cloud Architect – GCC, Snowflake), shared directly by the repo owner. Not derived
from the public event page — cross-check against the actual workshop recording/slides or the
Snowflake Discourse group (<https://snowflake.discourse.group/>) before treating any specific
product-name detail (e.g. exact Cortex feature names) as final.
