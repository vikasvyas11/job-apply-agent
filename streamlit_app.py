"""Streamlit entry point: sets the theme, draws the sidebar, and runs the chosen page.

Run with `start.bat` / `./start.sh`, or `python -m streamlit run streamlit_app.py`.
The pages themselves live in app_pages/.
"""
import streamlit as st

from job_apply_agent import config, ui

st.set_page_config(
    page_title="Job Application Agent", page_icon=":material/edit_document:", layout="wide",
)
config.ensure_content_files()
ui.apply_theme()

applications = st.Page("app_pages/applications.py", title="Applications", icon=":material/description:", default=True)
setup = st.Page("app_pages/setup.py", title="Setup", icon=":material/tune:")
page = st.navigation([applications, setup], position="hidden")

with st.sidebar:
    ui.sidebar_brand()
    st.page_link(applications)
    st.page_link(setup)
    ui.sidebar_status(ui.current_checks())

page.run()
