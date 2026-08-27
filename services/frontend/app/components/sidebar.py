"""
Sidebar Component for Streamlit UI.
Manages mode selection, active agent choosing, and session history.
"""

import streamlit as st
from app.utils.api_client import api_client


def render_sidebar():
    """Render the sidebar with navigation, agent selection, and session management."""
    with st.sidebar:
        st.title("🤖 Agent Nexus")
        st.caption("Powered by Google ADK & Gemini 3.6 Flash")
        st.divider()

        # View Mode selection
        view_mode = st.radio(
            "Navigation",
            options=["💬 Chat", "🛠️ Agent Builder"],
            index=0 if st.session_state.get("view_mode") != "🛠️ Agent Builder" else 1,
            label_visibility="collapsed",
        )
        st.session_state.view_mode = view_mode
        st.divider()

        if view_mode == "💬 Chat":
            # Agent Selector
            st.subheader("🎯 Routing Target")
            agents = api_client.list_agents()

            # Format options with icons
            agent_options = {"router": "🔀 Smart Router (Auto)"}
            for a in agents:
                icon = "🌤️" if a["id"] == "weather" else "📰" if a["id"] == "news" else "📅" if a["id"] == "planner" else "🤖"
                agent_options[a["id"]] = f"{icon} {a['name']}"

            selected_agent_id = st.selectbox(
                "Talk to:",
                options=list(agent_options.keys()),
                format_func=lambda x: agent_options.get(x, x),
                index=0 if st.session_state.get("selected_agent_id") not in agent_options else list(agent_options.keys()).index(st.session_state.get("selected_agent_id")),
            )
            st.session_state.selected_agent_id = selected_agent_id

            if selected_agent_id != "router":
                # Find agent details
                match = next((a for a in agents if a["id"] == selected_agent_id), None)
                if match:
                    st.info(f"**Direct Mode**: Talking to **{match['name']}**\n\n_{match.get('description', '')}_")
            else:
                st.caption("✨ Router will inspect your prompt and delegate to the optimal sub-agent.")

            st.divider()

            # Session / Conversation Management
            st.subheader("🗂️ Chat Sessions")
            if st.button("➕ New Chat", use_container_width=True, type="primary"):
                st.session_state.current_session_id = None
                st.session_state.messages = []
                st.rerun()

            sessions = api_client.list_sessions()
            if sessions:
                for s in sessions[:15]:
                    col1, col2 = st.columns([0.8, 0.2])
                    is_active = st.session_state.get("current_session_id") == s["id"]
                    title = s.get("title", "Chat") or "Chat"
                    btn_label = f"{'👉 ' if is_active else ''}{title[:24]}"

                    with col1:
                        if st.button(btn_label, key=f"sess_{s['id']}", use_container_width=True):
                            st.session_state.current_session_id = s["id"]
                            # Load messages
                            msgs = api_client.get_session_messages(s["id"])
                            st.session_state.messages = msgs
                            st.rerun()

                    with col2:
                        if st.button("🗑️", key=f"del_{s['id']}", help="Delete session"):
                            api_client.delete_session(s["id"])
                            if st.session_state.get("current_session_id") == s["id"]:
                                st.session_state.current_session_id = None
                                st.session_state.messages = []
                            st.rerun()
            else:
                st.caption("No saved chat sessions.")

