# AML Transaction Monitoring Policy

*Internal Policy Manual — Financial Crime Compliance*
*Document: AML-TM · Version 3.1 · Owner: Head of Financial Crime Compliance*

> **Synthetic demo document.** Thresholds and language are illustrative only, modeled loosely on
> common BSA/AML-style transaction monitoring practice. This is not legal or regulatory advice.

## AML-TM-1. Purpose & Scope

This policy governs automated and manual monitoring of customer transaction activity for
indicators of money laundering, terrorist financing, or fraud. It applies to all retail and
business accounts held by the Bank.

## AML-TM-2. Structuring / Smurfing Detection

A pattern of multiple cash transactions, each individually below the $10,000 Currency
Transaction Report (CTR) threshold, that in aggregate exceed $10,000 for a single customer or
related accounts within a rolling 5-business-day window, must be escalated as a **potential
structuring signal**. Three or more sub-threshold cash deposits (each between $8,000 and $9,999)
within that window is treated as a strong indicator requiring SAR (Suspicious Activity Report)
review by a Financial Crime Analyst within 2 business days of detection.

## AML-TM-3. Rapid Movement of Funds (Layering)

Where an account receives an incoming credit of $15,000 or more, and 70% or more of that value
is transferred out again within 48 hours across three or more distinct counterparties or
jurisdictions, the activity must be flagged as a **Tier 2 layering alert**. Analysts must
document the original source of funds and the destination of each outbound leg.

## AML-TM-4. Dormant Account Reactivation

An account with no debit or credit activity for 180 calendar days that suddenly processes a
transaction (or series of transactions within 72 hours) exceeding $5,000 in aggregate must be
flagged for **Enhanced Due Diligence (EDD)** review. Analysts should verify the transaction is
consistent with the customer's known profile and stated purpose of account.

## AML-TM-5. High-Risk Jurisdiction Transactions

Any wire transfer, inbound or outbound, involving a counterparty located in a jurisdiction on the
Bank's Designated High-Risk Jurisdiction List (see `sanctions_screening.md`, Appendix A) requires
enhanced scrutiny regardless of transaction amount, and must be logged with a jurisdiction-risk
annotation on the customer file.

## AML-TM-6. Card / ATM Testing and Mule Indicators

Multiple ATM withdrawals or point-of-sale authorizations across geographically distant locations
within a short window (under 6 hours) for a single card or account, particularly involving
round-dollar amounts, must be flagged as a potential **card testing / money-mule indicator** and
referred to Fraud Operations for real-time review.

## AML-TM-7. Escalation & SLA

All Tier 1 signals must be triaged within 1 business day. Tier 2 and above signals require a
documented Finding with cited evidentiary transactions and applicable policy sections, and must
be either closed with rationale or escalated to SAR filing within 5 business days of detection.

## AML-TM-10. Round-Dollar International Wire Pattern

Three or more outbound wire transfers to a counterparty located outside the United States, each
for an exact round-dollar amount (a multiple of $500, e.g. $5,000.00 or $2,500.00), originating
from the same account within a rolling 14-day window, must be flagged as a **Tier 1 round-dollar
wire signal**. Round, evenly-divisible wire amounts sent internationally in a short window are a
common indicator of pre-agreed or scripted fund movement rather than ordinary commercial payment
activity, and warrant review of the underlying business purpose for each wire.

## AML-TM-11. New Account High-Value Activity

Any single transaction exceeding $8,000 that occurs within 30 calendar days of an account's
opening date must be flagged as a **new-account high-value signal** and treated as a Tier 1
priority for review. Newly opened accounts have limited transaction history against which to
assess whether high-value activity is consistent with the customer's stated profile, so such
activity requires prompt Know Your Customer (KYC) re-verification before further high-value
transactions are processed.

## AML-TM-12. Transaction Velocity Spike

A calendar day on which an account's transaction count is at least three times its trailing
90-day average daily transaction count, and is at least 6 transactions for that day, must be
flagged as a **transaction velocity spike**. This threshold is designed to catch sudden bursts of
account activity — consistent with account takeover, bot-driven testing, or funnel-account
behavior — while excluding low-activity accounts where a small absolute increase would otherwise
appear as a large relative spike.
