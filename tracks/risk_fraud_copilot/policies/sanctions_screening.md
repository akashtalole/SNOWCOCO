# Sanctions & High-Risk Jurisdiction Screening Policy

*Internal Policy Manual — Financial Crime Compliance*
*Document: SANC · Version 1.8 · Owner: Head of Financial Crime Compliance*

> **Synthetic demo document.** Jurisdiction codes below are fictional and used only to make the
> demo self-contained; they do not correspond to real-world sanctions designations.

## SANC-1. Screening Requirement

All wire transfers, counterparties, and beneficial owners must be screened against the Bank's
consolidated watchlist ("SynthWatch") prior to or immediately after settlement. Any match, partial
match, or transaction touching a Designated High-Risk Jurisdiction must be logged.

## SANC-2. Designated High-Risk Jurisdiction List (Appendix A)

For the purposes of this synthetic environment, the following fictional jurisdiction codes are
designated **High-Risk**:

| Code | Label                          | Reason for designation                    |
|------|---------------------------------|--------------------------------------------|
| ZX   | High-Risk Jurisdiction "Zeta"   | Weak AML supervisory regime (synthetic)     |
| QW   | High-Risk Jurisdiction "Quorra" | Elevated trade-based ML typology (synthetic)|

All other jurisdiction codes used in this demo (US, UK, DE, SG, CA, AU, JP, IN) are treated as
standard risk.

## SANC-3. Escalation

A single transaction touching a High-Risk Jurisdiction is logged with a jurisdiction-risk
annotation per AML-TM-5. Three or more transactions to/from the same High-Risk Jurisdiction by one
customer within 30 days requires a Finding and Compliance Officer sign-off before the account may
process further international wires.
