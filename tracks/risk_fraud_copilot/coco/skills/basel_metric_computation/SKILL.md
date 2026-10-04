---
name: basel_metric_computation
description: >
  Computes Basel-style liquidity/capital metrics referenced in the Basel
  Liquidity Coverage Ratio policy, and explains a computed value by tracing
  it back to its inputs. Use this skill when the user asks about LCR,
  liquidity buffers, or capital ratios.
---

# Basel Metric Computation

Compute the requested metric only from figures available in
`RISK_FRAUD_SEMANTIC_VIEW` or an explicitly supplied input; never fabricate
a balance-sheet figure that was not retrieved.

State the formula used and cite the LCR-* policy section that defines it,
via `POLICY_SEARCH_SERVICE`.

If a required input isn't available in the semantic view, say so explicitly
rather than estimating it.
