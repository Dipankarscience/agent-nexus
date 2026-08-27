"""
PostgreSQL Database Layer - Chat session and message persistence.
"""

import logging
import uuid
from typing import Optional
from datetime import datetime, timezone

import asyncpg

from app.config import settings

logger = logging.getLogger(__name__)

_pool: Optional[asyncpg.Pool] = None


async def get_pool() -> asyncpg.Pool:
    """Get or create the connection pool."""
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            host=settings.POSTGRES_HOST,
            port=settings.POSTGRES_PORT,
            user=settings.POSTGRES_USER,
            password=settings.POSTGRES_PASSWORD,
            database=settings.POSTGRES_DB,
            min_size=2,
            max_size=10,
        )
    return _pool


async def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


async def create_session(agent_id: str = "router", title: str = "New Chat") -> dict:
    """Create a new chat session."""
    pool = await get_pool()
    session_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await pool.execute(
        """
        INSERT INTO sessions (id, title, agent_id, created_at, updated_at)
        VALUES ($1, $2, $3, $4, $5)
        """,
        uuid.UUID(session_id), title, agent_id, now, now,
    )

    return {
        "id": session_id,
        "title": title,
        "agent_id": agent_id,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }


async def get_session(session_id: str) -> Optional[dict]:
    """Get a session by ID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, title, agent_id, created_at, updated_at FROM sessions WHERE id = $1",
        uuid.UUID(session_id),
    )
    if row:
        return {
            "id": str(row["id"]),
            "title": row["title"],
            "agent_id": row["agent_id"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }
    return None


async def list_sessions(limit: int = 50) -> list[dict]:
    """List recent sessions."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, title, agent_id, created_at, updated_at FROM sessions ORDER BY updated_at DESC LIMIT $1",
        limit,
    )
    return [
        {
            "id": str(row["id"]),
            "title": row["title"],
            "agent_id": row["agent_id"],
            "created_at": row["created_at"].isoformat(),
            "updated_at": row["updated_at"].isoformat(),
        }
        for row in rows
    ]


async def delete_session(session_id: str) -> bool:
    """Delete a session and its messages."""
    pool = await get_pool()
    result = await pool.execute(
        "DELETE FROM sessions WHERE id = $1",
        uuid.UUID(session_id),
    )
    return result == "DELETE 1"


async def add_message(session_id: str, role: str, content: str, agent_id: Optional[str] = None) -> dict:
    """Add a message to a session."""
    pool = await get_pool()
    message_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)

    await pool.execute(
        """
        INSERT INTO messages (id, session_id, role, content, agent_id, created_at)
        VALUES ($1, $2, $3, $4, $5, $6)
        """,
        uuid.UUID(message_id), uuid.UUID(session_id), role, content, agent_id, now,
    )

    # Update session timestamp and title if first user message
    await pool.execute(
        "UPDATE sessions SET updated_at = $1 WHERE id = $2",
        now, uuid.UUID(session_id),
    )

    # Auto-set session title from first user message
    if role == "user":
        msg_count = await pool.fetchval(
            "SELECT COUNT(*) FROM messages WHERE session_id = $1 AND role = 'user'",
            uuid.UUID(session_id),
        )
        if msg_count == 1:
            title = content[:80] + "..." if len(content) > 80 else content
            await pool.execute(
                "UPDATE sessions SET title = $1 WHERE id = $2",
                title, uuid.UUID(session_id),
            )

    return {
        "id": message_id,
        "role": role,
        "content": content,
        "agent_id": agent_id,
        "created_at": now.isoformat(),
    }


async def get_messages(session_id: str, limit: int = 100) -> list[dict]:
    """Get messages for a session."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT id, role, content, agent_id, created_at
        FROM messages
        WHERE session_id = $1
        ORDER BY created_at ASC
        LIMIT $2
        """,
        uuid.UUID(session_id), limit,
    )
    return [
        {
            "id": str(row["id"]),
            "role": row["role"],
            "content": row["content"],
            "agent_id": row["agent_id"],
            "created_at": row["created_at"].isoformat(),
        }
        for row in rows
    ]


async def get_agent_from_db(agent_id: str) -> Optional[dict]:
    """Get agent info from database."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id, name, description, system_prompt, tools_config, is_active, is_builtin FROM agents WHERE id = $1",
        agent_id,
    )
    if row:
        import json
        tools = row["tools_config"]
        if isinstance(tools, str):
            tools = json.loads(tools)
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "system_prompt": row["system_prompt"],
            "tools_config": tools,
            "is_active": row["is_active"],
            "is_builtin": row["is_builtin"],
        }
    return None


async def list_agents_from_db() -> list[dict]:
    """List all active agents from database with full configurations."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, name, description, system_prompt, is_active, is_builtin, tools_config FROM agents WHERE is_active = TRUE ORDER BY is_builtin DESC, name ASC"
    )
    import json
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "system_prompt": row["system_prompt"] or "You are a helpful assistant.",
            "is_active": row["is_active"],
            "is_builtin": row["is_builtin"],
            "tools": json.loads(row["tools_config"]) if isinstance(row["tools_config"], str) else row["tools_config"],
        }
        for row in rows
    ]
