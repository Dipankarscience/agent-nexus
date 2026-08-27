"""
Streamlit Frontend Main Application.
Entry point for ADK Agent Hub Web Interface.
"""

import os
import sys
from pathlib import Path

# Ensure root /app is in Python path for Streamlit script runner
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

import streamlit as st

# Set page configuration must be the first Streamlit command
st.set_page_config(
    page_title="ADK Agent Hub",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

from app.components.sidebar import render_sidebar
from app.components.chat import render_chat_view
from app.components.agent_builder_ui import render_agent_builder_view


def init_session_state():
    """Initialize necessary session state variables."""
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "current_session_id" not in st.session_state:
        st.session_state.current_session_id = None
    if "selected_agent_id" not in st.session_state:
        st.session_state.selected_agent_id = "router"
    if "view_mode" not in st.session_state:
        st.session_state.view_mode = "💬 Chat"


def main():
    """Main application loop."""
    init_session_state()

    # Render left sidebar
    render_sidebar()

    # Route content based on view mode
    if st.session_state.view_mode == "🛠️ Agent Builder":
        render_agent_builder_view()
    else:
        render_chat_view()


if __name__ == "__main__":
    main()
