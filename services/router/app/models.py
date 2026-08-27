"""
Pydantic models for the Router Service API.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class ChatRequest(BaseModel):
    """Incoming chat request."""
    message: str = Field(..., description="User message")
    session_id: Optional[str] = Field(None, description="Session ID for continuing a conversation")
    agent_id: Optional[str] = Field(None, description="Target agent ID, if directly addressing an agent")


class ChatResponse(BaseModel):
    """Chat response from an agent."""
    response: str
    agent_id: str
    agent_name: str
    session_id: str


class AgentInfo(BaseModel):
    """Information about an available agent."""
    id: str
    name: str
    description: str
    is_builtin: bool = True
    is_active: bool = True
    tools: list[str] = []


class SessionInfo(BaseModel):
    """Chat session information."""
    id: str
    title: str
    agent_id: str
    created_at: str
    updated_at: str


class MessageInfo(BaseModel):
    """Chat message information."""
    id: str
    role: str
    content: str
    agent_id: Optional[str] = None
    created_at: str
