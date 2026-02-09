"""
Standalone Terms of Service page.

This page is accessible at /Terms_of_Service without authentication,
suitable for Paddle approval and direct linking.
"""
import streamlit as st
import sys
import os

# Add parent directory to path to import from src
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.legal_ui import TERMS_OF_SERVICE_CONTENT

# Page configuration - must be first Streamlit command
st.set_page_config(
    page_title="Terms of Service - ChessAnalyzerV1",
    page_icon="📜",
    layout="centered",
)

# Render the page
st.title("Terms of Service")
st.markdown(TERMS_OF_SERVICE_CONTENT)

# Footer with link back to main app
st.markdown("---")
st.markdown("[← Back to ChessAnalyzerV1](/)")
