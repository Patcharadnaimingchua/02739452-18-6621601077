"""Entry point: page config, global styles and Thai-labelled navigation."""
import streamlit as st

import theme

st.set_page_config(page_title="PM2.5 ประเทศไทย", page_icon=theme.page_icon(), layout="wide")
theme.inject_css()
st.navigation([
    st.Page("dashboard.py", title="แดชบอร์ด", default=True),
    st.Page("pipeline_status.py", title="สถานะ Pipeline"),
]).run()
