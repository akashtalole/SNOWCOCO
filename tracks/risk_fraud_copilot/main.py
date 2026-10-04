"""FastAPI backend for the Risk, Fraud & Regulatory Intelligence Copilot demo.

Run: uvicorn tracks.risk_fraud_copilot.main:app --reload --port 8001   (from the repo root)
Then open http://127.0.0.1:8001/
"""
import csv
import io
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .engine import findings as findings_mod
from .engine import qa
from .engine.models import DataStore
from .engine.retrieval import PolicyIndex
from .engine.signals import run_all_signals

APP_DIR = Path(__file__).parent

app = FastAPI(title="Risk, Fraud & Regulatory Intelligence Copilot")

store = DataStore()
policy_index = PolicyIndex()


class AskRequest(BaseModel):
    question: str
    use_llm: bool = True


class GenerateFindingRequest(BaseModel):
    signal_id: str


class StatusRequest(BaseModel):
    status: str


class NoteRequest(BaseModel):
    note: str
    author: str = "Analyst"


def _signal_by_id(signal_id: str):
    for s in run_all_signals(store):
        if s.signal_id == signal_id:
            return s
    return None


@app.get("/api/signals")
def api_signals():
    return [s.to_dict() for s in run_all_signals(store)]


@app.get("/api/signals/export.csv")
def api_signals_export_csv():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["signal_id", "signal_type", "severity", "account_id", "customer_id",
                      "summary", "citations", "evidence_txn_ids"])
    for s in run_all_signals(store):
        writer.writerow([s.signal_id, s.signal_type, s.severity, s.account_id, s.customer_id,
                          s.summary, ";".join(s.citations), ";".join(s.evidence_txn_ids)])
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=\"signals.csv\""},
    )


@app.get("/api/accounts/{account_id}")
def api_account(account_id: str):
    account = store.accounts.get(account_id)
    if not account:
        raise HTTPException(404, f"Account {account_id} not found")
    customer = store.customers.get(account.customer_id)
    txns = store.account_transactions(account_id)
    signals = [s.to_dict() for s in run_all_signals(store) if s.account_id == account_id]
    return {
        "account": account.__dict__,
        "customer": customer.__dict__ if customer else None,
        "transaction_count": len(txns),
        "recent_transactions": [t.__dict__ | {"timestamp": t.timestamp.isoformat()}
                                 for t in txns[-25:]],
        "signals": signals,
    }


@app.get("/api/customers/{customer_id}")
def api_customer(customer_id: str):
    customer = store.customers.get(customer_id)
    if not customer:
        raise HTTPException(404, f"Customer {customer_id} not found")
    accounts = store.customer_accounts(customer_id)
    signals = [s.to_dict() for s in run_all_signals(store) if s.customer_id == customer_id]
    return {
        "customer": customer.__dict__,
        "accounts": [a.__dict__ for a in accounts],
        "signals": signals,
    }


@app.get("/api/policies")
def api_policies():
    return [{"section_id": s.section_id, "title": s.title, "doc_name": s.doc_name,
              "text": s.text} for s in policy_index.sections]


@app.post("/api/ask")
def api_ask(req: AskRequest):
    result = qa.answer_question(req.question, store, policy_index)
    if req.use_llm:
        refined = qa.refine_with_llm(result)
        if refined:
            result["answer"] = refined
            result["mode"] = "llm"
        else:
            result["mode"] = "template"
    else:
        result["mode"] = "template"
    return result


@app.get("/api/findings")
def api_list_findings():
    return findings_mod.list_findings()


@app.get("/api/findings/export.csv")
def api_findings_export_csv():
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["finding_id", "signal_id", "signal_type", "severity", "status",
                      "account_id", "customer_id", "customer_name", "created_at", "narrative"])
    for f in findings_mod.list_findings():
        writer.writerow([f["finding_id"], f["signal_id"], f["signal_type"], f["severity"],
                          f["status"], f["account_id"], f["customer_id"], f["customer_name"],
                          f["created_at"], f["narrative"]])
    return Response(
        content=buf.getvalue(), media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=\"findings.csv\""},
    )


@app.get("/api/findings/{finding_id}")
def api_get_finding(finding_id: str):
    f = findings_mod.get_finding(finding_id)
    if not f:
        raise HTTPException(404, f"Finding {finding_id} not found")
    return f


@app.get("/api/findings/{finding_id}/report.md", response_class=PlainTextResponse)
def api_finding_report(finding_id: str):
    f = findings_mod.get_finding(finding_id)
    if not f:
        raise HTTPException(404, f"Finding {finding_id} not found")
    return findings_mod.render_markdown(f)


@app.post("/api/findings/generate")
def api_generate_finding(req: GenerateFindingRequest):
    signal = _signal_by_id(req.signal_id)
    if not signal:
        raise HTTPException(404, f"Signal {req.signal_id} not found")
    return findings_mod.generate_finding(signal, store, policy_index)


@app.post("/api/findings/{finding_id}/status")
def api_update_status(finding_id: str, req: StatusRequest):
    allowed = {"Open", "Under Review", "Filed", "Closed"}
    if req.status not in allowed:
        raise HTTPException(400, f"status must be one of {sorted(allowed)}")
    f = findings_mod.update_status(finding_id, req.status)
    if not f:
        raise HTTPException(404, f"Finding {finding_id} not found")
    return f


@app.post("/api/findings/{finding_id}/notes")
def api_add_note(finding_id: str, req: NoteRequest):
    f = findings_mod.add_note(finding_id, req.note, req.author)
    if not f:
        raise HTTPException(404, f"Finding {finding_id} not found")
    return f


app.mount("/", StaticFiles(directory=APP_DIR / "static", html=True), name="static")
