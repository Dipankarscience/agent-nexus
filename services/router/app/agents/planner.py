"""
Daily Planner Agent - Helps users plan their day with weather-aware suggestions.
"""

import logging
import httpx
from google.genai import types
from app.agents.base import BaseSubAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a smart daily planning assistant. Help users organize their day effectively.

Your capabilities:
- Create daily schedules and task lists
- Prioritize tasks (urgent/important matrix)
- Suggest optimal time blocks for different activities
- Provide weather-aware planning suggestions (when weather data is available)
- Give productivity tips and time management advice

When helping with planning:
1. Ask clarifying questions if the user's request is vague
2. Consider weather conditions for outdoor activities
3. Suggest breaks and buffer time between tasks
4. Group similar tasks together for efficiency
5. Consider energy levels throughout the day (complex tasks in morning, routine in afternoon)

Format plans clearly with times, tasks, and priorities. Use emojis for visual clarity."""


class PlannerAgent(BaseSubAgent):
    """Daily planner agent with weather-aware scheduling."""

    def __init__(self):
        super().__init__(
            agent_id="planner",
            name="Daily Planner Agent",
            description="Helps plan your day with tasks, schedules, and weather-aware suggestions.",
            system_prompt=SYSTEM_PROMPT,
            tools_config=["get_weather", "web_search"],
        )

    async def chat(self, message: str, history: list[dict] = None) -> str:
        """Process planning queries with optional weather context."""
        try:
            weather_context = ""
            if any(word in message.lower() for word in ["outdoor", "outside", "weather", "walk", "run", "park", "garden", "commute"]):
                city = await self._extract_city(message)
                if city:
                    weather_context = await self._get_weather(city)

            enhanced_prompt = self.system_prompt
            if weather_context:
                enhanced_prompt += f"\n\nCurrent weather conditions:\n{weather_context}"
                enhanced_prompt += "\n\nConsider this weather data when making outdoor activity suggestions."

            contents = self._build_sanitized_contents(message, history)

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=enhanced_prompt,
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )

            text = self._extract_response_text(response)
            return text or "I couldn't generate a plan at this time."

        except Exception as e:
            logger.error(f"Planner agent error: {e}", exc_info=True)
            return f"Sorry, I encountered an error with planning: {str(e)}"

    async def _extract_city(self, message: str) -> str:
        """Extract city name from message using Gemini."""
        try:
            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(
                            text=f"Extract ONLY the city name from this message. If no specific city is mentioned, return 'NONE'. Return just the city name.\n\nMessage: {message}"
                        )],
                    )
                ],
                config=types.GenerateContentConfig(temperature=0.0, max_output_tokens=50),
            )
            result = response.text.strip() if response.text else "NONE"
            return None if result == "NONE" else result
        except Exception:
            return None

    async def _get_weather(self, city: str) -> str:
        """Fetch weather data for planning context from MCP server."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                res = await client.post(
                    f"{self.mcp_url}/tools/weather",
                    json={"city": city},
                )
                if res.status_code == 200:
                    return res.json().get("result", "")
        except Exception:
            pass
        return ""
