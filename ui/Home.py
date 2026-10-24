import os

import requests
import streamlit as st

API_URL = os.getenv("API_URL", "http://localhost:8000")

st.set_page_config(page_title="CarbonLens", page_icon="🌍")
st.title("CarbonLens")
st.caption("Placeholder page: Member 3 replaces this with the real shell (login + navigation).")

try:
    r = requests.get(f"{API_URL}/", timeout=3)
    st.success(f"API reachable: {r.json()}")
except Exception as exc:
    st.error(f"API not reachable at {API_URL}: {exc}")
