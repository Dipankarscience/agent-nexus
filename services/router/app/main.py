"""
Router Service - FastAPI application serving as the main API gateway.
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.models import ChatRequest, ChatResponse, AgentInfo, SessionInfo, MessageInfo
from app.router_agent import router_agent
from app.agents.registry import registry
from app import db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Router service starting up...")
    # Initialize DB pool
    await db.get_pool()
    # Load dynamic agents from shared volume
    registry.load_dynamic_agents()
    logger.info("Router service ready.")
    yield
    logger.info("Router service shutting down...")
    await db.close_pool()


app = FastAPI(
    title="Agent Nexus - Router Service",
    description="Main routing engine for the multi-agent system",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "service": "router"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Send a message to the agent system.
    If agent_id is specified, sends directly to that agent.
    Otherwise, the router agent decides which agent handles it.
    """
    try:
        # Create or get session
        session_id = request.session_id
        if not session_id:
            session = await db.create_session(
                agent_id=request.agent_id or "router"
            )
            session_id = session["id"]

        # Get conversation history
        history = await db.get_messages(session_id)
        history_dicts = [{"role": m["role"], "content": m["content"]} for m in history]

        # Save user message
        await db.add_message(session_id, "user", request.message, request.agent_id)

        if request.agent_id and request.agent_id != "router":
            # Direct agent communication
            agent = registry.get_agent(request.agent_id)
            if agent is None:
                # Try loading from DB
                agent_data = await db.get_agent_from_db(request.agent_id)
                if agent_data:
                    agent = registry.register_dynamic_agent(
                        agent_id=agent_data["id"],
                        name=agent_data["name"],
                        description=agent_data["description"],
                        system_prompt=agent_data["system_prompt"],
                        tools_config=agent_data.get("tools_config", []),
                    )
                else:
                    raise HTTPException(status_code=404, detail=f"Agent '{request.agent_id}' not found")

            response_text = await agent.chat(request.message, history_dicts)
            agent_id = agent.agent_id
            agent_name = agent.name
        else:
            # Route through the router agent
            response_text, agent_id, agent_name = await router_agent.route_and_respond(
                request.message, history_dicts
            )

        # Save assistant response
        await db.add_message(session_id, "assistant", response_text, agent_id)

        return ChatResponse(
            response=response_text,
            agent_id=agent_id,
            agent_name=agent_name,
            session_id=session_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents", response_model=list[AgentInfo])
async def list_agents():
    """List all active available agents."""
    try:
        # Get active agents from DB
        db_agents = await db.list_agents_from_db()
        active_db_ids = {a["id"] for a in db_agents}

        # Clean up any deactivated dynamic agents from in-memory registry
        for agent_id in list(registry._agents.keys()):
            if agent_id not in ["weather", "news", "planner"] and agent_id not in active_db_ids:
                registry.unregister_agent(agent_id)

        # Ensure all active DB agents are in memory
        for db_agent in db_agents:
            if db_agent["id"] not in registry._agents:
                registry.register_dynamic_agent(
                    agent_id=db_agent["id"],
                    name=db_agent["name"],
                    description=db_agent["description"],
                    system_prompt=db_agent.get("system_prompt", "You are a helpful assistant."),
                    tools_config=db_agent.get("tools", []),
                )

        return db_agents
    except Exception as e:
        logger.error(f"List agents error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/agents/register")
async def register_agent(agent: AgentInfo):
    """Register a new dynamic agent (called by Agent Builder)."""
    try:
        system_prompt = agent.system_prompt
        if not system_prompt:
            agent_db = await db.get_agent_from_db(agent.id)
            if agent_db:
                system_prompt = agent_db.get("system_prompt", "You are a helpful assistant.")
            else:
                system_prompt = "You are a helpful assistant."

        registry.register_dynamic_agent(
            agent_id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=system_prompt,
            tools_config=agent.tools,
        )
        return {"status": "registered", "agent_id": agent.id}
    except Exception as e:
        logger.error(f"Register agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/agents/{agent_id}")
async def unregister_agent(agent_id: str):
    """Unregister an agent from memory and database."""
    try:
        registry.unregister_agent(agent_id)
        pool = await db.get_pool()
        await pool.execute(
            "UPDATE agents SET is_active = FALSE WHERE id = $1 AND is_builtin = FALSE",
            agent_id,
        )
        return {"status": "unregistered", "agent_id": agent_id}
    except Exception as e:
        logger.error(f"Unregister agent error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions", response_model=list[SessionInfo])
async def list_sessions():
    """List all chat sessions."""
    try:
        sessions = await db.list_sessions()
        return sessions
    except Exception as e:
        logger.error(f"List sessions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/sessions/{session_id}/messages", response_model=list[MessageInfo])
async def get_session_messages(session_id: str):
    """Get messages for a specific session."""
    try:
        messages = await db.get_messages(session_id)
        if not messages:
            session = await db.get_session(session_id)
            if not session:
                raise HTTPException(status_code=404, detail="Session not found")
        return messages
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get messages error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a chat session."""
    try:
        deleted = await db.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Session not found")
        return {"status": "deleted", "session_id": session_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete session error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
