"""Turns a detected Signal into an audit-ready Finding, with a narrative,
the evidence transactions, and cited policy sections — and can render the
whole thing as a Markdown report suitable for compliance file retention.

Findings persist to a flat JSON file (app/data/findings_store.json) so the
demo has a durable "signal -> evidence -> documented finding" trail across
requests without needing a database.
"""
import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

from .models import DataStore
from .retrieval import PolicyIndex
from .signals import Signal, format_inr

STORE_PATH = Path(__file__).parent.parent / "data" / "findings_store.json"

NARRATIVE_TEMPLATES = {
    "structuring": (
        "Between {window_start} and {window_end}, account {account_id} (customer "
        "{customer_name}, {customer_id}) received {count} cash deposits totaling "
        "${total_amount:,.2f}, each individually below the $10,000 Currency Transaction "
        "Report threshold. This pattern is consistent with structuring/smurfing activity "
        "as described in policy section AML-TM-2."
    ),
    "rapid_layering": (
        "Account {account_id} (customer {customer_name}, {customer_id}) received an inbound "
        "credit of ${inflow_amount:,.2f} and subsequently transferred ${outflow_total:,.2f} "
        "({outflow_pct:.0%} of the inflow) to {counterparty_count} distinct counterparties "
        "within 48 hours. This rapid fan-out is consistent with layering activity as "
        "described in policy section AML-TM-3."
    ),
    "dormant_reactivation": (
        "Account {account_id} (customer {customer_name}, {customer_id}) was dormant for "
        "{dormant_days} days before processing ${reactivation_total:,.2f} in activity within "
        "a 72-hour window. Sudden reactivation of a dormant account above the $5,000 "
        "threshold requires Enhanced Due Diligence per policy section AML-TM-4."
    ),
    "high_risk_jurisdiction": (
        "Account {account_id} (customer {customer_name}, {customer_id}) processed wire "
        "activity involving the Designated High-Risk Jurisdiction(s) {jurisdictions}. "
        "Per policy sections AML-TM-5 and SANC-2/SANC-3, this activity requires enhanced "
        "scrutiny and, where the repeated-transaction threshold is met, Compliance Officer "
        "sign-off before further international wires are processed."
    ),
    "card_testing_mule": (
        "Account {account_id} (customer {customer_name}, {customer_id}) recorded {count} ATM "
        "withdrawals totaling ${total_amount:,.2f} across {locations_count} distinct locations "
        "within a short window, consistent with card-testing or money-mule activity as "
        "described in policy section AML-TM-6."
    ),
    "round_dollar_wires": (
        "Account {account_id} (customer {customer_name}, {customer_id}) sent {count} round-dollar "
        "international wires totaling ${total_amount:,.2f} to {countries} within a 14-day window. "
        "This pattern is consistent with the round-dollar international wire indicator described "
        "in policy section AML-TM-10."
    ),
    "new_account_high_value": (
        "Account {account_id} (customer {customer_name}, {customer_id}), opened {opened_date}, "
        "processed {count} transaction(s) totaling ${total_amount:,.2f} above the $8,000 "
        "threshold within 30 days of opening. Per policy section AML-TM-11, this requires prompt "
        "KYC re-verification before further high-value transactions are processed."
    ),
    "velocity_spike": (
        "Account {account_id} (customer {customer_name}, {customer_id}) recorded {day_count} "
        "transactions on {day}, at least 3x its trailing 90-day daily average of "
        "{trailing_avg:.1f} transactions/day. This velocity spike is consistent with policy "
        "section AML-TM-12."
    ),
    "upi_mule_hub": (
        "Account {account_id} (customer {customer_name}, {customer_id}) received "
        "{total_in_inr} from {sender_count} distinct UPI senders within 48 hours, then "
        "transferred {total_out_inr} ({out_pct:.0%}) out to {receiver_count} distinct "
        "receivers within the following 24 hours. This fan-in/fan-out pass-through pattern "
        "is the classic signature of a recruited money-mule account on the UPI rail, as "
        "described in policy section UPI-MULE-2."
    ),
    "upi_mule_ring": (
        "A connected network of {ring_size} UPI Mule Hub accounts ({ring_accounts_str}) was "
        "detected, with account {account_id} acting as the root/recruiting hub. "
        "{total_value_inr} moved through the network before reaching external cash-out "
        "points. Per policy section UPI-MULE-3, multi-hub networks like this must be "
        "investigated and, where possible, frozen together rather than as isolated "
        "single-account alerts."
    ),
    "upi_new_beneficiary_high_value": (
        "Account {account_id} (customer {customer_name}, {customer_id}) made a first-ever "
        "UPI payment of {amount_inr} to beneficiary {new_beneficiary}, {multiple:.1f}x this "
        "account's average UPI payment size of {avg_payment_inr}. This unprecedented "
        "high-value payment to an unfamiliar VPA is characteristic of OTP-sharing or "
        "social-engineering fraud, as described in policy section UPI-MULE-4."
    ),
    "upi_dormant_reactivation": (
        "Account {account_id} (customer {customer_name}, {customer_id}) had no UPI activity "
        "for {dormant_days} days, then received {reactivation_total_inr} from {sender_count} "
        "distinct, unrelated senders within 24 hours. This reactivation-burst pattern is "
        "characteristic of a freshly recruited mule account, as described in policy section "
        "UPI-MULE-5."
    ),
}

RECOMMENDED_ACTION = {
    "structuring": "Escalate to a Financial Crime Analyst for SAR review within 2 business days (AML-TM-2).",
    "rapid_layering": "Open a Tier 2 layering alert; document source and destination of funds for each leg (AML-TM-3).",
    "dormant_reactivation": "Initiate Enhanced Due Diligence and confirm activity matches the customer's stated profile (AML-TM-4).",
    "high_risk_jurisdiction": "Log jurisdiction-risk annotation; obtain Compliance Officer sign-off before further international wires (AML-TM-5, SANC-3).",
    "card_testing_mule": "Refer to Fraud Operations for real-time review of card/ATM activity (AML-TM-6).",
    "round_dollar_wires": "Review underlying business purpose for each wire; escalate as a Tier 1 signal (AML-TM-10).",
    "new_account_high_value": "Perform prompt KYC re-verification before further high-value transactions are processed (AML-TM-11).",
    "velocity_spike": "Review account activity for takeover or bot-driven behavior; contact the customer to confirm activity (AML-TM-12).",
    "upi_mule_hub": "Place an immediate hold on outbound UPI transfers pending investigation; refer to Fraud Operations within 4 hours (UPI-MULE-2).",
    "upi_mule_ring": "Freeze every ring member account the Bank can reach, generate the network diagram for law-enforcement handoff, and refer to Fraud Operations within 2 hours (UPI-MULE-3).",
    "upi_new_beneficiary_high_value": "Contact the customer directly to confirm the payment was authorized before it settles further, rather than freezing the account (UPI-MULE-4).",
    "upi_dormant_reactivation": "Place a temporary hold on further outbound transfers and verify the account holder's identity before releasing funds (UPI-MULE-5).",
}


@dataclass
class Finding:
    finding_id: str
    signal_id: str
    signal_type: str
    severity: str
    account_id: str
    customer_id: str
    customer_name: str
    created_at: str
    narrative: str
    recommended_action: str
    evidence: list[dict] = field(default_factory=list)
    citations: list[dict] = field(default_factory=list)
    status: str = "Open"
    history: list[dict] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    network: dict | None = None  # {nodes, edges} for mule-ring visualization, when applicable

    def to_dict(self):
        return asdict(self)


def _load_all() -> list[dict]:
    if not STORE_PATH.exists():
        return []
    return json.loads(STORE_PATH.read_text())


def _save_all(items: list[dict]):
    STORE_PATH.parent.mkdir(exist_ok=True)
    STORE_PATH.write_text(json.dumps(items, indent=2))


def list_findings() -> list[dict]:
    return _load_all()


def get_finding(finding_id: str) -> dict | None:
    for f in _load_all():
        if f["finding_id"] == finding_id:
            return f
    return None


def find_by_signal_id(signal_id: str) -> dict | None:
    for f in _load_all():
        if f["signal_id"] == signal_id:
            return f
    return None


def update_status(finding_id: str, status: str) -> dict | None:
    items = _load_all()
    for f in items:
        if f["finding_id"] == finding_id:
            old_status = f["status"]
            f["status"] = status
            f.setdefault("history", []).append({
                "event": "status_change",
                "at": datetime.utcnow().isoformat() + "Z",
                "detail": f"{old_status} -> {status}",
            })
            _save_all(items)
            return f
    return None


def add_note(finding_id: str, note: str, author: str = "Analyst") -> dict | None:
    items = _load_all()
    for f in items:
        if f["finding_id"] == finding_id:
            f.setdefault("notes", []).append({
                "note": note,
                "author": author,
                "at": datetime.utcnow().isoformat() + "Z",
            })
            _save_all(items)
            return f
    return None


def _next_finding_id(items: list[dict]) -> str:
    nums = [int(f["finding_id"].split("-")[1]) for f in items if f["finding_id"].startswith("FIND-")]
    n = (max(nums) + 1) if nums else 1
    return f"FIND-{n:04d}"


def generate_finding(signal: Signal, store: DataStore, policy_index: PolicyIndex) -> dict:
    """Idempotent: re-generating for the same signal returns the existing finding."""
    existing = find_by_signal_id(signal.signal_id)
    if existing:
        return existing

    customer = store.customers.get(signal.customer_id)
    customer_name = customer.name if customer else signal.customer_id

    fmt_details = dict(signal.details)
    if "jurisdictions" in fmt_details:
        fmt_details["jurisdictions"] = ", ".join(fmt_details["jurisdictions"])
    if "locations" in fmt_details:
        fmt_details["locations_count"] = len(fmt_details["locations"])
    if "countries" in fmt_details:
        fmt_details["countries"] = ", ".join(fmt_details["countries"])
    if "ring_accounts" in fmt_details:
        fmt_details["ring_accounts_str"] = ", ".join(fmt_details["ring_accounts"])

    network = None
    if "ring_nodes" in fmt_details or "ring_edges" in fmt_details:
        network = {"nodes": fmt_details.pop("ring_nodes", []),
                   "edges": fmt_details.pop("ring_edges", [])}
    fmt_details.pop("sender_vpas", None)
    fmt_details.pop("receiver_vpas", None)
    fmt_details.pop("ring_accounts", None)

    template = NARRATIVE_TEMPLATES.get(signal.signal_type, signal.summary)
    try:
        narrative = template.format(
            account_id=signal.account_id, customer_id=signal.customer_id,
            customer_name=customer_name, **fmt_details,
        )
    except (KeyError, IndexError):
        narrative = signal.summary

    evidence = []
    for txn_id in signal.evidence_txn_ids:
        t = store.txn_by_id.get(txn_id)
        if t:
            evidence.append({
                "txn_id": t.txn_id, "timestamp": t.timestamp.isoformat(),
                "amount": t.amount, "currency": t.currency, "type": t.type,
                "counterparty_name": t.counterparty_name,
                "counterparty_country": t.counterparty_country,
                "channel": t.channel,
            })

    citations = []
    for section in policy_index.get_many(signal.citations):
        snippet = section.text.strip().split("\n")[0]
        citations.append({
            "section_id": section.section_id, "title": section.title,
            "snippet": snippet[:280], "doc_name": section.doc_name,
        })

    items = _load_all()
    created_at = datetime.utcnow().isoformat() + "Z"
    finding = Finding(
        finding_id=_next_finding_id(items),
        signal_id=signal.signal_id,
        signal_type=signal.signal_type,
        severity=signal.severity,
        account_id=signal.account_id,
        customer_id=signal.customer_id,
        customer_name=customer_name,
        created_at=created_at,
        narrative=narrative,
        recommended_action=RECOMMENDED_ACTION.get(signal.signal_type, "Route to Compliance for review."),
        evidence=evidence,
        citations=citations,
        network=network,
        history=[{
            "event": "created",
            "at": created_at,
            "detail": f"Finding generated from signal {signal.signal_id}",
        }],
    ).to_dict()

    items.append(finding)
    _save_all(items)
    return finding


def render_markdown(finding: dict) -> str:
    lines = []
    lines.append(f"# Finding {finding['finding_id']} — {finding['signal_type'].replace('_', ' ').title()}")
    lines.append("")
    lines.append("> **Synthetic demo output.** Generated for illustrative purposes; not a real regulatory filing.")
    lines.append("")
    lines.append(f"- **Status:** {finding['status']}")
    lines.append(f"- **Severity:** {finding['severity']}")
    lines.append(f"- **Subject:** {finding['customer_name']} ({finding['customer_id']}), Account {finding['account_id']}")
    lines.append(f"- **Detected:** {finding['created_at']}")
    lines.append(f"- **Source Signal:** {finding['signal_id']}")
    lines.append("")
    lines.append("## Suspicious Activity Summary")
    lines.append("")
    lines.append(finding["narrative"])
    lines.append("")
    lines.append("## Chronology of Evidence Transactions")
    lines.append("")
    lines.append("| Txn ID | Timestamp | Type | Amount | Counterparty | Country |")
    lines.append("|---|---|---|---|---|---|")
    for e in finding["evidence"]:
        amount_str = format_inr(e["amount"]) if e.get("currency") == "INR" else f"${e['amount']:,.2f}"
        lines.append(f"| {e['txn_id']} | {e['timestamp']} | {e['type']} | {amount_str} | "
                      f"{e['counterparty_name'] or '—'} | {e['counterparty_country'] or '—'} |")
    lines.append("")
    network = finding.get("network")
    if network and network.get("edges"):
        lines.append("## Mule Network Diagram (transfer graph)")
        lines.append("")
        lines.append("| From | To | Amount | Timestamp |")
        lines.append("|---|---|---|---|")
        for e in sorted(network["edges"], key=lambda x: x["at"]):
            lines.append(f"| {e['from']} | {e['to']} | {format_inr(e['amount'])} | {e['at']} |")
        lines.append("")
        role_order = {"hub": 0, "source": 1, "cashout": 2}
        nodes = sorted(network.get("nodes", []), key=lambda n: role_order.get(n["role"], 9))
        lines.append("Nodes: " + ", ".join(f"{n['label']} ({n['role']})" for n in nodes))
        lines.append("")
    lines.append("## Regulatory Basis")
    lines.append("")
    for c in finding["citations"]:
        lines.append(f"- **{c['section_id']}** ({c['doc_name']}) — {c['title']}: {c['snippet']}")
    lines.append("")
    lines.append("## Recommended Action")
    lines.append("")
    lines.append(finding["recommended_action"])
    lines.append("")
    notes = finding.get("notes") or []
    if notes:
        lines.append("## Notes")
        lines.append("")
        for n in notes:
            lines.append(f"- **{n['at']}** ({n['author']}): {n['note']}")
        lines.append("")
    history = finding.get("history") or []
    if len(history) > 1:
        lines.append("## Status History")
        lines.append("")
        for h in history:
            lines.append(f"- **{h['at']}** — {h['event']}: {h['detail']}")
        lines.append("")
    return "\n".join(lines)
