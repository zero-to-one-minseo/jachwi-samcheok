import os

import streamlit as st

DEV = os.environ.get("APP_DEV") == "1"
if not DEV:
    st.set_option("client.showErrorDetails", "none")

st.set_page_config(page_title="자취학과 · 삼척 자취방", page_icon=":material/home_work:", layout="wide")

rooms_page = st.Page("views/rooms.py", title="시세 지도", icon=":material/map:", default=True)
contract_page = st.Page("views/contract.py", title="계약서 점검", icon=":material/fact_check:")
st.navigation([rooms_page, contract_page], position="top").run()
