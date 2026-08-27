"""
Base Sub-Agent class - Common interface for all ADK sub-agents.
Connects with MCP Tool Server for Weather, Web Search, and RAG retrieval.
"""

import os
import logging
from typing import Optional, List
import httpx

from google import genai
from google.genai import types

from app.config import settings

logger = logging.getLogger(__name__)


class BaseSubAgent:
    """Base class for all sub-agents using Google GenAI and MCP Tools."""

    def __init__(
        self,
        agent_id: str,
        name: str,
        description: str,
        system_prompt: str,
        tools_config: List[str] = None,
    ):
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.tools_config = tools_config or []

        # Initialize Gemini client
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = settings.GEMINI_MODEL
        self.mcp_url = settings.MCP_SERVER_URL.rstrip("/")

    async def chat(self, message: str, history: list[dict] = None) -> str:
        """
        Send a message to the agent and get a response.
        Executes MCP tools if appropriate tools are configured.
        """
        try:
            tool_context = await self._gather_tool_context(message)

            enhanced_prompt = self.system_prompt
            if tool_context:
                enhanced_prompt += f"\n\n--- TOOL CONTEXT ---\n{tool_context}\n--- END TOOL CONTEXT ---\nUse the tool context above to assist the user accurately."

            # Build contents from history
            contents = []
            if history:
                for msg in history:
                    role = "user" if msg["role"] == "user" else "model"
                    contents.append(
                        types.Content(
                            role=role,
                            parts=[types.Part.from_text(text=msg["content"])],
                        )
                    )

            # Add current message
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=message)],
                )
            )

            # Call Gemini
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=enhanced_prompt,
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )

            return response.text or "I apologize, I couldn't generate a response."

        except Exception as e:
            logger.error(f"Agent {self.agent_id} error: {e}", exc_info=True)
            return f"I encountered an error: {str(e)}"

    async def _gather_tool_context(self, message: str) -> str:
        """Gather context from equipped MCP tools if applicable."""
        context_parts = []

        if "rag_query" in self.tools_config:
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(
                        f"{self.mcp_url}/tools/rag",
                        json={"query": message, "n_results": 3},
                    )
                    if resp.status_code == 200:
                        rag_result = resp.json().get("result", "")
                        if rag_result:
                            context_parts.append(rag_result)
            except Exception as e:
                logger.warning(f"RAG tool call failed: {e}")

        if "web_search" in self.tools_config and not any(isinstance(self, t) for t in []):
            # Only if not already handled by specialized agent
            pass

        return "\n\n".join(context_parts)

    def get_info(self) -> dict:
        """Return agent information."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "tools": self.tools_config,
            "is_builtin": True,
            "is_active": True,
        }
