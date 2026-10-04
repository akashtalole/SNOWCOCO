-- ============================================================================
-- 07_mcp_server.sql
-- The real, live `CREATE MCP SERVER` deployed against this track's Snowflake
-- account (distinct from 06_mcp_connector.md, which documents connecting OUT
-- to external systems like Slack/CRM/regulatory feeds -- this file exposes
-- this track's OWN semantic view + search service AS an MCP server, so any
-- MCP-capable client -- including the Cortex Agent deployed for this track --
-- can call them as MCP tools rather than native cortex_analyst/cortex_search
-- tool types. Attached to the agent via its `mcp_servers:` spec block.
-- See coco/README.md's "Live Pilot Results" section for the live proof
-- (a real server_mcp tool call, gated by an explicit permission_decision).
-- ============================================================================

USE SCHEMA RISK_FRAUD_COPILOT.CORE;

CREATE OR REPLACE MCP SERVER RISK_FRAUD_MCP_SERVER
  FROM SPECIFICATION
  $$
    tools:
      - name: "search_policy_corpus"
        type: "CORTEX_SEARCH_SERVICE_QUERY"
        identifier: "RISK_FRAUD_COPILOT.CORE.POLICY_SEARCH_SERVICE"
        title: "Policy Search"
        description: "Search AML/KYC/sanctions/CTR/Basel/UPI-mule policy sections for citations."
      - name: "query_risk_fraud_analyst"
        type: "CORTEX_ANALYST_MESSAGE"
        identifier: "RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_SEMANTIC_VIEW"
        title: "Risk Fraud Analyst"
        description: "Query transaction, account, and customer facts and metrics via the governed semantic view."
  $$;

-- Skills (see coco/skills/*/SKILL.md) are attached separately, via the
-- agent's own `skills:` spec block referencing a stage:
--   CREATE STAGE IF NOT EXISTS AGENT_SKILLS_STAGE
--       DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE');
--   PUT file://coco/skills/<name>/SKILL.md @AGENT_SKILLS_STAGE/skills/<name>/;
-- then, in the agent's CREATE AGENT ... FROM SPECIFICATION block:
--   skills:
--     - name: "fraud_signal_detection"
--       source: {type: "STAGE", path: "@RISK_FRAUD_COPILOT.CORE.AGENT_SKILLS_STAGE/skills/fraud_signal_detection"}
--     - name: "aml_pattern_matching"
--       source: {type: "STAGE", path: "@RISK_FRAUD_COPILOT.CORE.AGENT_SKILLS_STAGE/skills/aml_pattern_matching"}
--     - name: "basel_metric_computation"
--       source: {type: "STAGE", path: "@RISK_FRAUD_COPILOT.CORE.AGENT_SKILLS_STAGE/skills/basel_metric_computation"}
--   mcp_servers:
--     - server_spec: "RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_MCP_SERVER"
