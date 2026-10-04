"""05_streamlit_app.py

"Scaffold a compliance officer Streamlit dashboard with cited, explainable
outputs."

A real, deployed Streamlit-in-Snowflake app -- the Snowflake-native
counterpart to ../static/{index.html,app.js,style.css}. Same three tabs
(Ask / Signals / Findings), same "never show an answer without its
evidence and citation" principle, reading directly from the live
RISK_FRAUD_SEMANTIC_VIEW and POLICY_SEARCH_SERVICE this repo already
proved live in coco/README.md's "Live Pilot Results" section.

The Ask tab queries the same two governed tools the deployed
RISK_FRAUD_REGULATORY_COPILOT Cortex Agent uses (the semantic view and the
Cortex Search service) directly via SQL, rather than calling the agent's
REST endpoint -- a Streamlit-in-Snowflake app has no outbound network
access by default (that would need an External Access Integration wired
to the account's own REST endpoint), so this composes the same
"structured metric + policy citation" answer the agent gives, using the
identical governed sources, without that extra network hop.

Deployed via: snow streamlit deploy (see snowflake.yml in this folder).
"""
import json
import streamlit as st

from snowflake.snowpark.context import get_active_session

session = get_active_session()

# deploy_judge_app.sh flips this to True for the read-only judge copy.
READ_ONLY = False

st.set_page_config(page_title="Risk, Fraud & Regulatory Intelligence Copilot", layout="wide")
st.title("Risk, Fraud & Regulatory Intelligence Copilot")
st.caption("Snowflake-native · synthetic demo data · signal → evidence → documented finding"
           + (" · read-only judge view" if READ_ONLY else ""))

tab_ask, tab_signals, tab_findings = st.tabs(["Ask", "Signals", "Findings & Reports"])

# ---------------------------------------------------------------------------
# Ask tab — queries RISK_FRAUD_SEMANTIC_VIEW (metrics) and
# POLICY_SEARCH_SERVICE (citations) directly, the same two governed tools
# RISK_FRAUD_REGULATORY_COPILOT uses, composing a grounded answer that
# always names its metric value and policy citation together.
# ---------------------------------------------------------------------------
with tab_ask:
    st.caption(
        "Queries the same governed semantic view + Cortex Search service the deployed "
        "RISK_FRAUD_REGULATORY_COPILOT agent uses — never an invented number or citation."
    )
    question = st.text_input(
        "Ask about an account, a risk pattern, or a policy…",
        placeholder="What is our total sub-threshold cash deposit exposure?",
    )
    if question:
        with st.spinner("Querying the semantic view and policy search service…"):
            # SNOWFLAKE.CORTEX.SEARCH_PREVIEW's second argument must be a
            # literal/bound JSON string, not a computed SQL expression
            # (confirmed live: OBJECT_CONSTRUCT/TO_JSON built inline both
            # failed with "unexpected argument" -- the function requires
            # its request payload as a plain string, so it's built in
            # Python and passed as a single bind parameter here).
            search_payload = json.dumps({
                "query": question,
                "columns": ["SECTION_ID", "TITLE", "BODY_TEXT"],
                "limit": 3,
            })
            search_rows = session.sql(
                "SELECT PARSE_JSON(SNOWFLAKE.CORTEX.SEARCH_PREVIEW("
                "  'RISK_FRAUD_COPILOT.CORE.POLICY_SEARCH_SERVICE', ?"
                ")) AS RESULT",
                params=[search_payload],
            ).collect()
            search_json = json.loads(search_rows[0]["RESULT"]) if search_rows else {"results": []}

            metrics_df = session.sql(
                "SELECT * FROM SEMANTIC_VIEW("
                "  RISK_FRAUD_SEMANTIC_VIEW"
                "  METRICS sub_threshold_cash_total, high_risk_jurisdiction_wire_total, upi_total"
                "  DIMENSIONS accounts.account_id"
                ") WHERE sub_threshold_cash_total > 0 OR high_risk_jurisdiction_wire_total > 0 OR upi_total > 0"
            ).to_pandas()

        col_metric, col_policy = st.columns(2)
        with col_metric:
            st.subheader("Governed metrics (RISK_FRAUD_SEMANTIC_VIEW)")
            if len(metrics_df):
                st.dataframe(metrics_df, use_container_width=True)
            else:
                st.caption("No accounts currently exceed any of these metrics.")
        with col_policy:
            st.subheader("Policy citations (POLICY_SEARCH_SERVICE)")
            results = search_json.get("results", [])
            if results:
                for r in results:
                    with st.expander(f"{r.get('SECTION_ID', '?')} — {r.get('TITLE', '')}"):
                        st.write(r.get("BODY_TEXT", ""))
            else:
                st.caption("No policy section matched this question.")

# ---------------------------------------------------------------------------
# Signals tab — live query against the same corrected structuring-detector
# SQL documented in 04_orchestration.py / 09_scheduled_task.sql.
# ---------------------------------------------------------------------------
with tab_signals:
    st.subheader("Detected Signals — Structuring (AML-TM-2)")
    severity_filter = st.selectbox("Severity", ["All", "High", "Medium", "Low"])
    search = st.text_input("Search account, customer…", key="signals_search")

    signals_df = session.sql(
        """
        WITH deposits AS (
            SELECT txn_id, account_id, customer_id, txn_timestamp, amount
            FROM TRANSACTIONS
            WHERE type = 'cash_deposit' AND amount BETWEEN 8000 AND 9999.99
        ),
        windowed AS (
            SELECT *,
                   COUNT(*) OVER (
                       PARTITION BY account_id ORDER BY txn_timestamp
                       RANGE BETWEEN CURRENT ROW AND INTERVAL '5 days' FOLLOWING
                   ) AS window_count,
                   SUM(amount) OVER (
                       PARTITION BY account_id ORDER BY txn_timestamp
                       RANGE BETWEEN CURRENT ROW AND INTERVAL '5 days' FOLLOWING
                   ) AS window_total
            FROM deposits
        ),
        best_per_account AS (
            SELECT account_id, customer_id, window_total AS total_amount,
                   window_count AS deposit_count,
                   ROW_NUMBER() OVER (
                       PARTITION BY account_id ORDER BY window_count DESC, txn_timestamp
                   ) AS rn
            FROM windowed
            WHERE window_count >= 3
        )
        SELECT b.account_id, b.customer_id, c.name AS customer_name,
               b.deposit_count, b.total_amount, 'High' AS severity
        FROM best_per_account b
        JOIN CUSTOMERS c ON c.customer_id = b.customer_id
        WHERE rn = 1
        """
    ).to_pandas()

    if severity_filter != "All":
        signals_df = signals_df[signals_df["SEVERITY"] == severity_filter]
    if search:
        mask = (
            signals_df["ACCOUNT_ID"].str.contains(search, case=False)
            | signals_df["CUSTOMER_NAME"].str.contains(search, case=False)
        )
        signals_df = signals_df[mask]

    st.metric("Total structuring signals", len(signals_df))
    st.dataframe(signals_df, use_container_width=True)

# ---------------------------------------------------------------------------
# Findings & Reports tab — live query + status-update writeback against the
# real FINDINGS table.
# ---------------------------------------------------------------------------
with tab_findings:
    st.subheader("Findings")
    findings_df = session.sql(
        "SELECT FINDING_ID, SIGNAL_TYPE, SEVERITY, ACCOUNT_ID, CUSTOMER_NAME, "
        "NARRATIVE, RECOMMENDED_ACTION, STATUS, CITATIONS, EVIDENCE, CREATED_AT "
        "FROM FINDINGS ORDER BY CREATED_AT DESC"
    ).to_pandas()

    if len(findings_df) == 0:
        st.caption("No findings on file yet.")
    for _, row in findings_df.iterrows():
        with st.expander(f"{row['FINDING_ID']} — {row['SIGNAL_TYPE']} ({row['SEVERITY']}) — {row['STATUS']}"):
            st.write(str(row["NARRATIVE"]).replace("$", "\\$"))
            st.write(f"**Recommended action:** {row['RECOMMENDED_ACTION']}")
            st.write("**Citations:**", row["CITATIONS"])
            st.write("**Evidence transaction IDs:**", row["EVIDENCE"])
            if READ_ONLY:
                st.write(f"**Status:** {row['STATUS']}")
                continue
            new_status = st.selectbox(
                "Status",
                ["Open", "Investigating", "Resolved"],
                index=["Open", "Investigating", "Resolved"].index(row["STATUS"])
                if row["STATUS"] in ["Open", "Investigating", "Resolved"] else 0,
                key=f"status_{row['FINDING_ID']}",
            )
            if new_status != row["STATUS"]:
                if st.button("Save status", key=f"save_{row['FINDING_ID']}"):
                    session.sql(
                        "UPDATE FINDINGS SET STATUS = ? WHERE FINDING_ID = ?",
                        params=[new_status, row["FINDING_ID"]],
                    ).collect()
                    st.success(f"Updated {row['FINDING_ID']} to {new_status}")
                    st.rerun()
