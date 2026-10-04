-- ============================================================================
-- 01_synthetic_data.sql
-- "Generate synthetic, referentially consistent transaction + account
--  datasets -- no production data needed."
--
-- Snowflake DDL + synthetic population for the same schema shape as
-- ../seed_data.py's CSVs (customers / accounts / transactions), so a
-- signal detected here is directly comparable to one from the Python
-- prototype. Uses Snowflake's GENERATOR table function and RANDOM()/
-- UNIFORM() for the synthetic rows -- no production data is read or
-- required. Run with a role that can CREATE DATABASE/SCHEMA/TABLE.
-- ============================================================================

CREATE DATABASE IF NOT EXISTS RISK_FRAUD_COPILOT;
CREATE SCHEMA IF NOT EXISTS RISK_FRAUD_COPILOT.CORE;
USE SCHEMA RISK_FRAUD_COPILOT.CORE;

-- ---------------------------------------------------------------------------
-- Tables (same fields as customers.csv / accounts.csv / transactions.csv)
-- ---------------------------------------------------------------------------

CREATE OR REPLACE TABLE CUSTOMERS (
    CUSTOMER_ID             VARCHAR(20)  PRIMARY KEY,
    NAME                    VARCHAR(200),
    TYPE                    VARCHAR(20),   -- individual | business
    RISK_RATING             VARCHAR(10),   -- Low | Medium | High
    COUNTRY                 VARCHAR(5),
    OCCUPATION_OR_INDUSTRY  VARCHAR(100),
    ONBOARDING_DATE         DATE
);

CREATE OR REPLACE TABLE ACCOUNTS (
    ACCOUNT_ID    VARCHAR(20)  PRIMARY KEY,
    CUSTOMER_ID   VARCHAR(20)  REFERENCES CUSTOMERS(CUSTOMER_ID),
    ACCOUNT_TYPE  VARCHAR(20),
    OPENED_DATE   DATE,
    STATUS        VARCHAR(20),
    CURRENCY      VARCHAR(5),
    VPA           VARCHAR(100)   -- UPI Virtual Payment Address, if any
);

CREATE OR REPLACE TABLE TRANSACTIONS (
    TXN_ID                VARCHAR(20)  PRIMARY KEY,
    ACCOUNT_ID            VARCHAR(20)  REFERENCES ACCOUNTS(ACCOUNT_ID),
    CUSTOMER_ID           VARCHAR(20)  REFERENCES CUSTOMERS(CUSTOMER_ID),
    TXN_TIMESTAMP         TIMESTAMP_NTZ,
    AMOUNT                NUMBER(18,2),
    CURRENCY              VARCHAR(5),
    TYPE                  VARCHAR(30),   -- cash_deposit, wire_in, wire_out, upi_in, upi_out, ...
    COUNTERPARTY_NAME     VARCHAR(200),
    COUNTERPARTY_COUNTRY  VARCHAR(5),
    CHANNEL               VARCHAR(20),
    LOCATION              VARCHAR(50),
    DESCRIPTION           VARCHAR(500)
);

-- Findings table: the Snowflake-side counterpart to findings_store.json,
-- one row per generated Finding (see 04_orchestration.py).
CREATE OR REPLACE TABLE FINDINGS (
    FINDING_ID          VARCHAR(20)  PRIMARY KEY,
    SIGNAL_ID           VARCHAR(100),
    SIGNAL_TYPE         VARCHAR(50),
    SEVERITY            VARCHAR(10),
    ACCOUNT_ID          VARCHAR(20),
    CUSTOMER_ID         VARCHAR(20),
    CUSTOMER_NAME       VARCHAR(200),
    CREATED_AT          TIMESTAMP_NTZ,
    NARRATIVE           VARCHAR(4000),
    RECOMMENDED_ACTION  VARCHAR(2000),
    STATUS              VARCHAR(20) DEFAULT 'Open',
    EVIDENCE            VARIANT,      -- array of evidence txn objects
    CITATIONS           VARIANT,      -- array of {section_id, title, snippet}
    HISTORY             VARIANT,      -- array of {event, at, detail}
    NOTES               VARIANT       -- array of {note, author, at}
);

-- ---------------------------------------------------------------------------
-- Synthetic population (deterministic-ish via SEED, referentially consistent:
-- every transaction's ACCOUNT_ID/CUSTOMER_ID always exists in the parent
-- tables because we generate top-down: customers -> accounts -> transactions)
-- ---------------------------------------------------------------------------

-- 25 synthetic customers
INSERT INTO CUSTOMERS
SELECT
    'CUST-' || LPAD((1000 + SEQ4())::STRING, 4, '0')                       AS CUSTOMER_ID,
    'Synthetic Customer ' || (SEQ4() + 1)::STRING                          AS NAME,
    IFF(UNIFORM(0, 9, RANDOM()) < 7, 'individual', 'business')             AS TYPE,
    ARRAY_CONSTRUCT('Low', 'Low', 'Low', 'Medium', 'High')[UNIFORM(0, 4, RANDOM())] AS RISK_RATING,
    ARRAY_CONSTRUCT('US', 'UK', 'DE', 'SG', 'IN', 'CA', 'AU', 'JP')[UNIFORM(0, 7, RANDOM())] AS COUNTRY,
    ARRAY_CONSTRUCT('Software Engineer', 'Teacher', 'Consultant', 'Retail Manager',
                    'Import/Export', 'Logistics')[UNIFORM(0, 5, RANDOM())] AS OCCUPATION_OR_INDUSTRY,
    DATEADD(day, -UNIFORM(200, 1800, RANDOM()), CURRENT_DATE())            AS ONBOARDING_DATE
FROM TABLE(GENERATOR(ROWCOUNT => 25));

-- One account per customer
INSERT INTO ACCOUNTS
SELECT
    'ACC-' || LPAD((2000 + SEQ4())::STRING, 4, '0')          AS ACCOUNT_ID,
    c.CUSTOMER_ID,
    'checking'                                               AS ACCOUNT_TYPE,
    DATEADD(day, -UNIFORM(200, 1500, RANDOM()), CURRENT_DATE()) AS OPENED_DATE,
    'active'                                                 AS STATUS,
    'USD'                                                     AS CURRENCY,
    NULL                                                      AS VPA
FROM CUSTOMERS c
QUALIFY ROW_NUMBER() OVER (ORDER BY c.CUSTOMER_ID) = ROW_NUMBER() OVER (ORDER BY c.CUSTOMER_ID);

-- ~40 everyday transactions per account (noise), plus the analyst can layer
-- hand-crafted fraud patterns on top the same way ../seed_data.py does --
-- see the commented block below for one worked example (structuring).
INSERT INTO TRANSACTIONS
SELECT
    'TXN-' || LPAD((100000 + ROW_NUMBER() OVER (ORDER BY a.ACCOUNT_ID, g.SEQ))::STRING, 6, '0') AS TXN_ID,
    a.ACCOUNT_ID,
    a.CUSTOMER_ID,
    DATEADD(day, -UNIFORM(1, 220, RANDOM()), CURRENT_TIMESTAMP())          AS TXN_TIMESTAMP,
    ROUND(UNIFORM(8, 4500, RANDOM()) + UNIFORM(0, 99, RANDOM()) / 100.0, 2) AS AMOUNT,
    'USD'                                                                  AS CURRENCY,
    ARRAY_CONSTRUCT('pos_purchase', 'ach_in', 'ach_out', 'atm_withdrawal',
                     'wire_in')[UNIFORM(0, 4, RANDOM())]                   AS TYPE,
    'Everyday Counterparty ' || UNIFORM(1, 50, RANDOM())::STRING           AS COUNTERPARTY_NAME,
    'US'                                                                  AS COUNTERPARTY_COUNTRY,
    'pos'                                                                  AS CHANNEL,
    ''                                                                     AS LOCATION,
    'Synthetic noise transaction'                                         AS DESCRIPTION
FROM ACCOUNTS a
CROSS JOIN (SELECT SEQ4() AS SEQ FROM TABLE(GENERATOR(ROWCOUNT => 40))) g;

-- Example hand-crafted pattern (mirrors ACC-1001's structuring pattern in
-- ../seed_data.py): 4 cash deposits just under the $10,000 CTR threshold,
-- within 5 days, on one specific account. Uncomment and point ACCOUNT_ID_HERE
-- at a real account_id from this run to seed the same demo pattern here.
--
-- INSERT INTO TRANSACTIONS VALUES
--   ('TXN-STRUCT-1', '<ACCOUNT_ID_HERE>', '<CUSTOMER_ID_HERE>',
--    DATEADD(day, -6, CURRENT_TIMESTAMP()), 9200, 'USD', 'cash_deposit',
--    'Teller Branch 4', 'US', 'branch', '', 'Cash deposit'),
--   ('TXN-STRUCT-2', '<ACCOUNT_ID_HERE>', '<CUSTOMER_ID_HERE>',
--    DATEADD(day, -5, CURRENT_TIMESTAMP()), 8600, 'USD', 'cash_deposit',
--    'Teller Branch 4', 'US', 'branch', '', 'Cash deposit'),
--   ('TXN-STRUCT-3', '<ACCOUNT_ID_HERE>', '<CUSTOMER_ID_HERE>',
--    DATEADD(day, -3, CURRENT_TIMESTAMP()), 9800, 'USD', 'cash_deposit',
--    'Teller Branch 4', 'US', 'branch', '', 'Cash deposit'),
--   ('TXN-STRUCT-4', '<ACCOUNT_ID_HERE>', '<CUSTOMER_ID_HERE>',
--    DATEADD(day, -2, CURRENT_TIMESTAMP()), 8950, 'USD', 'cash_deposit',
--    'Teller Branch 4', 'US', 'branch', '', 'Cash deposit');
