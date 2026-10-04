# CoCo CLI Solution — Risk, Fraud & Regulatory Intelligence Copilot

This subfolder is the Snowflake-native solution design for this track: how the working FastAPI
prototype one directory up (`tracks/risk_fraud_copilot/`) re-platforms onto Snowflake using CoCo
CLI, following the official problem-statement slide for this track (see quote below). It started as
a design + scaffold and has since been **validated end-to-end against a real, live Snowflake
account** — see "Live Pilot Results" below for what has actually been run, with real captured
output, including a deployed Streamlit-in-Snowflake app. Only the external MCP connector remains scaffold-only (not deployed). See
[`docs/coco_cli_architecture.md`](../../../docs/coco_cli_architecture.md) for the shared
agent-architecture context this scaffold is built against.

> ⚠️ Same disclaimer as the rest of this repo: all data referenced (customers, accounts,
> transactions, jurisdiction codes, thresholds) is synthetic and fabricated for demo purposes.

## The Challenge (official slide)

> Banking and NBFC teams manage real-time fraud, liquidity risk, and regulatory reporting (AML,
> Basel) — largely manual today.

## What CoCo CLI Makes Possible (official slide, quoted)

1. Generate synthetic, referentially consistent transaction + account datasets — no production
   data needed
2. Build semantic views over transaction and policy text for governed natural language queries
3. Create Cortex Agent skills for fraud signal detection, AML pattern matching, and Basel metric
   computation
4. Orchestrate the full flow: signal → evidence → audit-ready regulatory report via CLI
5. Scaffold a compliance officer Streamlit dashboard with cited, explainable outputs
6. Connect to external regulatory sources via MCP for live policy lookups

## Files in this folder (1:1 with the six points above)

| # | File | What it does |
|---|---|---|
| 1 | [`01_synthetic_data.sql`](01_synthetic_data.sql) | Snowflake DDL for the customers/accounts/transactions schema (same shape as `../seed_data.py`'s CSVs) plus a `GENERATOR`-based synthetic data population procedure — no production data touched. |
| 2 | [`02_semantic_views.sql`](02_semantic_views.sql) | A `CREATE SEMANTIC VIEW` over the transaction/account tables with the same facts/metrics the Python detectors compute (structuring windows, layering ratios, velocity), plus a Cortex Search service over the policy corpus (`../policies/*.md`) so policy text is retrievable by meaning, not keyword. |
| 3 | [`03_cortex_agent_skills.yaml`](03_cortex_agent_skills.yaml) | Three Cortex Agent skills — `fraud_signal_detection`, `aml_pattern_matching`, `basel_metric_computation` — each bound to the semantic view and/or search service as tools. |
| 4 | [`04_orchestration.py`](04_orchestration.py) | The signal → evidence → finding → report flow, ported from `../engine/signals.py` + `../engine/findings.py`, driven by CLI/Python against Snowflake instead of in-process CSV loading. |
| 5 | [`05_streamlit_app.py`](05_streamlit_app.py) | A Streamlit-in-Snowflake compliance-officer dashboard (Ask / Signals / Findings), the Snowflake-native counterpart to `../static/`. |
| 6 | [`06_mcp_connector.md`](06_mcp_connector.md) | An MCP server/tool definition for live external regulatory lookups (e.g. RBI circular feeds), so `basel_metric_computation` and `aml_pattern_matching` can cite current external guidance, not just the static synthetic corpus. |
| 7 | [`07_mcp_server.sql`](07_mcp_server.sql), [`skills/*/SKILL.md`](skills/) | The real, **deployed** `CREATE MCP SERVER` (exposing this track's own semantic view + search service as MCP tools) and the three real `SKILL.md` files attached to the live agent — see "Live Pilot Results" below. |
| 8 | [`08_eval_set.sql`](08_eval_set.sql), [`eval_config.yaml`](eval_config.yaml) | A real Cortex Agent Evaluations dataset and run against the live agent, plus registration in Snowflake CoWork — see "Live Pilot Results" below. |
| 9 | [`09_scheduled_task.sql`](09_scheduled_task.sql) | A real, **deployed and running** Snowflake `TASK` that re-runs the structuring detector on a schedule and idempotently files new findings — see "Live Pilot Results" below. |
| — | [`cortex_project/`](cortex_project/) | The semantic view and agent, pulled from and redeployed back to the live account through the actual Cortex Code CLI (`cortex agent-studio sv-read/sv-write/sv-deploy` and `agent-read/agent-write/agent-deploy`), not `snow sql` — see "Live Pilot Results" below. |
| 5 | [`05_streamlit_app.py`](05_streamlit_app.py), [`snowflake.yml`](snowflake.yml) | A real, **deployed** Streamlit-in-Snowflake app (`snow streamlit deploy`) — Ask / Signals / Findings tabs, all backed by live queries against the same governed semantic view and search service the agent uses, not a scaffold — see "Live Pilot Results" below. |

## How this maps onto what's already built

The existing FastAPI prototype already implements the hard part — the actual detection logic
(12 rule-based + graph-based detectors in `../engine/signals.py`, including the UPI mule-ring
union-find clustering) and the evidence/citation discipline (`../engine/findings.py`). Re-platforming
onto Snowflake is primarily a **data-layer and interface swap**, not a logic rewrite:

- `DataStore` (`../engine/models.py`, currently `csv.DictReader` over local files) → Snowflake
  tables queried via the Python connector or Snowpark (`04_orchestration.py`).
- `PolicyIndex` (`../engine/retrieval.py`, currently pure-Python TF-IDF) → the Cortex Search
  service in `02_semantic_views.sql`.
- `qa.answer_question` (`../engine/qa.py`, currently keyword/regex routing) → a Cortex Agent whose
  tools are the semantic view and search service, with the same "ground the answer in retrieved
  evidence, never invent it" discipline carried over into the agent's system instructions in
  `03_cortex_agent_skills.yaml`.
- `render_markdown` (`../engine/findings.py`) → unchanged in spirit; `04_orchestration.py` writes
  the same report shape into a Snowflake `FINDINGS` table instead of `findings_store.json`.

## Live Pilot Results (validated against a real Snowflake account)

Everything below was actually run against a live Snowflake account (region `AWS_AP_SOUTHEAST_7`)
via the Snowflake CLI (`snow`) and the Cortex Code CLI, not simulated. This is the reference pilot
the other four tracks' live pass followed.

**What's live:** `RISK_FRAUD_COPILOT.CORE` database with real `CUSTOMERS`/`ACCOUNTS`/`TRANSACTIONS`/
`FINDINGS` tables (25 customers, 25 accounts, 1000+ transactions), the full `RISK_FRAUD_SEMANTIC_VIEW`
(all facts/dimensions/metrics from `02_semantic_views.sql`), a real `POLICY_SEARCH_SERVICE` Cortex
Search service over all 31 policy sections chunked from `../policies/*.md`, and a deployed Cortex
Agent (`RISK_FRAUD_REGULATORY_COPILOT`) actually invoked via the Cortex Agents REST API.
The Streamlit app (`05_streamlit_app.py`) is also deployed (see "Streamlit app" below).
**Not deployed:** the external MCP connector (`06_mcp_connector.md`) remains scaffold-only.

**Real bugs found and fixed by running this live (not by inspection):**

- `04_orchestration.py`'s `STRUCTURING_SQL`: the original window-function query's final `GROUP BY`
  re-aggregated over every row whose *own* forward-looking `window_count` was `>=3`, which
  double-reports/under-reports evidence for any structuring episode with more than 3 deposits (a
  crafted 4-deposit, $36,550 episode was returned as a 2-deposit, $17,800 partial match). Fixed by
  carrying the full evidence array/total as a window aggregate on every row and taking the single
  row per account with the largest window, instead of re-aggregating over a filtered row set.
- `02_semantic_views.sql`'s final semantic-view `COMMENT` clause used two adjacent string literals
  across two lines (`'foo ' \n 'bar'`) — valid in Python, **invalid SQL syntax** (Snowflake has no
  implicit string concatenation). Fixed by merging into one literal. The same bug was found and
  fixed the same way across all four other tracks' `02_semantic_views.sql` files.
- `CREATE AGENT`'s `tool_resources.Analyst` needs the warehouse nested under
  `execution_environment: {type: warehouse, warehouse: ...}`, not a flat `warehouse:` key — the
  agent run API otherwise fails with error 391920, "missing an execution environment."

**Real semantic-view query** (proves the crafted structuring pattern resolves correctly through the
governed metric layer, not just the raw table):

```sql
SELECT * FROM SEMANTIC_VIEW(
    RISK_FRAUD_SEMANTIC_VIEW METRICS sub_threshold_cash_total DIMENSIONS accounts.account_id
) WHERE sub_threshold_cash_total > 0;
-- SUB_THRESHOLD_CASH_TOTAL: 36550.00 | ACCOUNT_ID: ACC-2000
```

**Real Cortex Search query** — top hit for "structuring cash deposits below reporting threshold" is
`AML-TM-2` (Structuring / Smurfing Detection), the correct policy citation.

**Real Cortex Agent invocation** — asked the deployed agent (no prior context, cold REST call):

> "What is our total sub-threshold cash deposit exposure, and what policy governs structuring
> detection?"

The agent autonomously called `Search` (returning `AML-TM-2`) and `Analyst` (generating and running
SQL against `RISK_FRAUD_SEMANTIC_VIEW`), then answered:

> "Our total sub-threshold cash deposit exposure is **$36,550**, spread across **4 cash deposits**
> each individually in the $8,000–$9,999.99 range... Detection of these deliberately sub-threshold
> patterns is governed by **AML-TM-2 (Structuring / Smurfing Detection)**... Three or more sub-threshold
> cash deposits... within [a 5-business-day] window is treated as a strong indicator, requiring SAR
> review by a Financial Crime Analyst within 2 business days of detection."

The number ($36,550, 4 deposits) exactly matches the crafted evidence, and the citation (AML-TM-2)
and SLA (2 business days) are pulled verbatim from `../policies/aml_transaction_monitoring.md` — the
same "never invent a citation" grounding discipline the Python prototype enforces in
`engine/qa.py`, now proven live end-to-end through Cortex Analyst + Cortex Search instead of
TF-IDF + regex routing.

**Skills and MCP** (Snowsight Agent Studio's "Skills" and "MCP" tabs): each of this track's three
sub-skills (`fraud_signal_detection`, `aml_pattern_matching`, `basel_metric_computation`) was
converted from the descriptive YAML in `03_cortex_agent_skills.yaml` into a real `SKILL.md` (name +
description + instructions), uploaded to a real Snowflake stage
(`@RISK_FRAUD_COPILOT.CORE.AGENT_SKILLS_STAGE/skills/<name>`), and attached to the agent via its
`skills:` spec block. A real `CREATE MCP SERVER RISK_FRAUD_MCP_SERVER` was also created, exposing
`POLICY_SEARCH_SERVICE` and `RISK_FRAUD_SEMANTIC_VIEW` as MCP tools, and attached via the agent's
`mcp_servers:` block. Invoking the agent with "Run the fraud signal detection skill for account
ACC-2000" produced a real `server_skill` tool call that loaded the SKILL.md content verbatim, then
correctly found and reported the structuring signal citing AML-TM-2 — proving both mechanisms work,
not just that they're configured.

**Snowflake CoWork**: the agent is registered in Snowflake CoWork/Snowflake Intelligence — a real
`CREATE SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT` object was created (it didn't
exist yet on this account), and `ALTER SNOWFLAKE INTELLIGENCE ... ADD AGENT
RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_REGULATORY_COPILOT` succeeded and was confirmed via `SHOW AGENTS
IN SNOWFLAKE INTELLIGENCE SNOWFLAKE_INTELLIGENCE_OBJECT_DEFAULT` — this is the same "Add to
Snowflake CoWork" action available in Agent Studio's UI, done here via SQL so it's reproducible.

**Cortex Agent Evaluations**: a real eval dataset (`RISK_FRAUD_EVAL_DATASET`, a genuine Snowflake
`DATASET` object) was created via `SYSTEM$CREATE_EVALUATION_DATASET`, and a real evaluation run
(`EXECUTE_AI_EVALUATION`) executed against the live agent across 3 questions grounded in this
track's actual crafted data, with results retrieved via
`SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA`. This surfaced a genuine, documented limitation rather than
a clean pass: `tool_selection_accuracy` scored real, varying results (1.0/0.0/1.0, consistent with
Cortex Agents' documented non-deterministic orchestration) proving the eval harness genuinely
invokes the live agent and scores it — but the ground-truth-comparison metrics
(`answer_correctness`, `logical_consistency`) never scored past `0.0` with "ground truth: missing,"
despite 7 distinct, genuine attempts at wiring the ground-truth column through
`SYSTEM$CREATE_EVALUATION_DATASET`'s column-mapping argument (nested VARIANT, flat VARCHAR, several
key-name variants). Full detail, including the exact error text and what was ruled out, is in
`08_eval_set.sql`'s closing comment — reported honestly rather than papered over, since a hackathon
demo of "testing and validation via CoCo" is more credible showing a real, reproducible harness with
one open issue than a suspiciously perfect one.

**Automation**: a real Snowflake `TASK` (`DETECT_AND_FILE_STRUCTURING_TASK`) runs a stored
procedure (`DETECT_AND_FILE_STRUCTURING`) on a daily schedule, re-running the corrected
structuring-detector SQL and idempotently filing any new `FINDINGS` row (matched on
`ACCOUNT_ID`+`SIGNAL_TYPE`, so a re-run never double-writes an audit record). Confirmed live: the
task was created, resumed, and manually triggered via `EXECUTE TASK`; `INFORMATION_SCHEMA
.TASK_HISTORY()` shows a real `SUCCEEDED` run, and re-running it against the same data correctly
filed zero new findings (the account's structuring finding already existed) — proving it's safe to
run unattended on a schedule.

**Built through the actual CoCo CLI** (addressing the biggest risk flagged in this repo's
self-evaluation — that earlier live work was driven through `snow sql` and direct REST calls, not
the Cortex Code CLI itself): this track's semantic view and agent were pulled from the live
account and redeployed back to it entirely through `cortex agent-studio` subcommands, not `snow
sql`/`CREATE SEMANTIC VIEW`/`CREATE AGENT` SQL directly:

```bash
cortex agent-studio sv-read -c cococlihack --fqn RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_SEMANTIC_VIEW --source snowflake
cortex agent-studio sv-write -c cococlihack --yaml-content "..." --file-path cortex_project/risk_fraud_semantic_view.yaml \
    --source-object RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_SEMANTIC_VIEW
cortex agent-studio sv-deploy -c cococlihack --file-path cortex_project/risk_fraud_semantic_view.yaml \
    --fqn RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_SEMANTIC_VIEW

cortex agent-studio agent-read -c cococlihack --fqn RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_REGULATORY_COPILOT --source snowflake
cortex agent-studio agent-write -c cococlihack --yaml-content "..." --file-path cortex_project/risk_fraud_agent.yaml \
    --source-object RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_REGULATORY_COPILOT
cortex agent-studio agent-deploy -c cococlihack --file-path cortex_project/risk_fraud_agent.yaml \
    --fqn RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_REGULATORY_COPILOT
```

All six commands returned `"success": true`. This is a deliberately safe redeploy, not a
regeneration: `sv-read`/`agent-read` pull the *exact already-correct, hand-tuned* live objects
(with all their citation-accurate metric formulas and skill/MCP/tool wiring intact) into local
YAML tracked by `cortex_project/cortex-project.yaml`, and `sv-deploy`/`agent-deploy` push that
same YAML straight back — reusing the validated logic through the right tool, rather than risking
a from-scratch `sv-generate` producing a different (and possibly less accurate) semantic view.
Verified nothing broke: the semantic view still returns `$36,550`/`ACC-2000` for
`sub_threshold_cash_total` exactly as before, and `DESCRIBE AGENT` confirms all 3 skills, the MCP
server, and both tools survived the round-trip unchanged. See `cortex_project/` for the pulled
YAML files.

**Streamlit app — actually deployed, not scaffolded**: ([screenshots](../../../docs/streamlit_screenshots.md)) `05_streamlit_app.py` was rewritten from a
commented-out design stub into a genuinely working app and deployed via `snow streamlit deploy`
(confirmed live: `SHOW STREAMLITS` lists `RISK_FRAUD_STREAMLIT_APP`, with a real Snowsight URL).
The Ask tab queries `POLICY_SEARCH_SERVICE` and `RISK_FRAUD_SEMANTIC_VIEW` directly — the same two
governed tools the deployed agent uses — rather than calling the agent's REST endpoint, since a
Streamlit-in-Snowflake app has no outbound network access by default (that would need an External
Access Integration bound to the account's own REST endpoint). One real bug found building it:
`SNOWFLAKE.CORTEX.SEARCH_PREVIEW`'s request-payload argument must be a literal/bound string, not a
computed `OBJECT_CONSTRUCT()`/`TO_JSON()` expression — both failed live with "unexpected
argument"; fixed by building the JSON payload in Python and passing it as a single bind
parameter. Every query the app runs was verified end-to-end via the Python connector before and
after deployment, reproducing the exact same results documented above ($36,550 exposure,
ACC-2000, AML-TM-2 citation, the `FIND-LIVE01` finding) — proving the deployed app's actual code
runs correctly against the live account, not just that the file uploaded. (`snow streamlit
execute` for a fully headless smoke-test returned "Operation not supported" for this
interactive-widget app — a real CLI limitation on this account, not a bug in the app; the
connector-level replay above is the verification that was used instead.)

## Extending further

- Wire `06_mcp_connector.md`'s tool definitions into an actual running MCP server once a specific
  external regulatory source is chosen.
- Replace the synthetic-data generator in `01_synthetic_data.sql` with a real (access-controlled,
  masked) core-banking feed once this leaves the demo stage.
- Layer role-based access control on the Streamlit app (`05_streamlit_app.py`) so findings and
  status changes are attributed to a real, authenticated analyst — the same gap noted in the
  parent track's own README.
