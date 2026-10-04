---
name: fraud_signal_detection
description: >
  Detects account-level and network-level fraud signals (structuring,
  layering, dormant-account reactivation, card testing, UPI mule hub/ring)
  by querying the governed transaction semantic view. Use this skill when
  the user asks about suspicious transaction patterns, exposure amounts, or
  which accounts show fraud indicators.
---

# Fraud Signal Detection

Given an account_id, customer_id, or free-text question, query
`RISK_FRAUD_SEMANTIC_VIEW` for the relevant metrics
(`sub_threshold_cash_total`, `high_risk_jurisdiction_wire_total`,
`daily_txn_count`, `upi_total`) over the account/window in question.

Only report a signal when the underlying metric crosses the threshold
defined in the cited policy section — do not infer a signal from a metric
you have not actually retrieved.

Every signal you report must name:
- `signal_type`
- `severity`
- the `account_id`(s) and `customer_id`(s) involved
- the metric value(s) that triggered it
- the policy `section_id` it cites (e.g. AML-TM-2, UPI-MULE-3)

For graph-based detection (e.g. UPI mule-ring clustering) that a semantic
view's metrics alone cannot express, issue a parameterized SQL query
against `TRANSACTIONS`/`ACCOUNTS` directly instead of guessing.
