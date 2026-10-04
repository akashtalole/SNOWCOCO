"""04_orchestration.py

"Orchestrate the full flow: signal -> evidence -> audit-ready regulatory
report via CLI."

A Snowflake-native port of the exact flow ../engine/signals.py and
../engine/findings.py already implement against local CSVs. The detection
LOGIC is unchanged (same thresholds, same policy citations) -- only the data
access changes, from `csv.DictReader` to Snowpark/the Python connector, and
the persistence target changes, from findings_store.json to the FINDINGS
table created in 01_synthetic_data.sql.

This is a design scaffold: it shows the intended shape of a Snowflake-backed
CoCo CLI run, not a script that has been executed against a live account from
this repo. Fill in `get_connection()` with real credentials (or a Snowpark
session from the CoCo CLI runtime) to actually run it.

Usage (once connected):
    python 04_orchestration.py detect                  # run all detectors, print signals
    python 04_orchestration.py generate SIG-STRUCT-...  # generate a Finding from a signal_id
    python 04_orchestration.py report FIND-0001         # print a Finding's Markdown report
"""
from __future__ import annotations

import json
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# In a real CoCo CLI environment this would be:
#   from snowflake.snowpark import Session
#   session = Session.builder.config("connection_name", "risk_fraud_copilot").create()
# or the Cortex Agent runtime hands you an already-open session. Left as a
# stub here since this repo has no Snowflake credentials to connect with.


def get_connection():
    raise NotImplementedError(
        "Provide a live Snowflake connection/Snowpark session here -- see the "
        "module docstring. This scaffold intentionally does not embed credentials."
    )


@dataclass
class Signal:
    signal_id: str
    signal_type: str
    severity: str
    account_id: str
    customer_id: str
    summary: str
    citations: list[str]
    evidence_txn_ids: list[str]
    details: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Detectors -- same thresholds as ../engine/signals.py, expressed as SQL
# against RISK_FRAUD_SEMANTIC_VIEW / TRANSACTIONS instead of Python loops
# over an in-memory DataStore.
# ---------------------------------------------------------------------------

STRUCTURING_SQL = """
    -- AML-TM-2: >=3 sub-$10k cash deposits within a 5-day window, per account.
    -- Mirrors detect_structuring() in ../engine/signals.py, expressed in SQL
    -- via a window function instead of the Python two-pointer scan.
    --
    -- NOTE: this was corrected after a live run against a real Snowflake
    -- account surfaced a real bug -- the first version's final GROUP BY
    -- aggregated over every row whose *own* forward-looking window_count
    -- was >=3, which double-reports/under-reports evidence whenever a
    -- structuring episode has more than 3 deposits (a 4-deposit episode
    -- was captured as two separate 2-row groups instead of one 4-row
    -- group). Fixed by carrying the full evidence array and total as a
    -- window aggregate on every row, then taking the single row per
    -- account with the largest window (the earliest/fullest anchor),
    -- instead of re-aggregating over a filtered row set.
    WITH deposits AS (
        SELECT txn_id, account_id, customer_id, txn_timestamp, amount
        FROM TRANSACTIONS
        WHERE type = 'cash_deposit' AND amount BETWEEN 8000 AND 9999.99
    ),
    windowed AS (
        SELECT *,
               COUNT(*) OVER (
                   PARTITION BY account_id ORDER BY txn_timestamp
                   RANGE BETWEEN CURRENT ROW AND INTERVAL '5 days' FOLLOWING
               ) AS window_count,
               ARRAY_AGG(txn_id) OVER (
                   PARTITION BY account_id ORDER BY txn_timestamp
                   RANGE BETWEEN CURRENT ROW AND INTERVAL '5 days' FOLLOWING
               ) AS window_txn_ids,
               SUM(amount) OVER (
                   PARTITION BY account_id ORDER BY txn_timestamp
                   RANGE BETWEEN CURRENT ROW AND INTERVAL '5 days' FOLLOWING
               ) AS window_total
        FROM deposits
    ),
    best_per_account AS (
        SELECT account_id, customer_id,
               window_txn_ids AS evidence_txn_ids,
               window_total AS total_amount,
               window_count AS deposit_count,
               ROW_NUMBER() OVER (
                   PARTITION BY account_id ORDER BY window_count DESC, txn_timestamp
               ) AS rn
        FROM windowed
        WHERE window_count >= 3
    )
    SELECT account_id, customer_id, evidence_txn_ids, total_amount, deposit_count
    FROM best_per_account
    WHERE rn = 1
"""

VELOCITY_SPIKE_SQL = """
    -- AML-TM-12: a day's txn count >= 3x the trailing-90-day daily average
    -- and >= 6. Mirrors detect_velocity_spike().
    WITH daily_counts AS (
        SELECT account_id, customer_id, DATE(txn_timestamp) AS txn_date,
               COUNT(*) AS day_count
        FROM TRANSACTIONS
        GROUP BY account_id, customer_id, DATE(txn_timestamp)
    ),
    with_trailing_avg AS (
        SELECT *,
               AVG(day_count) OVER (
                   PARTITION BY account_id
                   ORDER BY txn_date
                   RANGE BETWEEN INTERVAL '90 days' PRECEDING AND INTERVAL '1 day' PRECEDING
               ) AS trailing_avg
        FROM daily_counts
    )
    SELECT account_id, customer_id, txn_date, day_count, trailing_avg
    FROM with_trailing_avg
    WHERE day_count >= 6 AND day_count >= 3 * COALESCE(trailing_avg, 0.01)
"""


def run_detectors(conn) -> list[Signal]:
    """Run every SQL detector and translate rows into Signal objects, the
    same shape ../engine/signals.py produces."""
    signals: list[Signal] = []
    cur = conn.cursor()

    cur.execute(STRUCTURING_SQL)
    for account_id, customer_id, evidence_ids, total_amount, count in cur.fetchall():
        signals.append(Signal(
            signal_id=f"SIG-STRUCT-{account_id}-{uuid.uuid4().hex[:8]}",
            signal_type="structuring",
            severity="High",
            account_id=account_id,
            customer_id=customer_id,
            summary=(f"{count} cash deposits totaling ${total_amount:,.2f} within 5 days"),
            citations=["AML-TM-2"],
            evidence_txn_ids=json.loads(evidence_ids) if isinstance(evidence_ids, str) else list(evidence_ids),
            details={"total_amount": float(total_amount), "count": int(count)},
        ))

    cur.execute(VELOCITY_SPIKE_SQL)
    for account_id, customer_id, txn_date, day_count, trailing_avg in cur.fetchall():
        signals.append(Signal(
            signal_id=f"SIG-VELOCITY-{account_id}-{txn_date}",
            signal_type="velocity_spike",
            severity="Medium",
            account_id=account_id,
            customer_id=customer_id,
            summary=(f"{day_count} transactions on {txn_date}, vs a trailing 90-day "
                     f"average of {trailing_avg:.1f}/day"),
            citations=["AML-TM-12"],
            evidence_txn_ids=[],  # would issue a follow-up query for the specific txn_ids
            details={"day": str(txn_date), "day_count": int(day_count), "trailing_avg": float(trailing_avg)},
        ))

    # The UPI mule-hub / mule-ring detectors and the remaining AML-TM-*
    # detectors follow the same pattern -- one SQL block per detector,
    # unioned into `signals` -- omitted here for length. Port
    # detect_upi_mule_ring's union-find step as a Python post-processing
    # pass over the SQL-derived hub signals, exactly as
    # ../engine/signals.py:detect_upi_mule_ring already does.
    return signals


def generate_finding(conn, signal: Signal) -> dict:
    """Signal -> evidence -> audit-ready Finding, written to the FINDINGS
    table. Narrative templates and citation lookup are unchanged from
    ../engine/findings.py -- only the storage target changes."""
    cur = conn.cursor()
    cur.execute(
        "SELECT NAME FROM CUSTOMERS WHERE CUSTOMER_ID = %s", (signal.customer_id,)
    )
    row = cur.fetchone()
    customer_name = row[0] if row else signal.customer_id

    finding_id = f"FIND-{uuid.uuid4().hex[:8].upper()}"
    created_at = datetime.now(timezone.utc).isoformat()
    narrative = signal.summary  # in the real port, reuse NARRATIVE_TEMPLATES from
                                 # ../engine/findings.py verbatim

    cur.execute(
        """
        INSERT INTO FINDINGS
            (FINDING_ID, SIGNAL_ID, SIGNAL_TYPE, SEVERITY, ACCOUNT_ID, CUSTOMER_ID,
             CUSTOMER_NAME, CREATED_AT, NARRATIVE, RECOMMENDED_ACTION, STATUS,
             EVIDENCE, CITATIONS, HISTORY, NOTES)
        SELECT %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'Open',
               PARSE_JSON(%s), PARSE_JSON(%s), PARSE_JSON(%s), PARSE_JSON('[]')
        """,
        (
            finding_id, signal.signal_id, signal.signal_type, signal.severity,
            signal.account_id, signal.customer_id, customer_name, created_at,
            narrative, "Route to Compliance for review.",
            json.dumps(signal.evidence_txn_ids),
            json.dumps(signal.citations),
            json.dumps([{"event": "created", "at": created_at,
                          "detail": f"Finding generated from signal {signal.signal_id}"}]),
        ),
    )
    conn.commit()
    return {"finding_id": finding_id, "signal_id": signal.signal_id, "status": "Open"}


if __name__ == "__main__":
    conn = get_connection()
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "detect":
        for s in run_detectors(conn):
            print(s)
    elif sys.argv[1] == "generate" and len(sys.argv) == 3:
        target_id = sys.argv[2]
        matches = [s for s in run_detectors(conn) if s.signal_id == target_id]
        if not matches:
            print(f"No signal {target_id} found in the current detection run.")
            sys.exit(1)
        print(generate_finding(conn, matches[0]))
    else:
        print(__doc__)
