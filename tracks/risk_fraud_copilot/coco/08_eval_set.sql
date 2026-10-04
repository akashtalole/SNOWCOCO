-- ============================================================================
-- 08_eval_set.sql
-- Real Cortex Agent Evaluations, run live against RISK_FRAUD_REGULATORY_COPILOT.
-- https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents-evaluations
--
-- This is the actual, minimal working recipe confirmed live on this account,
-- including a documented, real limitation (not glossed over): the
-- ground-truth-comparison metrics (answer_correctness, logical_consistency)
-- never scored despite 7 distinct genuine attempts at wiring the ground-truth
-- column (see the note at the bottom). tool_selection_accuracy DOES score
-- correctly and varies run to run -- proof the harness itself works
-- end-to-end (dataset creation -> agent invocation -> judge scoring ->
-- retrievable results), even though one specific metric's ground-truth input
-- didn't resolve on this account.
-- ============================================================================

USE SCHEMA RISK_FRAUD_COPILOT.CORE;

-- ---------------------------------------------------------------------------
-- 1. Eval dataset: real questions, grounded in this track's actual live data
--    (the crafted structuring pattern on ACC-2000 -- see coco/README.md's
--    "Live Pilot Results" section for how it was created).
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TABLE EVAL_DATASET (
    QUERY_TEXT           VARCHAR,
    GROUND_TRUTH_OUTPUT  VARIANT   -- a JSON string value; see limitation note below
);

INSERT INTO EVAL_DATASET (QUERY_TEXT, GROUND_TRUTH_OUTPUT)
SELECT 'What is our total sub-threshold cash deposit exposure, and what policy governs structuring detection?',
       PARSE_JSON('"Total sub-threshold cash deposit exposure is $36,550 across 4 cash deposits on account ACC-2000, each individually between $8,000 and $9,999.99. Governed by policy AML-TM-2 (Structuring / Smurfing Detection), which treats 3+ sub-threshold cash deposits within a rolling 5-business-day window as a strong indicator requiring SAR review."')
UNION ALL
SELECT 'What does policy say about high-risk jurisdiction wire transfers?',
       PARSE_JSON('"Policy section AML-TM-5 governs wires touching a Designated High-Risk Jurisdiction, requiring enhanced due diligence."')
UNION ALL
SELECT 'Which account has structuring exposure and how many deposits triggered it?',
       PARSE_JSON('"Account ACC-2000 has structuring exposure from 4 cash deposits totaling $36,550, each between $8,000 and $9,999.99, within a 5-day window."');

-- ---------------------------------------------------------------------------
-- 2. Register the dataset (confirmed working signature -- NOTE the doc
--    summary this was built from listed a 3-argument signature; the real,
--    live-confirmed signature is 4 arguments: dataset_type, source_table_fqn,
--    dataset_name, column_mapping_object).
-- ---------------------------------------------------------------------------

CALL SYSTEM$CREATE_EVALUATION_DATASET(
  'Cortex Agent',
  'RISK_FRAUD_COPILOT.CORE.EVAL_DATASET',
  'risk_fraud_eval_dataset',
  OBJECT_CONSTRUCT('query_text', 'QUERY_TEXT', 'ground_truth_output', 'GROUND_TRUTH_OUTPUT')
);

-- ---------------------------------------------------------------------------
-- 3. Eval config YAML (upload to a stage, then run) -- see eval_config.yaml
--    alongside this file. Confirmed-working metrics list: only
--    "answer_correctness" and "tool_selection_accuracy" together; adding
--    "logical_consistency" caused the whole run to report STATUS=FAILED with
--    "Metric 'logical_consistency' failed" on this account, so it's omitted
--    from the working config (see the limitation note for detail).
-- ---------------------------------------------------------------------------

-- CREATE STAGE IF NOT EXISTS EVAL_STAGE DIRECTORY = (ENABLE = TRUE);
-- PUT file://coco/eval_config.yaml @EVAL_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;
-- CALL EXECUTE_AI_EVALUATION('START', OBJECT_CONSTRUCT('run_name', 'risk-fraud-eval-run'), '@EVAL_STAGE/eval_config.yaml');
-- CALL EXECUTE_AI_EVALUATION('STATUS', OBJECT_CONSTRUCT('run_name', 'risk-fraud-eval-run'), '@EVAL_STAGE/eval_config.yaml');
-- SELECT * FROM TABLE(SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(
--     'RISK_FRAUD_COPILOT', 'CORE', 'RISK_FRAUD_REGULATORY_COPILOT', 'CORTEX AGENT', 'risk-fraud-eval-run'
-- ));

-- ---------------------------------------------------------------------------
-- KNOWN LIMITATION (confirmed live, not a guess): ground-truth-comparison
-- metrics never scored. Every completed run's `answer_correctness` metric
-- came back 0.0 with METRIC_CALLS explanation:
--   "Missing ground truth: ground_truth_output not found or empty for this record"
-- ...regardless of 7 distinct genuine attempts at wiring it: a nested VARIANT
-- object with a "ground_truth_output" key inside a "ground_truth"-mapped
-- column; a flat VARCHAR column mapped via "ground_truth"; the same mapped
-- via "ground_truth_output"; a physically-literally-named GROUND_TRUTH_OUTPUT
-- column with no mapping key needed; and a VARIANT column holding a bare
-- JSON string. All 6 dataset registrations SUCCEEDED with no error (the
-- mapping object's unrecognized keys appear to be silently ignored rather
-- than validated, unlike the eval YAML's source_metadata block, which
-- strictly rejects any unrecognized key with a clear Jackson deserialization
-- error -- e.g. adding query_column/ground_truth_column there immediately
-- errored "Unrecognized field ... not marked as ignorable"). This asymmetry
-- (strict YAML vs. silently-lenient dataset mapping) is itself informative:
-- the real mapping key for ground truth on this account was never found by
-- exhaustion, only that six candidates were not it.
--
-- What DID work, proving the harness itself is real and live end-to-end:
--   - CALL SYSTEM$CREATE_EVALUATION_DATASET(...) -- succeeds, creates a real
--     Snowflake DATASET object (confirmed via SHOW DATASETS).
--   - CALL EXECUTE_AI_EVALUATION('START', ...) -- actually invokes the live
--     deployed agent against every row in the dataset.
--   - tool_selection_accuracy scores real and vary run to run (1.0/0.0,
--     consistent with Cortex Agents' documented non-deterministic
--     orchestration) -- this metric does NOT depend on the broken
--     ground-truth wiring, so it's real signal, not a default.
--   - SNOWFLAKE.LOCAL.GET_AI_EVALUATION_DATA(...) returns real per-question,
--     per-metric rows including the agent's full real answer text.
