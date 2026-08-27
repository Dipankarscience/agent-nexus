"""
Router Agent - Main routing engine that analyzes queries and routes to the best sub-agent.
Includes resilient fallback routing in case of API rate limits (429 RESOURCE_EXHAUSTED).
"""

import logging
import json
import re
from google import genai
from google.genai import types

from app.config import settings
from app.agents.registry import registry
from app import db

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """You are an intelligent routing engine for a multi-agent system.
Your job is to analyze the user's message and select the single best specialist agent to handle it.

LIST OF REGISTERED SPECIALIST AGENTS:
{agent_descriptions}

DECISION INSTRUCTIONS:
1. Carefully compare the user's query against the capabilities and specialties of the listed agents above.
2. If the user's request matches the specialty of any listed agent, select that agent's EXACT "Agent ID".
3. If the user's query is a simple greeting, generic conversation, general knowledge/trivia not matching any specialist, or unclear, select "self".
4. You MUST use the exact string from "Agent ID" (for example: "weather", "news", "planner", or the exact custom agent ID string). Do not abbreviate or modify the ID.

RESPONSE FORMAT:
You MUST respond with ONLY a valid JSON object:
{{"route": "<exact_agent_id or 'self'>", "reason": "<brief explanation>"}}

IMPORTANT: Return ONLY valid JSON with no markdown fences or extra text."""


class RouterAgent:
    """Main routing agent that delegates to specialized sub-agents."""

    def __init__(self):
        self.client = genai.Client(api_key=settings.GOOGLE_API_KEY)
        self.model = settings.GEMINI_MODEL

    async def route_and_respond(self, message: str, history: list[dict] = None) -> tuple[str, str, str]:
        """
        Route a message to the appropriate agent and get a response.

        Returns:
            Tuple of (response_text, agent_id, agent_name)
        """
        # Ensure registry is in sync with latest DB state
        await registry.sync_with_db()

        # Determine the best agent (with LLM or fallback heuristics)
        route_result = await self._determine_route(message)
        agent_id = route_result.get("route", "self")
        reason = route_result.get("reason", "")

        logger.info(f"Routing evaluation: Target='{agent_id}', Reason='{reason}'")

        if agent_id == "self":
            response = await self._direct_response(message, history)
            return response, "router", "Router Agent"

        # Resolve agent from registry with fuzzy fallback
        agent = self._resolve_agent(agent_id)
        if agent is None:
            # Try DB fallback
            agent_data = await db.get_agent_from_db(agent_id)
            if agent_data and agent_data.get("is_active"):
                agent = registry.register_dynamic_agent(
                    agent_id=agent_data["id"],
                    name=agent_data["name"],
                    description=agent_data["description"],
                    system_prompt=agent_data.get("system_prompt", "You are a helpful assistant."),
                    tools_config=agent_data.get("tools_config", []),
                )

        if agent is None:
            logger.warning(f"Target agent '{agent_id}' could not be resolved. Handling directly as Router.")
            response = await self._direct_response(message, history)
            return response, "router", "Router Agent"

        logger.info(f"Delegating query to sub-agent: {agent.name} ({agent.agent_id})")
        response = await agent.chat(message, history)
        return response, agent.agent_id, agent.name

    def _resolve_agent(self, agent_id: str):
        """Find agent by exact ID or fuzzy key match."""
        if not agent_id or agent_id == "self":
            return None

        # 1. Exact match
        agent = registry.get_agent(agent_id)
        if agent:
            return agent

        # 2. Case-insensitive / slug match
        target = agent_id.lower().replace("-", "_").strip()
        for k, v in registry._agents.items():
            if k.lower() == target:
                return v

        # 3. Substring match
        for k, v in registry._agents.items():
            if target in k.lower() or k.lower() in target:
                return v

        return None

    async def _determine_route(self, message: str) -> dict:
        """Use Gemini with JSON mode, or fallback to heuristics if rate-limited."""
        try:
            agent_descriptions = registry.get_agent_descriptions()
            system_prompt = ROUTER_SYSTEM_PROMPT.format(agent_descriptions=agent_descriptions)

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=f"User Message: {message}")],
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.0,
                    max_output_tokens=1024,
                    response_mime_type="application/json",
                ),
            )

            text = response.text.strip() if response.text else '{"route": "self", "reason": "fallback"}'

            # Clean potential markdown fences
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text
                text = text.rsplit("```", 1)[0] if "```" in text else text
                text = text.strip()

            # Attempt 1: direct JSON parse
            try:
                return json.loads(text)
            except Exception:
                pass

            # Attempt 2: regex extract route field
            match = re.search(r'["\']route["\']\s*:\s*["\']([^"\']+)["\']', text)
            if match:
                return {"route": match.group(1), "reason": "regex extracted"}

            # Attempt 3: match against registered agent IDs
            for agent_id in registry._agents.keys():
                if agent_id.lower() in text.lower():
                    return {"route": agent_id, "reason": "matched from text"}

        except Exception as e:
            logger.warning(f"LLM routing failed ({e}). Attempting keyword heuristic fallback.")

        # Heuristic / Keyword fallback routing (handles 429 rate limit gracefully)
        return self._heuristic_route(message)

    def _heuristic_route(self, message: str) -> dict:
        """Fallback rule-based routing when LLM API is rate-limited or unreachable."""
        msg_lower = message.lower()

        # 1. Weather keywords
        if any(w in msg_lower for w in ["weather", "temperature", "forecast", "rain", "sunny", "humidity", "wind", "celsius"]):
            if "weather" in registry._agents:
                return {"route": "weather", "reason": "heuristic: weather keyword match"}

        # 2. News keywords
        if any(w in msg_lower for w in ["news", "latest", "headline", "breakthrough", "current events", "article"]):
            if "news" in registry._agents:
                return {"route": "news", "reason": "heuristic: news keyword match"}

        # 3. Planner keywords
        if any(w in msg_lower for w in ["plan", "schedule", "routine", "calendar", "task list", "todo", "time block"]):
            if "planner" in registry._agents:
                return {"route": "planner", "reason": "heuristic: planner keyword match"}

        # 4. Check dynamic custom agents
        for agent_id, agent in registry._agents.items():
            if agent_id in ["weather", "news", "planner"]:
                continue

            # Build keyword bank from name and description
            words = (
                agent.name.lower().split()
                + agent.description.lower().replace(",", " ").replace(".", " ").split()
                + agent_id.split("_")
            )
            keywords = [w for w in words if len(w) > 3 and w not in ["agent", "with", "from", "that", "this", "help", "your"]]
            for kw in set(keywords):
                if kw in msg_lower:
                    return {"route": agent_id, "reason": f"heuristic: dynamic agent keyword '{kw}'"}

        return {"route": "self", "reason": "heuristic default fallback"}

    async def _direct_response(self, message: str, history: list[dict] = None) -> str:
        """Generate a direct general response."""
        try:
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

            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=message)],
                )
            )

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=(
                        "You are a helpful AI assistant and general router. Answer the user's questions clearly and accurately."
                    ),
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )

            return response.text or "I'm sorry, I couldn't generate a response."

        except Exception as e:
            logger.error(f"Direct response error: {e}")
            if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                return "⚠️ **Rate Limit Reached (429 Resource Exhausted)**: Google Gemini API quota has been temporarily exceeded for this key. Please wait a minute, switch to `gemini-1.5-flash` in `.env`, or generate a new API key in Google AI Studio."
            return f"I encountered an error: {str(e)}"


# Global router instance
router_agent = RouterAgent()
