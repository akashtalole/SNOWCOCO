-- ============================================================================
-- 02_semantic_views.sql
-- "Build semantic views over transaction and policy text for governed
--  natural language queries."
--
-- Two halves: (a) a Cortex Analyst SEMANTIC VIEW over the structured
-- transaction/account facts, encoding the same metrics the Python detectors
-- in ../engine/signals.py compute, so "what's our structuring exposure this
-- week" resolves consistently regardless of who asks; (b) a Cortex Search
-- service over the policy corpus (../policies/*.md) so policy text is
-- retrievable by meaning, replacing the pure-Python TF-IDF index in
-- ../engine/retrieval.py with a managed, embeddings-backed equivalent.
-- ============================================================================

USE SCHEMA RISK_FRAUD_COPILOT.CORE;

-- ---------------------------------------------------------------------------
-- (a) Semantic view over transactions/accounts/customers
-- ---------------------------------------------------------------------------
-- Syntax matches Snowflake's CREATE SEMANTIC VIEW (Cortex Analyst); verify
-- against the current Snowflake docs for your account's release train before
-- running, since this DDL surface is still evolving.

CREATE OR REPLACE SEMANTIC VIEW RISK_FRAUD_SEMANTIC_VIEW
    TABLES (
        customers AS CUSTOMERS
            PRIMARY KEY (CUSTOMER_ID)
            WITH SYNONYMS ('clients', 'account holders')
            COMMENT = 'Bank customers, one row per customer.',
        accounts AS ACCOUNTS
            PRIMARY KEY (ACCOUNT_ID)
            WITH SYNONYMS ('bank accounts')
            COMMENT = 'Bank accounts, one row per account.',
        transactions AS TRANSACTIONS
            PRIMARY KEY (TXN_ID)
            WITH SYNONYMS ('txns', 'payments', 'transfers')
            COMMENT = 'Every transaction (cash, wire, ACH, UPI, ATM, card) across all accounts.'
    )
    RELATIONSHIPS (
        transactions_to_accounts AS transactions (ACCOUNT_ID) REFERENCES accounts (ACCOUNT_ID),
        accounts_to_customers    AS accounts (CUSTOMER_ID) REFERENCES customers (CUSTOMER_ID)
    )
    FACTS (
        transactions.amount_fact AS transactions.AMOUNT
            COMMENT = 'Raw transaction amount in its native currency.'
    )
    DIMENSIONS (
        customers.customer_id     AS customers.CUSTOMER_ID,
        customers.risk_rating     AS customers.RISK_RATING
            WITH SYNONYMS ('KYC risk rating'),
        customers.country         AS customers.COUNTRY,
        accounts.account_id       AS accounts.ACCOUNT_ID,
        accounts.opened_date      AS accounts.OPENED_DATE,
        transactions.txn_type     AS transactions.TYPE
            WITH SYNONYMS ('transaction type'),
        transactions.counterparty_country AS transactions.COUNTERPARTY_COUNTRY,
        transactions.channel      AS transactions.CHANNEL,
        transactions.txn_date     AS DATE(transactions.TXN_TIMESTAMP)
    )
    METRICS (
        -- Mirrors detect_structuring's threshold in ../engine/signals.py (AML-TM-2):
        -- cash deposits individually below $10,000.
        transactions.sub_threshold_cash_total AS
            SUM(IFF(transactions.TYPE = 'cash_deposit'
                    AND transactions.AMOUNT BETWEEN 8000 AND 9999.99,
                    transactions.AMOUNT, 0))
            COMMENT = 'Total value of individually sub-$10k cash deposits -- AML-TM-2 structuring exposure.',

        -- Mirrors detect_high_risk_jurisdiction (AML-TM-5): wires touching ZX/QW.
        transactions.high_risk_jurisdiction_wire_total AS
            SUM(IFF(transactions.TYPE IN ('wire_in', 'wire_out')
                    AND transactions.COUNTERPARTY_COUNTRY IN ('ZX', 'QW'),
                    transactions.AMOUNT, 0))
            COMMENT = 'Total wire value touching a Designated High-Risk Jurisdiction -- AML-TM-5.',

        -- Mirrors AML-TM-12's daily transaction-count velocity check.
        transactions.daily_txn_count AS
            COUNT(transactions.TXN_ID)
            COMMENT = 'Transaction count, for velocity-spike comparisons against a trailing average -- AML-TM-12.',

        transactions.upi_total AS
            SUM(IFF(transactions.TYPE IN ('upi_in', 'upi_out'), transactions.AMOUNT, 0))
            COMMENT = 'Total UPI-rail transaction value -- feeds the UPI mule-hub/ring detectors (UPI-MULE-2/3).'
    )
    COMMENT = 'Governed semantic layer for the Risk, Fraud & Regulatory Intelligence Copilot -- every metric here has a 1:1 policy citation in ../policies/*.md.';

-- ---------------------------------------------------------------------------
-- (b) Cortex Search service over the policy corpus
-- ---------------------------------------------------------------------------
-- Load ../policies/*.md into a staged table first (one row per section, same
-- chunking ../engine/retrieval.py already does by "## SECTION-ID. Title"
-- heading), then index it for semantic search.

CREATE OR REPLACE TABLE POLICY_SECTIONS (
    SECTION_ID   VARCHAR(20)  PRIMARY KEY,   -- e.g. AML-TM-2, UPI-MULE-3
    DOC_NAME     VARCHAR(100),               -- e.g. aml_transaction_monitoring
    TITLE        VARCHAR(300),
    BODY_TEXT    VARCHAR(16000)
);

-- Populate via COPY INTO from a stage holding ../policies/*.md, parsed the
-- same way PolicyIndex._load() in ../engine/retrieval.py already does
-- (split on "## SECTION-ID. Title" headings) -- omitted here since it's a
-- one-time ETL step, not a repeatable DDL statement.

CREATE OR REPLACE CORTEX SEARCH SERVICE POLICY_SEARCH_SERVICE
    ON BODY_TEXT
    ATTRIBUTES SECTION_ID, DOC_NAME, TITLE
    WAREHOUSE = COMPUTE_WH  -- replace with your warehouse
    TARGET_LAG = '1 hour'
    AS (
        SELECT SECTION_ID, DOC_NAME, TITLE, BODY_TEXT
        FROM POLICY_SECTIONS
    );

-- Usage from the Cortex Agent (see 03_cortex_agent_skills.yaml): the agent
-- calls this search service as a tool, gets back {SECTION_ID, TITLE,
-- BODY_TEXT} snippets, and must cite SECTION_ID in every answer -- the same
-- "never invent a citation" discipline PolicyIndex.search() already enforces
-- in the Python prototype.
