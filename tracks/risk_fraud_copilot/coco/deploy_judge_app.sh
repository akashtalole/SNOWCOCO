#!/bin/bash
# Deploys a read-only copy of the Streamlit app for judges (no status write-back).
# Streamlit-in-Snowflake runs with the owner's privileges, so judges must never get the writable app.
set -euo pipefail
SRC="$(cd "$(dirname "$0")" && pwd)"
TMP="$(mktemp -d)"
sed 's/^READ_ONLY = False/READ_ONLY = True/' "$SRC/05_streamlit_app.py" > "$TMP/05_streamlit_app.py"
grep -q '^READ_ONLY = True' "$TMP/05_streamlit_app.py"
cat > "$TMP/snowflake.yml" << 'YML'
definition_version: "2"
entities:
  risk_fraud_streamlit_app_judge:
    type: streamlit
    identifier:
      name: RISK_FRAUD_STREAMLIT_APP_JUDGE
    stage: streamlit_stage
    query_warehouse: COMPUTE_WH
    main_file: 05_streamlit_app.py
    title: "Risk, Fraud & Regulatory Intelligence Copilot (read-only judge view)"
    artifacts:
      - 05_streamlit_app.py
YML
cd "$TMP"
snow streamlit deploy -c "${SNOWFLAKE_CONNECTION:-cococlihack}" --database RISK_FRAUD_COPILOT --schema CORE --replace
rm -rf "$TMP"
