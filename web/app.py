"""Entry point: sidebar navigation between the dashboard and the pipeline status page."""
import streamlit as st

import theme

st.set_page_config(page_title="PM2.5 ประเทศไทย", page_icon=theme.page_icon(), layout="wide")
theme.inject_css()
pages = st.navigation([
    st.Page("dashboard.py", title="แดชบอร์ด", default=True),
    st.Page("pipeline_status.py", title="สถานะ Pipeline"),
])
pages.run()
