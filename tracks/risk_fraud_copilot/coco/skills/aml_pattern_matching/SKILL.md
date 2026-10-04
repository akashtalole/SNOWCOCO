---
name: aml_pattern_matching
description: >
  Answers AML/KYC/sanctions questions and matches transaction activity
  against the AML transaction-monitoring and sanctions-screening policy
  corpus, citing the exact policy section for every claim. Use this skill
  when the user asks "what does policy say about X" or wants a citation for
  a compliance rule.
---

# AML Pattern Matching

Search the policy corpus (`POLICY_SEARCH_SERVICE`) for the most relevant
section(s) for the question. Quote or closely paraphrase only what the
retrieved section actually says; always include its `section_id`
(e.g. AML-TM-2, SANC-2, UPI-MULE-3) in the answer.

If no section scores above a reasonable relevance threshold, say so
explicitly rather than guessing a plausible-sounding rule.

When the question also needs a number (e.g. "how much exposure do we have
under this rule"), also query `RISK_FRAUD_SEMANTIC_VIEW` and combine the
governed metric with its policy citation in one answer.
