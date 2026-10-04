import os
import streamlit as st
from snowflake.snowpark import Session

@st.cache_resource
def _session():
    return Session.builder.config("connection_name", "cococlihack").config(
        "database", os.environ["SF_DB"]).config("schema", "CORE").config(
        "warehouse", "COMPUTE_WH").create()

_session()
_src = open(os.environ["APP_PATH"]).read()
exec(compile(_src, os.environ["APP_PATH"], "exec"), {"__name__": "__main__"})
