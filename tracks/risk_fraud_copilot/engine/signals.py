"""Rule-based risk/fraud signal detection over transaction data.

Each detector implements one clause of app/policies/aml_transaction_monitoring.md
and emits Signal objects carrying: which policy section justifies the flag, and
which transactions are the evidence for it. This is what makes downstream
answers/findings "evidence backed" rather than opaque predictions.
"""
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from itertools import combinations

from .models import DataStore, Transaction

HIGH_RISK_JURISDICTIONS = {"ZX", "QW"}


def format_inr(amount: float) -> str:
    """Format a number using Indian digit grouping, e.g. 311000 -> '₹3,11,000'."""
    n = int(round(amount))
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        return f"{sign}₹{s}"
    last3, rest = s[-3:], s[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return f"{sign}₹{','.join(groups)},{last3}"


class _UnionFind:
    """Minimal union-find for clustering connected Mule Hub accounts into rings."""

    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


@dataclass
class Signal:
    signal_id: str
    signal_type: str
    severity: str  # Low / Medium / High
    account_id: str
    customer_id: str
    summary: str
    citations: list[str]
    evidence_txn_ids: list[str]
    details: dict = field(default_factory=dict)

    def to_dict(self):
        return asdict(self)


def _sig_id(kind: str, account_id: str, seed: str) -> str:
    return f"SIG-{kind}-{account_id}-{seed}"


def detect_structuring(store: DataStore) -> list[Signal]:
    """AML-TM-2: >=3 sub-$10k cash deposits ($8,000-$9,999) within 5 business days."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        deposits = [t for t in txns if t.type == "cash_deposit" and 8000 <= t.amount < 10000]
        deposits.sort(key=lambda t: t.timestamp)
        n = len(deposits)
        i = 0
        while i < n:
            window = [deposits[i]]
            j = i + 1
            while j < n and (deposits[j].timestamp - deposits[i].timestamp) <= timedelta(days=5):
                window.append(deposits[j])
                j += 1
            if len(window) >= 3:
                total = sum(t.amount for t in window)
                customer_id = window[0].customer_id
                out.append(Signal(
                    signal_id=_sig_id("STRUCT", account_id, window[0].txn_id),
                    signal_type="structuring",
                    severity="High",
                    account_id=account_id,
                    customer_id=customer_id,
                    summary=(f"{len(window)} cash deposits totaling ${total:,.2f} "
                             f"(each below the $10,000 CTR threshold) within "
                             f"{(window[-1].timestamp - window[0].timestamp).days + 1} days"),
                    citations=["AML-TM-2"],
                    evidence_txn_ids=[t.txn_id for t in window],
                    details={"total_amount": total, "count": len(window),
                              "window_start": window[0].timestamp.isoformat(),
                              "window_end": window[-1].timestamp.isoformat()},
                ))
                i = j
            else:
                i += 1
    return out


def detect_layering(store: DataStore) -> list[Signal]:
    """AML-TM-3: inflow >= $15k, >=70% moved out within 48h across >=3 counterparties."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        inflows = [t for t in txns if t.type in ("wire_in", "ach_in") and t.amount >= 15000]
        for inflow in inflows:
            window_end = inflow.timestamp + timedelta(hours=48)
            outflows = [t for t in txns
                        if t.type in ("wire_out", "ach_out")
                        and inflow.timestamp < t.timestamp <= window_end]
            if not outflows:
                continue
            out_total = sum(t.amount for t in outflows)
            counterparties = {(t.counterparty_name, t.counterparty_country) for t in outflows}
            if out_total >= 0.7 * inflow.amount and len(counterparties) >= 3:
                evidence = [inflow.txn_id] + [t.txn_id for t in outflows]
                out.append(Signal(
                    signal_id=_sig_id("LAYER", account_id, inflow.txn_id),
                    signal_type="rapid_layering",
                    severity="High",
                    account_id=account_id,
                    customer_id=inflow.customer_id,
                    summary=(f"${inflow.amount:,.2f} received then ${out_total:,.2f} "
                             f"({out_total/inflow.amount:.0%}) moved out within 48h across "
                             f"{len(counterparties)} counterparties"),
                    citations=["AML-TM-3"],
                    evidence_txn_ids=evidence,
                    details={"inflow_amount": inflow.amount, "outflow_total": out_total,
                             "outflow_pct": out_total / inflow.amount,
                             "counterparty_count": len(counterparties)},
                ))
    return out


def detect_dormant_reactivation(store: DataStore) -> list[Signal]:
    """AML-TM-4: 180+ days dormant, then activity > $5,000 within 72h."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        if len(txns) < 2:
            continue
        for idx in range(1, len(txns)):
            gap = txns[idx].timestamp - txns[idx - 1].timestamp
            if gap >= timedelta(days=180):
                window_end = txns[idx].timestamp + timedelta(hours=72)
                burst = [t for t in txns[idx:] if t.timestamp <= window_end]
                total = sum(t.amount for t in burst)
                if total > 5000:
                    out.append(Signal(
                        signal_id=_sig_id("DORMANT", account_id, txns[idx].txn_id),
                        signal_type="dormant_reactivation",
                        severity="Medium",
                        account_id=account_id,
                        customer_id=txns[idx].customer_id,
                        summary=(f"Account dormant for {gap.days} days, then ${total:,.2f} "
                                 f"in activity within 72 hours"),
                        citations=["AML-TM-4"],
                        evidence_txn_ids=[t.txn_id for t in burst],
                        details={"dormant_days": gap.days, "reactivation_total": total},
                    ))
    return out


def detect_high_risk_jurisdiction(store: DataStore) -> list[Signal]:
    """AML-TM-5 / SANC-3: wires touching a Designated High-Risk Jurisdiction."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        hr_wires = [t for t in txns
                    if t.type in ("wire_in", "wire_out")
                    and t.counterparty_country in HIGH_RISK_JURISDICTIONS]
        if not hr_wires:
            continue
        # group by 30-day rolling window per jurisdiction (simple: whole-account grouping)
        hr_wires.sort(key=lambda t: t.timestamp)
        customer_id = hr_wires[0].customer_id
        if len(hr_wires) >= 3 and (hr_wires[-1].timestamp - hr_wires[0].timestamp) <= timedelta(days=30):
            out.append(Signal(
                signal_id=_sig_id("HRJ", account_id, hr_wires[0].txn_id),
                signal_type="high_risk_jurisdiction",
                severity="High",
                account_id=account_id,
                customer_id=customer_id,
                summary=(f"{len(hr_wires)} wires to/from Designated High-Risk Jurisdictions "
                         f"within {(hr_wires[-1].timestamp - hr_wires[0].timestamp).days} days"),
                citations=["AML-TM-5", "SANC-2", "SANC-3"],
                evidence_txn_ids=[t.txn_id for t in hr_wires],
                details={"jurisdictions": sorted({t.counterparty_country for t in hr_wires}),
                         "count": len(hr_wires)},
            ))
        else:
            for t in hr_wires:
                out.append(Signal(
                    signal_id=_sig_id("HRJ", account_id, t.txn_id),
                    signal_type="high_risk_jurisdiction",
                    severity="Low",
                    account_id=account_id,
                    customer_id=t.customer_id,
                    summary=(f"Wire {t.type.replace('_', ' ')} of ${t.amount:,.2f} involving "
                             f"Designated High-Risk Jurisdiction {t.counterparty_country}"),
                    citations=["AML-TM-5", "SANC-2"],
                    evidence_txn_ids=[t.txn_id],
                    details={"jurisdiction": t.counterparty_country},
                ))
    return out


def detect_card_testing(store: DataStore) -> list[Signal]:
    """AML-TM-6: >=4 ATM withdrawals across locations within a 6-hour window."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        atms = [t for t in txns if t.type == "atm_withdrawal"]
        atms.sort(key=lambda t: t.timestamp)
        n = len(atms)
        i = 0
        while i < n:
            window = [atms[i]]
            j = i + 1
            while j < n and (atms[j].timestamp - atms[i].timestamp) <= timedelta(hours=6):
                window.append(atms[j])
                j += 1
            if len(window) >= 4:
                locations = {t.location for t in window if t.location}
                total = sum(t.amount for t in window)
                out.append(Signal(
                    signal_id=_sig_id("CARDTEST", account_id, window[0].txn_id),
                    signal_type="card_testing_mule",
                    severity="Medium",
                    account_id=account_id,
                    customer_id=window[0].customer_id,
                    summary=(f"{len(window)} ATM withdrawals totaling ${total:,.2f} across "
                             f"{len(locations)} locations within "
                             f"{(window[-1].timestamp - window[0].timestamp)}"),
                    citations=["AML-TM-6"],
                    evidence_txn_ids=[t.txn_id for t in window],
                    details={"count": len(window), "locations": sorted(locations),
                              "total_amount": total},
                ))
                i = j
            else:
                i += 1
    return out


def detect_round_dollar_wires(store: DataStore) -> list[Signal]:
    """AML-TM-10: >=3 round-dollar ($500-divisible) wire_out to a non-US country within 14 days."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        wires = [t for t in txns
                 if t.type == "wire_out" and t.counterparty_country != "US"
                 and abs(t.amount - round(t.amount)) < 1e-6 and round(t.amount) % 500 == 0]
        wires.sort(key=lambda t: t.timestamp)
        n = len(wires)
        i = 0
        while i < n:
            window = [wires[i]]
            j = i + 1
            while j < n and (wires[j].timestamp - wires[i].timestamp) <= timedelta(days=14):
                window.append(wires[j])
                j += 1
            if len(window) >= 3:
                total = sum(t.amount for t in window)
                countries = sorted({t.counterparty_country for t in window})
                out.append(Signal(
                    signal_id=_sig_id("ROUNDWIRE", account_id, window[0].txn_id),
                    signal_type="round_dollar_wires",
                    severity="Medium",
                    account_id=account_id,
                    customer_id=window[0].customer_id,
                    summary=(f"{len(window)} round-dollar international wires totaling "
                             f"${total:,.2f} to {', '.join(countries)} within "
                             f"{(window[-1].timestamp - window[0].timestamp).days + 1} days"),
                    citations=["AML-TM-10"],
                    evidence_txn_ids=[t.txn_id for t in window],
                    details={"count": len(window), "total_amount": total, "countries": countries},
                ))
                i = j
            else:
                i += 1
    return out


def detect_new_account_high_value(store: DataStore) -> list[Signal]:
    """AML-TM-11: any transaction over $8,000 within 30 days of the account's opened_date."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        account = store.accounts.get(account_id)
        if not account:
            continue
        opened_dt = datetime.fromisoformat(account.opened_date)
        qualifying = [t for t in txns
                      if t.currency == "USD" and t.amount > 8000
                      and 0 <= (t.timestamp - opened_dt).days <= 30]
        if not qualifying:
            continue
        qualifying.sort(key=lambda t: t.timestamp)
        total = sum(t.amount for t in qualifying)
        out.append(Signal(
            signal_id=_sig_id("NEWACCT", account_id, qualifying[0].txn_id),
            signal_type="new_account_high_value",
            severity="High",
            account_id=account_id,
            customer_id=qualifying[0].customer_id,
            summary=(f"{len(qualifying)} transaction(s) totaling ${total:,.2f} over $8,000 "
                     f"occurred within 30 days of account opening ({account.opened_date})"),
            citations=["AML-TM-11"],
            evidence_txn_ids=[t.txn_id for t in qualifying],
            details={"count": len(qualifying), "total_amount": total,
                      "opened_date": account.opened_date},
        ))
    return out


def detect_velocity_spike(store: DataStore) -> list[Signal]:
    """AML-TM-12: a day's txn count >= 3x the trailing-90-day daily average, and >= 6."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        if not txns:
            continue
        by_day = defaultdict(list)
        for t in txns:
            by_day[t.timestamp.date()].append(t)
        for d in sorted(by_day.keys()):
            day_txns = by_day[d]
            count = len(day_txns)
            if count < 6:
                continue
            window_start = d - timedelta(days=90)
            prior_count = sum(len(v) for dd, v in by_day.items() if window_start <= dd < d)
            avg = prior_count / 90
            if count >= 3 * avg:
                out.append(Signal(
                    signal_id=_sig_id("VELOCITY", account_id, day_txns[0].txn_id),
                    signal_type="velocity_spike",
                    severity="Medium",
                    account_id=account_id,
                    customer_id=day_txns[0].customer_id,
                    summary=(f"{count} transactions on {d.isoformat()}, vs a trailing 90-day "
                             f"daily average of {avg:.1f} transactions/day (>= 3x spike)"),
                    citations=["AML-TM-12"],
                    evidence_txn_ids=[t.txn_id for t in day_txns],
                    details={"day": d.isoformat(), "day_count": count, "trailing_avg": avg},
                ))
    return out


def detect_upi_mule_hub(store: DataStore) -> list[Signal]:
    """UPI-MULE-2: fan-in from >=5 distinct sender VPAs within 48h, then >=70% of that value
    fanned back out to >=3 distinct receiver VPAs within the following 24h. The dominant
    money-mule "pass-through" signature on India's UPI rail."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        inflows = sorted([t for t in txns if t.type == "upi_in"], key=lambda t: t.timestamp)
        n = len(inflows)
        i = 0
        while i < n:
            j = i + 1
            while j < n and (inflows[j].timestamp - inflows[i].timestamp) <= timedelta(hours=48):
                j += 1
            window = inflows[i:j]
            senders = {t.counterparty_name for t in window}
            if len(senders) >= 5:
                total_in = sum(t.amount for t in window)
                last_in = window[-1].timestamp
                fanout_end = last_in + timedelta(hours=24)
                outflows = [t for t in txns
                            if t.type == "upi_out" and last_in < t.timestamp <= fanout_end]
                out_total = sum(t.amount for t in outflows)
                receivers = {t.counterparty_name for t in outflows}
                if out_total >= 0.7 * total_in and len(receivers) >= 3:
                    evidence = [t.txn_id for t in window] + [t.txn_id for t in outflows]
                    out.append(Signal(
                        signal_id=_sig_id("UPIHUB", account_id, window[0].txn_id),
                        signal_type="upi_mule_hub",
                        severity="High",
                        account_id=account_id,
                        customer_id=window[0].customer_id,
                        summary=(f"Received {format_inr(total_in)} from {len(senders)} distinct "
                                 f"UPI senders within 48h, then sent {format_inr(out_total)} "
                                 f"({out_total/total_in:.0%}) to {len(receivers)} distinct "
                                 f"receivers within the following 24h"),
                        citations=["UPI-MULE-2"],
                        evidence_txn_ids=evidence,
                        details={"total_in": total_in, "total_in_inr": format_inr(total_in),
                                 "sender_count": len(senders), "sender_vpas": sorted(senders),
                                 "total_out": out_total, "total_out_inr": format_inr(out_total),
                                 "out_pct": out_total / total_in, "receiver_count": len(receivers),
                                 "receiver_vpas": sorted(receivers),
                                 "window_start": window[0].timestamp.isoformat()},
                    ))
                i = j
            else:
                i += 1
    return out


def detect_upi_mule_ring(store: DataStore) -> list[Signal]:
    """UPI-MULE-3: two or more independently-flagged Mule Hub accounts directly connected by
    a UPI transfer between them are one Mule Ring, not unrelated alerts. This is the
    graph-based detector: it clusters Signal objects from detect_upi_mule_hub via union-find
    over the account-to-account edges implied by each hub's own fan-out targets, so a
    multi-hop laundering chain is recognized as a single network even though no individual
    account's transactions alone reveal the whole picture."""
    hubs = detect_upi_mule_hub(store)
    if len(hubs) < 2:
        return []
    hub_by_account = {h.account_id: h for h in hubs}

    uf = _UnionFind()
    for h in hubs:
        for vpa in h.details.get("receiver_vpas", []):
            target_account = store.account_id_for_vpa(vpa)
            if target_account and target_account in hub_by_account and target_account != h.account_id:
                uf.union(h.account_id, target_account)

    clusters: dict[str, list[str]] = defaultdict(list)
    for acct in hub_by_account:
        clusters[uf.find(acct)].append(acct)

    out = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        members = sorted(members)
        root = min(members, key=lambda a: hub_by_account[a].details["window_start"])
        root_hub = hub_by_account[root]

        # Node keys are always the VPA string (never account_id), since counterparty_name on
        # every transaction is a VPA -- keying some nodes by account_id and others by VPA
        # would silently duplicate the same hub (once under its account_id, once under its
        # own VPA when it shows up as another hub's counterparty).
        acct_vpa = {a: (store.accounts[a].vpa or a) for a in members}

        evidence_ids: list[str] = []
        nodes: dict[str, dict] = {}
        edges: list[dict] = []
        total_value = 0.0
        for acct in members:
            h = hub_by_account[acct]
            evidence_ids.extend(h.evidence_txn_ids)
            total_value += h.details["total_in"]
            vpa = acct_vpa[acct]
            nodes[vpa] = {"id": vpa, "label": vpa, "role": "hub", "account_id": acct}
            for txn_id in h.evidence_txn_ids:
                t = store.txn_by_id[txn_id]
                if t.type == "upi_in":
                    src = t.counterparty_name
                    if src not in nodes:
                        src_acct = store.account_id_for_vpa(src)
                        role = "hub" if src_acct in hub_by_account else "source"
                        nodes[src] = {"id": src, "label": src, "role": role, "account_id": src_acct}
                    edges.append({"from": src, "to": vpa, "amount": t.amount,
                                  "at": t.timestamp.isoformat()})
                else:
                    dst = t.counterparty_name
                    if dst not in nodes:
                        dst_acct = store.account_id_for_vpa(dst)
                        role = "hub" if dst_acct in hub_by_account else "cashout"
                        nodes[dst] = {"id": dst, "label": dst, "role": role, "account_id": dst_acct}
                    edges.append({"from": vpa, "to": dst, "amount": t.amount,
                                  "at": t.timestamp.isoformat()})

        evidence_ids = sorted(set(evidence_ids))
        out.append(Signal(
            signal_id=_sig_id("UPIRING", root, root_hub.evidence_txn_ids[0]),
            signal_type="upi_mule_ring",
            severity="High",
            account_id=root,
            customer_id=root_hub.customer_id,
            summary=(f"{len(members)} connected UPI Mule Hub accounts ({', '.join(members)}) "
                     f"form a single laundering network moving {format_inr(total_value)} "
                     f"through the ring"),
            citations=["UPI-MULE-3"],
            evidence_txn_ids=evidence_ids,
            details={"ring_size": len(members), "ring_accounts": members,
                     "total_value": total_value, "total_value_inr": format_inr(total_value),
                     "ring_nodes": list(nodes.values()), "ring_edges": edges},
        ))
    return out


def detect_upi_new_beneficiary_high_value(store: DataStore) -> list[Signal]:
    """UPI-MULE-4: a UPI payment to a beneficiary the account has never paid before, for
    5x+ the account's average UPI payment size (min floor Rs 20,000) -- the classic
    OTP-sharing / social-engineering fraud signature: one large, unprecedented payment."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        outflows = sorted([t for t in txns if t.type == "upi_out"], key=lambda t: t.timestamp)
        if len(outflows) < 6:
            continue
        seen_payees: set[str] = set()
        prior_amounts: list[float] = []
        for t in outflows:
            if prior_amounts:
                avg = sum(prior_amounts) / len(prior_amounts)
                if (t.counterparty_name not in seen_payees and avg > 0
                        and t.amount > 5 * avg and t.amount > 20000):
                    out.append(Signal(
                        signal_id=_sig_id("UPINEWBEN", account_id, t.txn_id),
                        signal_type="upi_new_beneficiary_high_value",
                        severity="High",
                        account_id=account_id,
                        customer_id=t.customer_id,
                        summary=(f"First-ever UPI payment of {format_inr(t.amount)} to new "
                                 f"beneficiary {t.counterparty_name}, {t.amount/avg:.1f}x this "
                                 f"account's average UPI payment of {format_inr(avg)}"),
                        citations=["UPI-MULE-4"],
                        evidence_txn_ids=[t.txn_id],
                        details={"amount": t.amount, "amount_inr": format_inr(t.amount),
                                 "avg_payment_inr": format_inr(avg), "multiple": t.amount / avg,
                                 "new_beneficiary": t.counterparty_name},
                    ))
            seen_payees.add(t.counterparty_name)
            prior_amounts.append(t.amount)
    return out


def detect_upi_dormant_reactivation(store: DataStore) -> list[Signal]:
    """UPI-MULE-5: 60+ days with no UPI activity, then >=3 credits from distinct, unrelated
    senders within 24h -- freshly recruited mule accounts sit dormant until a ring is ready
    to route funds through them."""
    out = []
    for account_id, txns in store.txns_by_account.items():
        upi_txns = sorted([t for t in txns if t.type in ("upi_in", "upi_out")],
                           key=lambda t: t.timestamp)
        for idx in range(1, len(upi_txns)):
            gap = upi_txns[idx].timestamp - upi_txns[idx - 1].timestamp
            if gap < timedelta(days=60):
                continue
            window_end = upi_txns[idx].timestamp + timedelta(hours=24)
            burst = [t for t in upi_txns[idx:] if t.timestamp <= window_end and t.type == "upi_in"]
            senders = {t.counterparty_name for t in burst}
            if len(senders) >= 3:
                total = sum(t.amount for t in burst)
                out.append(Signal(
                    signal_id=_sig_id("UPIDORMANT", account_id, upi_txns[idx].txn_id),
                    signal_type="upi_dormant_reactivation",
                    severity="Medium",
                    account_id=account_id,
                    customer_id=upi_txns[idx].customer_id,
                    summary=(f"VPA inactive for {gap.days} days, then {format_inr(total)} "
                             f"received from {len(senders)} distinct, unrelated senders "
                             f"within 24 hours"),
                    citations=["UPI-MULE-5"],
                    evidence_txn_ids=[t.txn_id for t in burst],
                    details={"dormant_days": gap.days, "reactivation_total_inr": format_inr(total),
                             "sender_count": len(senders)},
                ))
    return out


ALL_DETECTORS = [
    detect_structuring,
    detect_layering,
    detect_dormant_reactivation,
    detect_high_risk_jurisdiction,
    detect_card_testing,
    detect_round_dollar_wires,
    detect_new_account_high_value,
    detect_velocity_spike,
    detect_upi_mule_hub,
    detect_upi_mule_ring,
    detect_upi_new_beneficiary_high_value,
    detect_upi_dormant_reactivation,
]


def run_all_signals(store: DataStore) -> list[Signal]:
    signals = []
    for detector in ALL_DETECTORS:
        signals.extend(detector(store))
    return signals
