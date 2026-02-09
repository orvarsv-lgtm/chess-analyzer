"""
Standalone Refund Policy page.

This page is accessible at /Refund_Policy without authentication.
"""
import streamlit as st
import sys
import os

# Add parent directory to path to import from src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.legal_ui import REFUND_POLICY_CONTENT

# Page configuration - must be first Streamlit command
st.set_page_config(
    page_title="Refund Policy - ChessAnalyzerV1",
    page_icon="💸",
    layout="centered",
)

# Render the page
st.title("Refund Policy")
st.markdown(REFUND_POLICY_CONTENT)

# Footer with link back to main app
st.markdown("---")
st.markdown("[← Back to ChessAnalyzerV1](/)")
