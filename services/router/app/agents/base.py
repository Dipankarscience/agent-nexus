"""
Base Sub-Agent class - Common interface for all ADK sub-agents.
Connects with MCP Tool Server for Weather, Web Search, and RAG retrieval,
and handles multi-turn conversation sanitization for Gemini.
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
                enhanced_prompt += (
                    f"\n\n=== CONTEXT FROM TOOLS ===\n"
                    f"{tool_context}\n"
                    f"=== END TOOL CONTEXT ===\n"
                    f"Use the relevant tool context above to answer the user accurately."
                )

            # Build strictly sanitized contents for Gemini
            contents = self._build_sanitized_contents(message, history)

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

            # Safely extract text from response parts
            extracted_text = self._extract_response_text(response)
            if extracted_text:
                return extracted_text

            logger.warning(f"Agent {self.agent_id} received empty text. Response: {response}")
            return "I apologize, but I could not generate a complete response. Please try rephrasing your question."

        except Exception as e:
            logger.error(f"Agent {self.agent_id} generation error: {e}", exc_info=True)
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                return "⚠️ **Rate Limit Reached (429 Resource Exhausted)**: The Google Gemini API free quota has been temporarily exceeded for this key. Please wait 30–60 seconds, switch to `gemini-1.5-flash` in `.env`, or generate a fresh API key in a new Google AI Studio project."
            return f"I encountered an error while processing your request: {str(e)}"

    def _build_sanitized_contents(self, current_message: str, history: list[dict] = None) -> list:
        """Build strictly valid, alternating user/model contents for Gemini."""
        contents = []

        if history:
            cleaned_history = []
            for msg in history:
                content_str = (msg.get("content") or "").strip()
                if not content_str:
                    continue

                raw_role = msg.get("role", "user")
                genai_role = "user" if raw_role in ["user", "human"] else "model"

                # If same role as previous, merge them to preserve alternation
                if cleaned_history and cleaned_history[-1]["role"] == genai_role:
                    cleaned_history[-1]["content"] += f"\n\n{content_str}"
                else:
                    cleaned_history.append({"role": genai_role, "content": content_str})

            # Ensure history does not end with 'user' before adding current message
            if cleaned_history and cleaned_history[-1]["role"] == "user":
                cleaned_history.pop()

            for item in cleaned_history:
                contents.append(
                    types.Content(
                        role=item["role"],
                        parts=[types.Part.from_text(text=item["content"])],
                    )
                )

        # Add current user message
        contents.append(
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=current_message)],
            )
        )

        return contents

    def _extract_response_text(self, response) -> str:
        """Safely extract text across all candidate parts."""
        if not response:
            return ""

        # Try standard .text accessor
        try:
            if response.text:
                return response.text.strip()
        except Exception:
            pass

        # Fallback: scan candidate parts directly
        try:
            if getattr(response, "candidates", None):
                for candidate in response.candidates:
                    if getattr(candidate, "content", None) and getattr(candidate.content, "parts", None):
                        parts_text = [
                            p.text for p in candidate.content.parts
                            if getattr(p, "text", None)
                        ]
                        if parts_text:
                            return "\n".join(parts_text).strip()
        except Exception as e:
            logger.warning(f"Error parsing candidates: {e}")

        return ""

    async def _gather_tool_context(self, message: str) -> str:
        """Gather context from equipped MCP tools based on agent config."""
        context_parts = []

        # 1. Vector RAG tool
        if "rag_query" in self.tools_config:
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{self.mcp_url}/tools/rag",
                        json={"query": message, "n_results": 3},
                    )
                    if resp.status_code == 200:
                        rag_result = resp.json().get("result", "")
                        if rag_result:
                            context_parts.append(rag_result)
            except Exception as e:
                logger.warning(f"RAG tool call failed for {self.agent_id}: {e}")

        # 2. Web search tool
        if "web_search" in self.tools_config and self.agent_id != "news":
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{self.mcp_url}/tools/search",
                        json={"query": message, "max_results": 3},
                    )
                    if resp.status_code == 200:
                        search_result = resp.json().get("result", "")
                        if search_result:
                            context_parts.append(search_result)
            except Exception as e:
                logger.warning(f"Web search tool call failed for {self.agent_id}: {e}")

        # 3. Weather tool
        if "get_weather" in self.tools_config and self.agent_id != "weather":
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        f"{self.mcp_url}/tools/weather",
                        json={"city": message},
                    )
                    if resp.status_code == 200:
                        weather_result = resp.json().get("result", "")
                        if weather_result:
                            context_parts.append(weather_result)
            except Exception as e:
                logger.warning(f"Weather tool call failed for {self.agent_id}: {e}")

        return "\n\n".join(context_parts)

    def get_info(self) -> dict:
        """Return agent information."""
        return {
            "id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools_config,
            "is_builtin": self.agent_id in ["weather", "news", "planner"],
            "is_active": True,
        }
