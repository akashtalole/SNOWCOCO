# Risk, Fraud & Regulatory Intelligence Copilot

A working prototype built for the **Risk, Fraud and Regulatory Intelligence Copilot** hackathon
track. Banking/NBFC risk, fraud and compliance teams manage transaction monitoring, AML alerts,
and regulatory reporting largely by hand today. This copilot combines transaction/account data
with policy and regulatory text so a compliance or business user can ask a natural-language
question and get a **governed, explainable, evidence-backed answer** — and turn a detected signal
into an **audit-ready finding/report** in one click.

> ⚠️ **All data in this repository is synthetic.** Customers, accounts, transactions, and even
> the jurisdiction codes and dollar thresholds in the policy documents are fabricated for this
> demo. Nothing here is real regulatory guidance or a real filing.

## What it does (signal → evidence → documented finding)

1. **Signal detection** — a rule-based engine scans synthetic transaction data for five classic
   AML/fraud typologies: structuring/smurfing, rapid layering, dormant-account reactivation,
   high-risk-jurisdiction wires, and ATM card-testing/mule activity. Every signal records *why*
   it fired and *which transactions* are the evidence.
2. **Policy grounding** — a small corpus of synthetic policy documents (AML transaction
   monitoring, KYC risk rating, sanctions screening, CTR, Basel LCR) is indexed with a
   dependency-free TF-IDF retriever, section by section, so every answer can cite the exact
   policy clause behind it (e.g. `AML-TM-2`).
3. **Governed Q&A** — ask questions in plain English ("Why was ACC-1001 flagged?", "What's the
   CTR threshold?", "Show me high-risk jurisdiction activity"). Answers are always composed
   **only** from the retrieved signals/transactions and cited policy sections — never an opaque
   prediction. If `ANTHROPIC_API_KEY` is set, Claude is used only to *phrase* the already-grounded
   facts more naturally; the IDs and citations are never LLM-generated. Without a key, a
   deterministic template composer produces the same grounded answer.
4. **Audit-ready findings** — turn any signal into a `Finding`: a structured record with a
   narrative, the full evidence chronology (transaction table), the regulatory basis (cited
   policy sections with snippets), a recommended action, and a status workflow
   (Open → Under Review → Filed → Closed). Each finding renders as a Markdown report suitable for
   compliance file retention.

## UPI Fraud & Mule Account Network Detection (India)

The hardest, highest-impact fraud problem on India's real-time payments rail isn't a single
suspicious transaction — it's a **mule account network**: a victim is socially engineered (OTP
sharing, a fake collect request, an investment scam) into paying a "mule" account, and the money
is then rapidly relayed through a short chain of further mule accounts before cash-out, so no
single account's own history reveals the whole picture. Every other detector in this track (and
in most transaction-monitoring systems) looks at one account at a time; this module adds a
**graph-based detector** that doesn't.

- **`engine/signals.py: detect_upi_mule_hub`** flags a single account with the classic
  fan-in/fan-out "pass-through" signature: credits from 5+ distinct UPI senders (VPAs) within 48
  hours, followed by 70%+ of that value paid straight back out to 3+ distinct receivers within the
  next 24 hours (**UPI-MULE-2**).
- **`engine/signals.py: detect_upi_mule_ring`** is the standout piece: it takes the individually
  flagged hub accounts and unions them into connected components (via a small in-memory
  union-find) wherever one hub's payout target is *itself* another flagged hub. A multi-hop
  laundering chain — hub → hub → hub — gets recognized as **one network**, not three unrelated
  alerts, which is exactly what a real fraud-ops team needs to act on (freeze the whole ring, not
  one node of it) (**UPI-MULE-3**). The ring signal carries a full node/edge graph
  (`details.ring_nodes` / `details.ring_edges`) that the UI renders as an **interactive network
  diagram** — this flows through `/api/signals`, the Ask tab, and the generated Finding's report
  with zero changes to `main.py`, since the existing generic endpoints already serialize whatever
  a detector puts in `Signal.details`.
- **`detect_upi_new_beneficiary_high_value`** flags a first-ever payment to a new VPA for 5x+ the
  account's average UPI payment size — the OTP-sharing/social-engineering victim pattern
  (**UPI-MULE-4**).
- **`detect_upi_dormant_reactivation`** flags a VPA dormant for 60+ days suddenly receiving a
  burst of credits from 3+ unrelated senders — freshly recruited mules sit unused until a ring is
  ready to route funds through them (**UPI-MULE-5**).

All four are grounded in `policies/upi_fraud_mule_detection.md` (synthetic, modeled loosely on
NPCI/RBI-style UPI risk-control concepts — see that file's own disclaimer), including a reference
to where a production version would hand off to India's real **1930** cybercrime helpline and the
**CFCFRMS** (Citizen Financial Cyber Fraud Reporting and Management System) — this demo files
nothing with any real system, it just documents the real workflow it's modeling.

Demo scenario (`seed_data.py`): `ACC-1009` is a 3-hub mule ring root, fanning out to `ACC-1010`
and `ACC-1011`, each of which independently *also* exhibits the hub signature and further
disperses to external cash-out VPAs — so the demo shows both "3 separate hub alerts" and, from the
ring detector, "these 3 are one network moving ₹7,46,000" side by side. `ACC-1012` is a clean
new-beneficiary victim case; `ACC-1013` is a dormant-VPA reactivation. Amounts in this module are
in INR with Indian digit grouping (`format_inr` in `engine/signals.py`, e.g. `₹7,46,000`), and a
third of the ordinary "noise" accounts get everyday UPI activity too, so the mule ring isn't the
only thing on the rail.

## Architecture

```
tracks/risk_fraud_copilot/
  seed_data.py         synthetic customers/accounts/transactions generator (13 embedded patterns)
  data/                generated CSVs (+ findings_store.json, created at runtime)
  policies/*.md         synthetic, section-numbered policy corpus (AML-TM-*, KYC-RR-*, SANC-*,
                        CTR-*, LCR-*, UPI-MULE-*) — the citable "ground truth" for answers
  engine/
    models.py           CSV loading + DataStore (indexed by account/customer/VPA)
    signals.py           rule-based + graph-based detectors, one per policy clause; also holds
                         format_inr() and the union-find used by the UPI mule-ring detector
    retrieval.py         pure-Python TF-IDF search over policy sections (no ML dependency)
    qa.py                 NL question router: gathers evidence + citations, composes grounded
                          answer, optional LLM phrasing pass
    findings.py           Signal -> audit-ready Finding, JSON persistence, Markdown rendering
                         (including the mule-ring network table)
  main.py                FastAPI app: REST API + serves the frontend
  static/                vanilla HTML/CSS/JS single-page UI (Ask / Signals / UPI Mule Network /
                        Findings tabs) — the UPI tab renders an inline-SVG network diagram
```

No database, no vector DB, no required external API — the whole "signal → evidence → finding"
flow runs locally with two pip dependencies (`fastapi`, `uvicorn`). This keeps the prototype easy
to run and easy to audit end-to-end.

### Embedded synthetic risk patterns

| Account   | Pattern                          | Policy clause |
|-----------|-----------------------------------|---------------|
| ACC-1001  | Structuring / smurfing             | AML-TM-2      |
| ACC-1002  | Rapid layering                     | AML-TM-3      |
| ACC-1003  | Dormant account reactivation       | AML-TM-4      |
| ACC-1004  | High-risk jurisdiction wires        | AML-TM-5, SANC-2/3 |
| ACC-1005  | ATM card-testing / mule indicators | AML-TM-6      |
| ACC-1006  | Round-dollar international wire pattern | AML-TM-10 |
| ACC-1007  | New-account high-value activity    | AML-TM-11     |
| ACC-1008  | Transaction velocity spike          | AML-TM-12     |
| ACC-1009  | UPI mule ring root (hub, fan-in/fan-out)  | UPI-MULE-2, UPI-MULE-3 |
| ACC-1010  | UPI mule ring member A (also its own hub) | UPI-MULE-2, UPI-MULE-3 |
| ACC-1011  | UPI mule ring member B (also its own hub) | UPI-MULE-2, UPI-MULE-3 |
| ACC-1012  | UPI new-beneficiary high-value (OTP/social-engineering victim) | UPI-MULE-4 |
| ACC-1013  | UPI dormant VPA reactivation burst  | UPI-MULE-5    |

Plus 20 accounts of ordinary "noise" activity (a third with everyday UPI history too), so signals
aren't trivially the only data present.

## Running it

From the **repository root**:

```bash
pip install -r requirements.txt
python3 -m tracks.risk_fraud_copilot.seed_data     # generates data/*.csv (only needed once, or to reset)
uvicorn tracks.risk_fraud_copilot.main:app --reload --port 8001
```

Open <http://127.0.0.1:8001/>. Try the suggested questions on the **Ask** tab, browse detected
signals on the **Signals** tab, explore the mule network diagram on the **UPI Mule Network** tab,
or generate/view audit-ready reports on the **Findings & Reports** tab.

Optional: `export ANTHROPIC_API_KEY=sk-...` before starting the server to have Claude phrase
answers in the Ask tab (grounded strictly in the retrieved evidence/citations — see
`engine/qa.py:refine_with_llm`). The app works fully without it.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/signals` | All currently detected signals |
| GET | `/api/accounts/{id}` | Account 360: account, customer, recent transactions, signals |
| GET | `/api/customers/{id}` | Customer's accounts + signals |
| GET | `/api/policies` | Full indexed policy corpus |
| POST | `/api/ask` | `{"question": "..."}` → grounded answer + evidence + citations |
| GET | `/api/findings` | All generated findings |
| POST | `/api/findings/generate` | `{"signal_id": "..."}` → generate (or fetch existing) finding |
| GET | `/api/findings/{id}/report.md` | Audit-ready Markdown report |
| POST | `/api/findings/{id}/status` | Update workflow status |
| POST | `/api/findings/{id}/notes` | `{"note": "...", "author": "Analyst"}` → append an analyst note |
| GET | `/api/signals/export.csv` | All detected signals as CSV (download) |
| GET | `/api/findings/export.csv` | All findings as CSV (download) |

## Judging-criteria mapping

- **Real World Relevance** — models an actual compliance workflow (transaction monitoring →
  SAR-style finding), grounded in policy citations the way a real Financial Crime Analyst would
  need to justify a filing decision. The UPI mule-network module targets India's single largest
  digital-payment fraud pattern directly, with the same evidence-backed, policy-cited rigor as
  every other detector, plus a reference to the real-world 1930/CFCFRMS hand-off point.
- **Technical Execution** — deterministic, testable rule engine; dependency-free retrieval;
  clean separation between evidence-gathering (never hallucinated) and optional LLM phrasing;
  a real running API + UI, not a slide deck. The mule-ring detector is genuinely graph-based
  (union-find clustering over inferred account-to-account edges), not just another per-account
  threshold rule, and its network data flows through the existing generic Signal/Finding API
  unchanged — the interactive diagram required zero backend endpoint changes.
- **Solution Completeness** — covers the full arc the brief asks for: structured transaction data
  + unstructured policy text → NL question → governed, evidence-backed answer → documented,
  exportable finding with a status workflow.

## Recent additions

- **3 new detectors (`engine/signals.py`)**, each grounded in a new policy clause in
  `policies/aml_transaction_monitoring.md`:
  - `AML-TM-10` **Round-Dollar International Wire Pattern** — 3+ `wire_out` transactions to a
    non-US country, each an exact multiple of $500, from the same account within 14 days
    (Medium severity, `round_dollar_wires`). Demo pattern: `ACC-1006`.
  - `AML-TM-11` **New Account High-Value Activity** — any transaction over $8,000 within 30 days
    of the account's `opened_date` (High severity, `new_account_high_value`). Demo pattern:
    `ACC-1007`.
  - `AML-TM-12` **Transaction Velocity Spike** — a day where an account's transaction count is
    at least 3x its trailing 90-day daily average and at least 6 (Medium severity,
    `velocity_spike`). Demo pattern: `ACC-1008`.
- **Audit trail + analyst notes on findings** (`engine/findings.py`) — every `Finding` now carries
  `history` (a `created` entry seeded at generation, plus a `status_change` entry on every status
  update) and `notes` (free-text analyst notes with author/timestamp). `render_markdown` adds
  `## Notes` and `## Status History` sections to the report when either is present.
- **New endpoints (`main.py`)**: `POST /api/findings/{id}/notes` to add a note, and
  `GET /api/signals/export.csv` / `GET /api/findings/export.csv` for CSV export (stdlib `csv`,
  `Content-Disposition: attachment`).
- **UI**: the Signals tab gets a severity-counts bar strip plus a severity filter, free-text
  search, and a "Download CSV" button; the Findings tab gets the same filter/search/CSV
  controls, and the report detail view now shows a status-history timeline and a Notes section
  (list + add-note form) wired to the new endpoint.

## Extending toward production

- Swap the CSV `DataStore` for a real core-banking/data-warehouse connector.
- Swap the TF-IDF retriever for embeddings + a vector store once the policy corpus grows beyond
  what keyword search handles well; the `PolicyIndex` interface (`search`, `get`, `get_many`)
  would not need to change.
- Add authentication/roles so findings and status changes are attributed to a real analyst.
- Persist findings to a real datastore instead of the flat JSON file, and add e-signature/export
  to whatever SAR-filing system the institution uses.

## Snowflake / CoCo CLI solution design

See **[`coco/`](coco/README.md)** for how this track re-platforms onto Snowflake for the hackathon's
technical requirement to "demonstrate use of the Snowflake platform" — semantic views, Cortex Agent
skills, a Streamlit-in-Snowflake app, and an MCP connector, following the event's official
problem-statement slide for this track. It's a design + scaffold, not a deployed system.
