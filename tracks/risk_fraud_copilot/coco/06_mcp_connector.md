# MCP Connector — External Regulatory Sources

"Connect to external regulatory sources via MCP for live policy lookups."

The synthetic policy corpus in `../policies/*.md` is a static, offline stand-in for what a
production deployment would look up live. This is the connector definition that would let the
Cortex Agent (`03_cortex_agent_skills.yaml`) call out to a real regulatory source — an MCP server
the agent can invoke as a tool, the same way the Loop Harness diagram's "Agentic Tools" box shows
tool calls flowing out of the Primary Agent (see `../../../docs/coco_cli_architecture.md`).

> This is a design stub, not a running server. No real regulatory API is called from this repo.

## Why MCP here specifically

`aml_pattern_matching` and `basel_metric_computation` (see `03_cortex_agent_skills.yaml`) both cite
policy sections from the static corpus. In production, a compliance analyst would also want the
agent to check whether a *live* regulator circular or update supersedes what's in the corpus —
that's exactly the kind of external, changing, authoritative data source MCP is meant to expose to
an agent without hand-coding a bespoke integration per source.

## Example MCP server manifest

```json
{
  "name": "regulatory-lookup",
  "description": "Live lookups against external regulatory circulars/updates for AML, Basel, and local (e.g. RBI-style) regulations, to supplement the static policy corpus.",
  "tools": [
    {
      "name": "search_regulatory_circulars",
      "description": "Full-text search over recent regulatory circulars/notifications by keyword or topic.",
      "input_schema": {
        "type": "object",
        "properties": {
          "query": {"type": "string", "description": "Keyword or topic, e.g. 'UPI mule account advisory'"},
          "jurisdiction": {"type": "string", "description": "e.g. 'IN', 'US'"},
          "since_date": {"type": "string", "format": "date"}
        },
        "required": ["query"]
      }
    },
    {
      "name": "get_circular_by_id",
      "description": "Fetch the full text of one specific circular/notification by its official reference ID.",
      "input_schema": {
        "type": "object",
        "properties": {"circular_id": {"type": "string"}},
        "required": ["circular_id"]
      }
    }
  ]
}
```

## Wiring it into the Cortex Agent skill

Add to `aml_pattern_matching` in `03_cortex_agent_skills.yaml`:

```yaml
    tools:
      - type: cortex_search
        search_service: POLICY_SEARCH_SERVICE
      - type: cortex_analyst
        semantic_view: RISK_FRAUD_SEMANTIC_VIEW
      - type: mcp
        server: regulatory-lookup
        allowed_tools: [search_regulatory_circulars, get_circular_by_id]
```

And extend the skill's `instructions` to require the agent to distinguish citations from the
static corpus (e.g. `AML-TM-2`) from citations pulled live via MCP (e.g. a circular reference ID),
so an analyst reading a Finding's report always knows which kind of source backs which claim.

## Candidate real sources (not yet chosen or integrated)

- RBI (Reserve Bank of India) circular/notification feeds, for AML/KYC/UPI-fraud guidance relevant
  to the UPI mule-network module (`../policies/upi_fraud_mule_detection.md`).
- Basel Committee on Banking Supervision publications, for the LCR/liquidity policy
  (`../policies/basel_liquidity_lcr.md`).
- India's **1930** cybercrime helpline / **CFCFRMS** system, referenced descriptively in
  `../policies/upi_fraud_mule_detection.md` (UPI-MULE-6) as where a confirmed mule-ring Finding
  would be reported in production — this would be a *write* tool (filing/escalation), not just a
  lookup, and needs its own authorization/audit design before wiring in for real.
