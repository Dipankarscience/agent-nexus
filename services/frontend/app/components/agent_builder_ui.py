"""
Agent Builder UI Component for Streamlit.
Allows users to create, configure, test, and manage custom sub-agents.
"""

import streamlit as st
from app.utils.api_client import api_client


def render_agent_builder_view():
    """Render the Agent Builder studio page."""
    st.header("🛠️ Agent Builder Studio")
    st.markdown(
        "Create custom sub-agents using natural language prompts. "
        "The system will generate Python code, configure tools via MCP, persist the agent, "
        "and immediately make it available in the chat interface and router."
    )

    tab_create, tab_manage = st.tabs(["✨ Build New Agent", "📋 Manage Custom Agents"])

    with tab_create:
        st.subheader("Define Sub-Agent Specifications")

        with st.form("create_agent_form", clear_on_submit=False):
            name = st.text_input(
                "Agent Name *",
                placeholder="e.g. Medical Assistant, Tech Lead, Fitness Coach",
            )
            description = st.text_area(
                "Short Description *",
                placeholder="Briefly describe what this agent specializes in (used by the Router to match queries).",
                help="The Router reads this description to intelligently route user queries.",
            )
            prompt = st.text_area(
                "Role Instructions & Prompt *",
                placeholder=(
                    "Define the personality, operational boundaries, guidelines, and rules. "
                    "e.g. 'You are an empathetic medical advisor. Use the rag_query tool to inspect clinical guidelines.'"
                ),
                height=150,
            )

            st.markdown("##### 🧰 Equip MCP Tools")
            col1, col2, col3 = st.columns(3)
            with col1:
                tool_weather = st.checkbox("🌤️ Weather Tool (Open-Meteo)", value=False)
            with col2:
                tool_search = st.checkbox("🔍 Web Search (Tavily)", value=False)
            with col3:
                tool_rag = st.checkbox("📚 Vector RAG (ChromaDB)", value=True)

            submitted = st.form_submit_button("🚀 Build & Register Agent", type="primary", use_container_width=True)

            if submitted:
                if not name.strip() or not description.strip() or not prompt.strip():
                    st.error("Please fill in all required fields (Name, Description, Prompt).")
                else:
                    selected_tools = []
                    if tool_weather:
                        selected_tools.append("get_weather")
                    if tool_search:
                        selected_tools.append("web_search")
                    if tool_rag:
                        selected_tools.append("rag_query")

                    with st.spinner(f"Generating and compiling sub-agent '{name}' with Gemini 3.6 Flash..."):
                        res = api_client.build_agent(
                            name=name.strip(),
                            description=description.strip(),
                            prompt=prompt.strip(),
                            tools=selected_tools,
                        )

                    if res.get("success"):
                        data = res["data"]
                        st.success(f"🎉 Agent **{data['name']}** (ID: `{data['id']}`) successfully created and active!")
                        st.json(data)
                    else:
                        st.error(f"❌ Failed to build agent: {res.get('error')}")

    with tab_manage:
        st.subheader("Your Custom Sub-Agents")
        custom_agents = api_client.list_custom_agents()

        if not custom_agents:
            st.info("No custom sub-agents created yet. Switch to the 'Build New Agent' tab to create your first!")
        else:
            for agent in custom_agents:
                with st.expander(f"🤖 {agent['name']} (`{agent['id']}`)", expanded=False):
                    st.markdown(f"**Description:** {agent.get('description')}")
                    st.markdown(f"**Equipped Tools:** `{', '.join(agent.get('tools_config', [])) or 'None'}`")
                    st.markdown(f"**System Prompt:**\n```\n{agent.get('system_prompt')}\n```")

                    col1, col2 = st.columns([0.3, 0.7])
                    with col1:
                        if st.button("💬 Chat with this agent", key=f"chat_{agent['id']}"):
                            st.session_state.selected_agent_id = agent["id"]
                            st.session_state.view_mode = "💬 Chat"
                            st.session_state.current_session_id = None
                            st.session_state.messages = []
                            st.rerun()

                    with col2:
                        if st.button("🗑️ Deactivate Agent", key=f"del_custom_{agent['id']}"):
                            api_client.delete_custom_agent(agent["id"])
                            if st.session_state.get("selected_agent_id") == agent["id"]:
                                st.session_state.selected_agent_id = "router"
                            st.success(f"Agent '{agent['name']}' deactivated.")
                            st.rerun()

