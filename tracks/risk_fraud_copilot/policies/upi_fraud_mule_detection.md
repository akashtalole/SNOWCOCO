# UPI Fraud & Mule Account Network Detection Policy

*Internal Policy Manual — Financial Crime Compliance*
*Document: UPI-MULE · Version 1.0 · Owner: Head of Financial Crime Compliance*

> **Synthetic demo document.** Thresholds and language are illustrative only, modeled loosely on
> the kind of transaction-monitoring controls Indian banks and PSPs run over the UPI (Unified
> Payments Interface) rail, informed by public NPCI/RBI-style risk-control concepts. This is not
> real regulatory guidance and does not reproduce any actual bank's or regulator's rules.

## UPI-MULE-1. Purpose & Scope

This policy governs monitoring of UPI (P2P and P2M) transaction activity for indicators of money
mule recruitment and layering — the dominant fraud pattern on India's real-time payments rail,
where a victim is socially engineered (OTP fraud, fake collect requests, investment/job scams)
into transferring funds that are then rapidly moved through a chain of "mule" accounts to
frustrate tracing and recovery. It applies to all UPI-linked accounts (identified by a Virtual
Payment Address, or VPA) held by the Bank.

## UPI-MULE-2. Fan-In / Fan-Out Mule Hub Detection

An account that receives UPI credits from **5 or more distinct sender VPAs within a rolling
48-hour window**, and within the **following 24 hours** transfers **70% or more of that inflow
value** back out to **3 or more distinct receiver VPAs**, must be flagged as a **Mule Hub**. This
"pass-through" signature — funds arriving from many unrelated sources and immediately being
disbursed onward — is the single strongest indicator of a recruited money-mule account, since
legitimate consumer accounts rarely both receive from, and pay out to, unrelated parties at that
velocity. Mule Hub signals are High severity and must be reviewed by a Financial Crime Analyst
within 4 hours of detection.

## UPI-MULE-3. Mule Ring / Connected Network Detection

Individual Mule Hub accounts (UPI-MULE-2) are often only one layer of a longer laundering chain,
where one hub's fan-out target is itself another Mule Hub. Where two or more accounts independently
meeting the UPI-MULE-2 criteria are directly connected by a UPI transfer between them within the
same detection window, the accounts must be treated as a single **Mule Ring** and escalated
together — not investigated as unrelated individual alerts. A Mule Ring finding requires: (a) a
network diagram showing every account and external VPA in the ring together with the transferred
amounts, (b) immediate account holds pending investigation for every ring member the Bank can
freeze, and (c) referral to Fraud Operations for law-enforcement coordination. Because a ring
represents active, ongoing layering rather than a single suspicious account, Mule Ring signals are
High severity with a 2-hour SLA — faster than a standalone Mule Hub — since delay allows further
layers to be added before funds can be frozen.

## UPI-MULE-4. New-Beneficiary High-Value First Transaction

A UPI payment to a beneficiary VPA the paying account has **never paid before**, where the amount
exceeds **5 times the account's average UPI payment size** (and a minimum floor of ₹20,000), must
be flagged. This pattern is characteristic of OTP-sharing and social-engineering fraud, where a
victim is talked into making one large, unprecedented payment to an unfamiliar VPA (a fake
"refund," a fraudulent investment scheme, or a scan-to-pay QR code disguised as scan-to-receive).
Because the customer — not the account — is usually the victim here, the recommended action is
outbound customer contact to confirm the payment was genuinely authorized, not an account freeze.

## UPI-MULE-5. Dormant VPA Reactivation Burst

A UPI-linked account with no UPI activity for **60 or more days** that then receives **3 or more
credits from distinct, unrelated sender VPAs within a 24-hour window** must be flagged. Freshly
recruited money mules are frequently dormant or newly opened accounts that sit unused until the
fraud ring is ready to route funds through them, at which point they receive a short, sharp burst
of unrelated inbound credits before being abandoned. This is UPI-MULE-5, distinct from the general
account-dormancy control in `aml_transaction_monitoring.md` (AML-TM-4), because the multi-sender
signature — not simply the resumption of activity — is what makes it mule-specific.

## UPI-MULE-6. Escalation, SLA & External Referral

All UPI-MULE signals require a documented Finding citing the evidentiary transactions and the
applicable clause above. High-severity Mule Hub and Mule Ring findings must be triaged within the
SLA stated in their clause; Medium/High New-Beneficiary and Dormant-Reactivation findings within 1
business day. Findings that confirm mule activity are, in a production deployment, referable to
India's national cybercrime reporting channel — the **1930** helpline and the **Citizen Financial
Cyber Fraud Reporting and Management System (CFCFRMS)** operated by the Indian Cybercrime
Coordination Centre (I4C) — for the victim-side complaint and cross-bank fund-freeze coordination
that no single bank's own systems can do alone. This demo does not file anything with any real
system; it documents *where* a production version of this workflow would hand off.
