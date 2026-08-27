"""
Agent Builder Service - FastAPI Application.
Handles dynamic creation, registration, and management of new sub-agents.
"""

import os
import logging
from typing import List
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx

from app.models import BuildAgentRequest, AgentResponse
from app.builder import build_agent, get_db_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ROUTER_URL = os.environ.get("ROUTER_URL", "http://router:8000")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Agent Builder Service started.")
    yield
    logger.info("Agent Builder Service stopped.")


app = FastAPI(
    title="Agent Nexus - Agent Builder",
    description="Microservice to generate and register dynamic sub-agents",
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
    return {"status": "healthy", "service": "agent-builder"}


@app.post("/build", response_model=AgentResponse)
async def build_new_agent(request: BuildAgentRequest):
    """
    Build a new dynamic sub-agent from prompt and specifications.
    Writes code to shared volume, persists to Postgres, and registers with Router.
    """
    try:
        agent_data = await build_agent(
            name=request.name,
            description=request.description,
            prompt=request.prompt,
            tools=request.tools,
        )

        # Notify router service to register agent dynamically in-memory
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"{ROUTER_URL}/agents/register",
                    json={
                        "id": agent_data["id"],
                        "name": agent_data["name"],
                        "description": agent_data["description"],
                        "system_prompt": agent_data.get("system_prompt", ""),
                        "is_builtin": False,
                        "is_active": True,
                        "tools": agent_data["tools_config"],
                    },
                )
        except Exception as e:
            logger.warning(f"Could not immediately notify router service: {e}. It will pick up from DB.")

        return AgentResponse(**agent_data)

    except Exception as e:
        logger.error(f"Error building agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/agents", response_model=List[AgentResponse])
async def list_custom_agents():
    """List all user-built custom agents from DB."""
    try:
        conn = await get_db_connection()
        try:
            rows = await conn.fetch(
                """
                SELECT id, name, description, system_prompt, tools_config, is_active, is_builtin, created_at, updated_at
                FROM agents
                WHERE is_builtin = FALSE AND is_active = TRUE
                ORDER BY created_at DESC
                """
            )
            import json
            results = []
            for r in rows:
                tools = r["tools_config"]
                if isinstance(tools, str):
                    tools = json.loads(tools)
                results.append(
                    AgentResponse(
                        id=r["id"],
                        name=r["name"],
                        description=r["description"],
                        system_prompt=r["system_prompt"],
                        tools_config=tools,
                        is_active=r["is_active"],
                        is_builtin=r["is_builtin"],
                        created_at=r["created_at"].isoformat() if r["created_at"] else None,
                        updated_at=r["updated_at"].isoformat() if r["updated_at"] else None,
                    )
                )
            return results
        finally:
            await conn.close()
    except Exception as e:
        logger.error(f"Error listing custom agents: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str):
    """Deactivate a custom agent, remove from shared volume, and unregister from Router."""
    try:
        conn = await get_db_connection()
        try:
            result = await conn.execute(
                "UPDATE agents SET is_active = FALSE WHERE id = $1 AND is_builtin = FALSE",
                agent_id,
            )
            if result == "UPDATE 0":
                raise HTTPException(status_code=404, detail=f"Custom agent '{agent_id}' not found")
        finally:
            await conn.close()

        # Update agents_config.json in shared volume
        try:
            import json
            from pathlib import Path
            dynamic_dir = Path(os.environ.get("DYNAMIC_AGENTS_DIR", "/app/dynamic_agents"))
            config_file = dynamic_dir / "agents_config.json"
            if config_file.exists():
                with open(config_file, "r", encoding="utf-8") as f:
                    configs = json.load(f)
                configs = [c for c in configs if c.get("id") != agent_id]
                with open(config_file, "w", encoding="utf-8") as f:
                    json.dump(configs, f, indent=2)
        except Exception as e:
            logger.warning(f"Error updating dynamic agent file config: {e}")

        # Notify Router service to immediately remove from memory
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.delete(f"{ROUTER_URL}/agents/{agent_id}")
        except Exception as e:
            logger.warning(f"Could not notify router service to unregister {agent_id}: {e}")

        return {"status": "deactivated", "agent_id": agent_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting agent {agent_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

