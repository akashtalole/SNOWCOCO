"""Natural-language question routing and grounded answer composition.

Everything here is retrieval-then-compose: the question is used to gather
evidence (matching signals + evidence transactions) and policy citations from
the deterministic engines, and the answer is built ONLY from that gathered
context. If ANTHROPIC_API_KEY is set, an LLM call is used purely to phrase the
already-gathered facts more naturally (with an explicit instruction not to
introduce anything not in the provided context); otherwise a template-based
composer produces the same grounded answer. Either way, evidence transaction
IDs and policy section IDs returned to the caller are exact, not generated.
"""
import os
import re

from .models import DataStore
from .retrieval import PolicyIndex
from .signals import Signal, run_all_signals
from . import findings as findings_mod

ACCOUNT_RE = re.compile(r"\bACC-\d{4}\b")
CUSTOMER_RE = re.compile(r"\bCUST-\d{4}\b")
SIGNAL_RE = re.compile(r"\bSIG-[A-Z]+-ACC-\d{4}-[A-Za-z0-9]+\b")
FINDING_RE = re.compile(r"\bFIND-\d{4}\b")

TYPE_KEYWORDS = {
    "structuring": ["structuring", "smurfing", "sub-threshold", "cash deposit"],
    "rapid_layering": ["layering", "fan out", "fan-out", "rapid movement", "shell"],
    "dormant_reactivation": ["dormant", "reactivation", "inactive account"],
    "high_risk_jurisdiction": ["high-risk jurisdiction", "high risk jurisdiction", "sanction", "zeta", "quorra"],
    "card_testing_mule": ["card testing", "atm", "mule", "card-testing"],
    "upi_mule_hub": ["upi", "mule hub", "mule account", "fan-in", "pass-through", "pass through"],
    "upi_mule_ring": ["mule ring", "mule network", "upi network", "ring", "laundering network"],
    "upi_new_beneficiary_high_value": ["new beneficiary", "otp fraud", "social engineering", "upi scam"],
    "upi_dormant_reactivation": ["dormant vpa", "vpa reactivation", "upi dormant"],
}

GENERATE_KEYWORDS = ["generate", "draft", "file a sar", "create a finding", "create a report",
                      "write up", "produce a report", "write a report"]
EXPLAIN_KEYWORDS = ["why", "explain", "flagged", "suspicious about", "what happened"]
LIST_KEYWORDS = ["list", "show", "all signals", "alerts", "what signals", "any signals",
                  "open signals", "current signals"]
POLICY_KEYWORDS = ["threshold", "policy", "requirement", "rule", "definition", "deadline",
                    "lcr", "hqla", "ctr", "basel", "kyc", "edd", "sanction", "filing"]


def _entity_signals(signals: list[Signal], account_ids: list[str], customer_ids: list[str]) -> list[Signal]:
    if account_ids:
        return [s for s in signals if s.account_id in account_ids]
    if customer_ids:
        return [s for s in signals if s.customer_id in customer_ids]
    return []


def _type_matched_signals(signals: list[Signal], ql: str) -> list[Signal]:
    out = []
    for sig_type, kws in TYPE_KEYWORDS.items():
        if any(kw in ql for kw in kws):
            out.extend([s for s in signals if s.signal_type == sig_type])
    return out


def _dedupe(signals: list[Signal]) -> list[Signal]:
    seen, out = set(), []
    for s in signals:
        if s.signal_id not in seen:
            seen.add(s.signal_id)
            out.append(s)
    return out


def _signal_block(s: Signal, store: DataStore) -> dict:
    customer = store.customers.get(s.customer_id)
    return {
        "signal_id": s.signal_id, "signal_type": s.signal_type, "severity": s.severity,
        "account_id": s.account_id, "customer_id": s.customer_id,
        "customer_name": customer.name if customer else s.customer_id,
        "summary": s.summary, "citations": s.citations, "evidence_txn_ids": s.evidence_txn_ids,
        "details": s.details,
    }


def _citation_block(policy_index: PolicyIndex, section_ids: list[str]) -> list[dict]:
    out = []
    for sec in policy_index.get_many(section_ids):
        out.append({
            "section_id": sec.section_id, "title": sec.title, "doc_name": sec.doc_name,
            "snippet": sec.text.strip().split("\n")[0][:300],
        })
    return out


def answer_question(question: str, store: DataStore, policy_index: PolicyIndex) -> dict:
    q = question.strip()
    ql = q.lower()
    signals = run_all_signals(store)

    account_ids = ACCOUNT_RE.findall(q)
    customer_ids = CUSTOMER_RE.findall(q)
    finding_ids = FINDING_RE.findall(q)

    entity_signals = _entity_signals(signals, account_ids, customer_ids)
    keyword_signals = _type_matched_signals(signals, ql)

    # --- Intent: generate a finding/report for an entity or matched signals ---
    if any(k in ql for k in GENERATE_KEYWORDS):
        target_signals = _dedupe(entity_signals or keyword_signals)
        if not target_signals:
            return _no_match_answer(q, policy_index, ql)
        generated = [findings_mod.generate_finding(s, store, policy_index) for s in target_signals]
        text = _compose_generate_text(generated)
        return {
            "question": q, "intent": "generate_finding", "answer": text,
            "signals": [_signal_block(s, store) for s in target_signals],
            "findings": [{"finding_id": f["finding_id"], "signal_id": f["signal_id"],
                          "status": f["status"]} for f in generated],
            "citations": _citation_block(policy_index, sorted({c for s in target_signals for c in s.citations})),
            "mode": _mode(),
        }

    # --- Intent: explain why an entity was flagged ---
    if entity_signals and (any(k in ql for k in EXPLAIN_KEYWORDS) or account_ids or customer_ids):
        text = _compose_explain_text(entity_signals, store)
        citation_ids = sorted({c for s in entity_signals for c in s.citations})
        return {
            "question": q, "intent": "explain_signals", "answer": text,
            "signals": [_signal_block(s, store) for s in entity_signals],
            "findings": [],
            "citations": _citation_block(policy_index, citation_ids),
            "mode": _mode(),
        }

    # --- Intent: list signals (optionally filtered by type keywords) ---
    if any(k in ql for k in LIST_KEYWORDS):
        target = _dedupe(keyword_signals) if keyword_signals else signals
        text = _compose_list_text(target, store)
        citation_ids = sorted({c for s in target for c in s.citations})
        return {
            "question": q, "intent": "list_signals", "answer": text,
            "signals": [_signal_block(s, store) for s in target],
            "findings": [],
            "citations": _citation_block(policy_index, citation_ids),
            "mode": _mode(),
        }

    # --- Intent: policy / threshold lookup ---
    if any(k in ql for k in POLICY_KEYWORDS) or not (entity_signals or keyword_signals):
        hits = policy_index.search(q, top_k=3)
        if hits:
            text = _compose_policy_text(hits)
            return {
                "question": q, "intent": "policy_lookup", "answer": text,
                "signals": [_signal_block(s, store) for s in keyword_signals],
                "findings": [],
                "citations": [{
                    "section_id": sec.section_id, "title": sec.title, "doc_name": sec.doc_name,
                    "snippet": sec.text.strip()[:400],
                } for _, sec in hits],
                "mode": _mode(),
            }

    # --- Fallback: combine any keyword-matched signals + best-effort retrieval ---
    return _no_match_answer(q, policy_index, ql)


def _no_match_answer(q: str, policy_index: PolicyIndex, ql: str) -> dict:
    hits = policy_index.search(q, top_k=3)
    if hits:
        text = ("I didn't find a specific account, customer, or signal referenced in your "
                "question, but here is the most relevant policy guidance:\n\n" +
                _compose_policy_text(hits))
        citations = [{
            "section_id": sec.section_id, "title": sec.title, "doc_name": sec.doc_name,
            "snippet": sec.text.strip()[:400],
        } for _, sec in hits]
    else:
        text = ("I couldn't find matching signals, findings, or policy guidance for that "
                "question. Try referencing an account (ACC-xxxx), customer (CUST-xxxx), or "
                "a topic like structuring, layering, dormant reactivation, high-risk "
                "jurisdiction, card testing, UPI mule hub, mule ring, CTR, LCR, or KYC.")
        citations = []
    return {"question": q, "intent": "no_match", "answer": text, "signals": [], "findings": [],
            "citations": citations, "mode": _mode()}


def _compose_explain_text(sigs: list[Signal], store: DataStore) -> str:
    lines = []
    for s in sigs:
        customer = store.customers.get(s.customer_id)
        cname = customer.name if customer else s.customer_id
        lines.append(f"**{s.signal_type.replace('_', ' ').title()}** ({s.severity} severity) — "
                      f"account {s.account_id}, customer {cname} ({s.customer_id}): {s.summary}. "
                      f"Evidence: {', '.join(s.evidence_txn_ids)}. Policy basis: "
                      f"{', '.join(s.citations)}.")
    if not lines:
        return "No signals were detected for that account/customer."
    return "\n\n".join(lines)


def _compose_list_text(sigs: list[Signal], store: DataStore) -> str:
    if not sigs:
        return "No signals currently match that criteria."
    by_sev = {"High": [], "Medium": [], "Low": []}
    for s in sigs:
        by_sev.setdefault(s.severity, []).append(s)
    parts = [f"Found {len(sigs)} signal(s)."]
    for sev in ["High", "Medium", "Low"]:
        for s in by_sev.get(sev, []):
            parts.append(f"- [{sev}] {s.signal_type.replace('_', ' ')} on {s.account_id} "
                         f"({s.customer_id}): {s.summary} — cites {', '.join(s.citations)}")
    return "\n".join(parts)


def _compose_policy_text(hits) -> str:
    parts = []
    for score, sec in hits:
        parts.append(f"**{sec.section_id} — {sec.title}**\n{sec.text.strip()}")
    return "\n\n---\n\n".join(parts)


def _compose_generate_text(generated: list[dict]) -> str:
    parts = [f"Generated {len(generated)} finding(s):"]
    for f in generated:
        parts.append(f"- {f['finding_id']} ({f['signal_type'].replace('_', ' ')}, {f['severity']} "
                      f"severity) for account {f['account_id']}, customer {f['customer_name']} "
                      f"— status: {f['status']}.")
    return "\n".join(parts)


def _mode() -> str:
    return "llm" if os.environ.get("ANTHROPIC_API_KEY") else "template"


def refine_with_llm(raw_answer: dict) -> str | None:
    """Optional: rephrase the already-grounded answer via Claude. Returns None on any
    failure or if no API key is configured, so callers can silently fall back."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        client = anthropic.Anthropic(api_key=api_key)
        context = (
            f"Question: {raw_answer['question']}\n\n"
            f"Grounded facts (signals): {raw_answer['signals']}\n\n"
            f"Grounded facts (citations): {raw_answer['citations']}\n\n"
            f"Draft answer: {raw_answer['answer']}"
        )
        msg = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=500,
            system=(
                "You are a risk & compliance analyst assistant. Rephrase the draft answer to be "
                "clear and professional for a compliance user. Use ONLY the facts, signals, and "
                "citations given in the context — do not invent transactions, amounts, accounts, "
                "or policy sections that are not present in the context. Keep policy section IDs "
                "(like AML-TM-2) and transaction IDs (like TXN-000123) exactly as given, since the "
                "user will cross-reference them."
            ),
            messages=[{"role": "user", "content": context}],
        )
        return "".join(b.text for b in msg.content if hasattr(b, "text"))
    except Exception:
        return None
