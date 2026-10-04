# SNOWCOCO: Risk, Fraud & Regulatory Intelligence Copilot

Entry for the **Snowflake CoCo CLI Hackathon 2026 (GCC Edition)**, Track 1.

Ask a plain-English question about an account, a risk pattern or a policy and get a cited answer
plus a documented, audit-ready finding. Example: *"Why was ACC-1001 flagged?"* returns 4
sub-threshold cash deposits totalling $36,550 in 5 days, policy AML-TM-2 and the evidence
transaction IDs. All data is synthetic.

**Docs site:** <https://akashtalole.github.io/SNOWCOCO/> (built with MkDocs; see `mkdocs.yml`)

## What is here

| Path | What it is |
|---|---|
| `tracks/risk_fraud_copilot/` | Runnable prototype: FastAPI backend, 12 rule-based and graph-based detectors (including a UPI mule-network detector), policy retrieval, findings and reports, and a single-page UI |
| `tracks/risk_fraud_copilot/coco/` | The Snowflake build: SQL for the semantic view and Cortex Search service, Cortex Agent definition and 3 Skills, MCP server, evaluation set, scheduled task, Streamlit-in-Snowflake app, and the `cortex agent-studio` project files. Start with its `README.md` |
| `docs/` | CoCo CLI architecture notes, screenshots of the Snowflake app, and judge access instructions |

## Run the prototype

```bash
pip install -r requirements.txt
python3 -m tracks.risk_fraud_copilot.seed_data      # generates the synthetic CSVs
uvicorn tracks.risk_fraud_copilot.main:app --port 8001
```

Open <http://127.0.0.1:8001/>. No database or external API is needed.

## The Snowflake build

Objects in the `RISK_FRAUD_COPILOT.CORE` schema of the pilot account:

- `RISK_FRAUD_SEMANTIC_VIEW`: governed metrics (for example `sub_threshold_cash_total`)
- `POLICY_SEARCH_SERVICE`: Cortex Search over 31 policy sections
- `RISK_FRAUD_REGULATORY_COPILOT`: Cortex Agent with 3 Skills and an MCP server
- `DETECT_AND_FILE_STRUCTURING_TASK`: scheduled task that files findings without duplicates
- `RISK_FRAUD_STREAMLIT_APP` and a read-only `..._JUDGE` copy (see `docs/judge_access.md`)

The semantic view and agent were deployed through `cortex agent-studio`
(`sv-read` / `sv-write` / `sv-deploy`, `agent-read` / `agent-write` / `agent-deploy`). Commands,
real outputs and the bugs found along the way are in `tracks/risk_fraud_copilot/coco/README.md`.

## Status

- The UPI mule-ring detector runs in the prototype. Porting it to Snowflake is next.
- Cortex Agent Evaluations ran on 3 questions: tool selection scored 1.0, 0.0, 1.0. Answer-correctness
  scoring did not resolve ground truth on the pilot account.
- No external MCP connector (Slack or a case system) is connected yet; it needs a credential.
- Time saved for analysts has not been measured.

## Build the docs locally

```bash
pip install -r requirements-docs.txt
mkdocs serve
```

## License

See `LICENSE`.
