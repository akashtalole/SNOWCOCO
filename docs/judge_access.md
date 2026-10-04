# Judge access: Track 1 Streamlit app

A temporary, read-only login for reviewers. The password is **not** in this repository; it is
supplied separately in the submission form.

| | |
|---|---|
| App | `RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_STREAMLIT_APP_JUDGE` (read-only copy) |
| Link | <https://app.snowflake.com/ap-southeast-7.aws/yi98626/#/streamlit-apps/RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_STREAMLIT_APP_JUDGE> |
| Username | `JUDGE_ACCESS` |
| Role | `HACKATHON_JUDGE_ROLE` (default) |
| Expires | 30 days after creation (2026-10-04), i.e. about 2026-11-03 |

## What to try

1. **Ask** tab: "What is our total sub-threshold cash deposit exposure?" returns the live
   semantic-view metrics ($36,550 for the structuring account) next to Cortex Search policy citations.
2. **Signals** tab: the structuring (AML-TM-2) detector run live.
3. **Findings & Reports** tab: the filed finding with narrative, citations and evidence IDs.

## What the login can and cannot do

- Can: open the one read-only app (it queries the live semantic view, Cortex Search service and findings table on the reviewer's behalf).
- Cannot: read any table directly, change any data, or see the writable app or any other track's objects.
- The status dropdown that writes back to `FINDINGS` exists only in the owner's writable app. The judge copy is deployed with `deploy_judge_app.sh`, which sets `READ_ONLY = True`.

Verified from the account owner's side: the judge user logs in, `SELECT` and `UPDATE` on `FINDINGS` are denied, other databases are not visible, and `SHOW STREAMLITS` lists only the judge app. Not verified: the Snowsight browser login itself (the build sandbox cannot trust Snowflake's certificate chain), so the owner should open the link once in a normal browser before submitting. If Snowsight asks for multi-factor enrollment, that is an account-level setting.

## Owner: rotate or revoke

```sql
ALTER USER JUDGE_ACCESS SET PASSWORD = '<new password>';
-- or remove everything:
DROP USER IF EXISTS JUDGE_ACCESS;
DROP ROLE IF EXISTS HACKATHON_JUDGE_ROLE;
DROP STREAMLIT IF EXISTS RISK_FRAUD_COPILOT.CORE.RISK_FRAUD_STREAMLIT_APP_JUDGE;
```

Redeploy the judge copy after app changes: `tracks/risk_fraud_copilot/coco/deploy_judge_app.sh`.
