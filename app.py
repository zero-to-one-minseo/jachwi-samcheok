import os

import streamlit as st

DEV = os.environ.get("APP_DEV") == "1"
if not DEV:
    st.set_option("client.showErrorDetails", "none")

st.set_page_config(page_title="계약 전에 · 삼척 자취방", page_icon="🏠", layout="wide")

rooms_page = st.Page("views/rooms.py", title="삼척 자취방 시세", default=True)
contract_page = st.Page("views/contract.py", title="계약서 점검")
st.navigation([rooms_page, contract_page]).run()
