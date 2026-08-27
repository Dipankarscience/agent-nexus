"""
Pydantic models for the Agent Builder Service.
"""

from typing import List, Optional
from pydantic import BaseModel, Field


class BuildAgentRequest(BaseModel):
    """Request payload for building a dynamic sub-agent."""
    name: str = Field(..., description="Display name for the agent")
    description: str = Field(..., description="Short description of what the agent does")
    prompt: str = Field(..., description="Natural language instructions or role prompt for the agent")
    tools: List[str] = Field(default_factory=list, description="List of tools to equip: 'get_weather', 'web_search', 'rag_query'")


class AgentResponse(BaseModel):
    """Response model for an agent definition."""
    id: str
    name: str
    description: str
    system_prompt: str
    tools_config: List[str]
    is_active: bool = True
    is_builtin: bool = False
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

