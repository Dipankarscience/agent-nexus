"""
Router Agent - Main routing engine that analyzes queries and routes to the best sub-agent.
"""

import logging
from google import genai
from google.genai import types

from app.config import settings
from app.agents.registry import registry

logger = logging.getLogger(__name__)

ROUTER_SYSTEM_PROMPT = """You are a smart routing agent. Your job is to analyze the user's message 
and determine which specialized agent should handle it.

Available agents:
{agent_descriptions}

ROUTING RULES:
1. If the query is about weather, temperature, or climate → route to "weather"
2. If the query is about news, current events, or trending topics → route to "news"  
3. If the query is about planning, scheduling, tasks, or daily organization → route to "planner"
4. If the query is about medical topics, health, treatments, or diagnoses → route to "medical" (if available) or answer directly
5. For any other query → answer directly as a helpful general assistant

RESPONSE FORMAT:
You MUST respond with ONLY a JSON object in this exact format:
{{"route": "<agent_id or 'self'>", "reason": "<brief reason for routing>"}}

Examples:
- User: "What's the weather in Paris?" → {{"route": "weather", "reason": "Weather query about Paris"}}
- User: "Latest AI news" → {{"route": "news", "reason": "Requesting current news about AI"}}
- User: "Plan my day tomorrow" → {{"route": "planner", "reason": "Daily planning request"}}
- User: "What is 2+2?" → {{"route": "self", "reason": "General knowledge question"}}

IMPORTANT: Respond ONLY with the JSON object, nothing else."""


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
        # Determine the best agent
        route_result = await self._determine_route(message)
        agent_id = route_result.get("route", "self")
        reason = route_result.get("reason", "")

        logger.info(f"Routing to: {agent_id} (reason: {reason})")

        if agent_id == "self":
            # Handle directly with general Gemini response
            response = await self._direct_response(message, history)
            return response, "router", "Router Agent"

        # Get the target agent
        agent = registry.get_agent(agent_id)
        if agent is None:
            logger.warning(f"Agent '{agent_id}' not found, handling directly.")
            response = await self._direct_response(message, history)
            return response, "router", "Router Agent"

        # Delegate to the sub-agent
        response = await agent.chat(message, history)
        return response, agent.agent_id, agent.name

    async def _determine_route(self, message: str) -> dict:
        """Use Gemini to determine which agent should handle the query."""
        try:
            agent_descriptions = registry.get_agent_descriptions()
            system_prompt = ROUTER_SYSTEM_PROMPT.format(agent_descriptions=agent_descriptions)

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=message)],
                    )
                ],
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    temperature=0.0,
                    max_output_tokens=200,
                ),
            )

            text = response.text.strip() if response.text else '{"route": "self", "reason": "fallback"}'

            # Parse JSON response
            import json
            # Clean up potential markdown formatting
            if text.startswith("```"):
                text = text.split("\n", 1)[1] if "\n" in text else text
                text = text.rsplit("```", 1)[0] if "```" in text else text
                text = text.strip()

            return json.loads(text)

        except Exception as e:
            logger.error(f"Routing error: {e}")
            return {"route": "self", "reason": f"routing error: {str(e)}"}

    async def _direct_response(self, message: str, history: list[dict] = None) -> str:
        """Generate a direct response for queries that don't need a specific agent."""
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
                        "You are a helpful AI assistant. Answer the user's questions clearly and accurately. "
                        "If the user needs specialized help (weather, news, planning), suggest they can ask "
                        "about those topics and you'll route them to the right specialist."
                    ),
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )

            return response.text or "I'm sorry, I couldn't generate a response."

        except Exception as e:
            logger.error(f"Direct response error: {e}")
            return f"I encountered an error: {str(e)}"


# Global router instance
router_agent = RouterAgent()
