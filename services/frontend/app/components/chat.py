"""
Chat View Component for Streamlit UI.
Renders conversation messages with agent attribution and handles input submission.
"""

import streamlit as st
from app.utils.api_client import api_client


def get_agent_badge_and_avatar(agent_id: str):
    """Return an appropriate avatar emoji and badge title for an agent."""
    if not agent_id:
        return "🤖", "Assistant"
    agent_id = agent_id.lower()
    if agent_id == "weather":
        return "🌤️", "Weather Agent"
    elif agent_id == "news":
        return "📰", "News Agent"
    elif agent_id == "planner":
        return "📅", "Daily Planner Agent"
    elif agent_id == "router":
        return "🔀", "Router Agent"
    else:
        return "🤖", f"Sub-Agent ({agent_id})"


def render_chat_view():
    """Render the main chat window and message stream."""
    st.header("💬 Multi-Agent Workspace")

    # Display welcome banner if conversation is empty
    if not st.session_state.messages:
        st.info(
            "👋 Welcome to **ADK Agent Hub**! Ask any question or pick a specialist.\n\n"
            "- 🌤️ **Weather**: _'What is the forecast in Tokyo this weekend?'_\n"
            "- 📰 **News**: _'Latest breakthroughs in quantum computing'_ \n"
            "- 📅 **Planner**: _'Plan my Monday schedule with workout and meetings'_\n"
            "- 🩺 **RAG / Medical**: _'What are the treatment options for type 2 diabetes?'_\n"
            "- 🛠️ **Agent Builder**: Create your own custom agent anytime using the sidebar!"
        )

    # Render previous conversation history
    for msg in st.session_state.messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        agent_id = msg.get("agent_id")

        if role == "user":
            with st.chat_message("user", avatar="🧑‍💻"):
                st.markdown(content)
        else:
            avatar, badge = get_agent_badge_and_avatar(agent_id)
            with st.chat_message("assistant", avatar=avatar):
                st.caption(f"⚡ Handled by: **{badge}**")
                st.markdown(content)

    # Chat prompt input
    if prompt := st.chat_input("Type your message here..."):
        # Display user message immediately in UI
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user", avatar="🧑‍💻"):
            st.markdown(prompt)

        # Call backend API
        selected_agent = st.session_state.get("selected_agent_id", "router")
        with st.chat_message("assistant", avatar="⏳"):
            with st.spinner("Processing through ADK agent pipeline..."):
                response_data = api_client.send_chat(
                    message=prompt,
                    session_id=st.session_state.get("current_session_id"),
                    agent_id=selected_agent,
                )

        # Update session state with response
        resp_text = response_data.get("response", "No response received.")
        resp_agent_id = response_data.get("agent_id", selected_agent)
        resp_session_id = response_data.get("session_id")

        if resp_session_id:
            st.session_state.current_session_id = resp_session_id

        st.session_state.messages.append({
            "role": "assistant",
            "content": resp_text,
            "agent_id": resp_agent_id,
        })

        st.rerun()

