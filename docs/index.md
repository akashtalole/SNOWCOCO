# Risk, Fraud & Regulatory Intelligence Copilot

Entry for the **Snowflake CoCo CLI Hackathon 2026 (GCC Edition)**, Track 1.

Ask a plain-English question about an account, a risk pattern or a policy, and get a cited answer
plus a documented, audit-ready finding. All data is synthetic.

!!! example "Example"
    *"Why was ACC-1001 flagged?"* returns **4 sub-threshold cash deposits totalling $36,550 in
    5 days**, policy **AML-TM-2**, and the evidence transaction IDs. One click files the finding with
    a status workflow and an exportable report.

## Where to start

| If you want to... | Read |
|---|---|
| See how the pieces fit | [Architecture](coco_cli_architecture.md) |
| Run the prototype locally | [Prototype](prototype.md) |
| See the Snowflake objects, commands and real outputs | [Snowflake build](snowflake-build.md) |
| See the Snowflake-native app | [App screenshots](streamlit_screenshots.md) |
| Open the app as a reviewer | [Judge access](judge_access.md) |

## What was built

- **Prototype:** FastAPI backend, 12 rule-based and graph-based detectors (including an India-specific UPI mule-network detector), policy retrieval, findings and reports, and a single-page UI. No database or external API needed.
- **On Snowflake:** a governed semantic view, Cortex Search over 31 policy sections, a Cortex Agent with 3 Skills and an MCP server, a Streamlit-in-Snowflake app, a scheduled detection task, Cortex Agent Evaluations and CoWork registration.
- **CoCo CLI:** the semantic view and agent were deployed through `cortex agent-studio` (`sv-read` / `sv-write` / `sv-deploy`, `agent-read` / `agent-write` / `agent-deploy`).

## Run it

```bash
pip install -r requirements.txt
python3 -m tracks.risk_fraud_copilot.seed_data
uvicorn tracks.risk_fraud_copilot.main:app --port 8001
```

## Status

!!! warning "Known limits"
    - The UPI mule-ring detector runs in the prototype. Porting it to Snowflake is next.
    - Cortex Agent Evaluations ran on 3 questions: tool selection scored 1.0, 0.0, 1.0. Answer-correctness scoring did not resolve ground truth on the pilot account.
    - No external MCP connector (Slack or a case system) is connected yet; it needs a credential.
    - Analyst time saved has not been measured.
