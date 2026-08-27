"""
Weather Agent - Specialized agent for weather queries.
Uses MCP weather tool via the MCP server.
"""

import logging
import httpx
from app.agents.base import BaseSubAgent
from app.config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a helpful weather assistant. Your job is to provide accurate, 
friendly weather information for any location the user asks about.

When the user asks about weather, you will receive weather data from the weather tool. 
Present the information in a clear, conversational format. Include:
- Current temperature and what it feels like
- Weather conditions (sunny, cloudy, rainy, etc.)
- Humidity and wind information
- Any relevant advice (e.g., "Bring an umbrella!" for rainy conditions)

If the user asks about something unrelated to weather, politely redirect them or provide 
a brief answer while mentioning you specialize in weather information."""


class WeatherAgent(BaseSubAgent):
    """Weather information agent with MCP tool access."""

    def __init__(self):
        super().__init__(
            agent_id="weather",
            name="Weather Agent",
            description="Provides current weather information for any city worldwide.",
            system_prompt=SYSTEM_PROMPT,
            tools_config=["get_weather"],
        )

    async def chat(self, message: str, history: list[dict] = None) -> str:
        """Process weather queries by calling the MCP tool first, then generating a response."""
        try:
            city = await self._extract_city(message)

            weather_data = None
            if city:
                weather_data = await self._call_weather_tool(city)

            enhanced_prompt = self.system_prompt
            if weather_data:
                enhanced_prompt += f"\n\nCurrent weather data:\n{weather_data}"
                enhanced_prompt += "\n\nUse this data to answer the user's question."

            from google import genai
            from google.genai import types

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
                    system_instruction=enhanced_prompt,
                    temperature=0.7,
                    max_output_tokens=2048,
                ),
            )

            return response.text or "I couldn't get weather information at this time."

        except Exception as e:
            logger.error(f"Weather agent error: {e}")
            return f"Sorry, I encountered an error getting weather information: {str(e)}"

    async def _extract_city(self, message: str) -> str:
        """Use Gemini to extract city name from user message."""
        try:
            from google.genai import types

            response = await self.client.aio.models.generate_content(
                model=self.model,
                contents=[
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(
                            text=f"Extract ONLY the city name from this message. Return just the city name, nothing else. If no city is mentioned, return 'London' as default.\n\nMessage: {message}"
                        )],
                    )
                ],
                config=types.GenerateContentConfig(
                    temperature=0.0,
                    max_output_tokens=50,
                ),
            )
            return response.text.strip() if response.text else "London"
        except Exception:
            return "London"

    async def _call_weather_tool(self, city: str) -> str:
        """Call the MCP server's weather tool endpoint."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.mcp_url}/tools/weather",
                    json={"city": city},
                )
                if res.status_code == 200:
                    return res.json().get("result", "")
        except Exception as e:
            logger.warning(f"MCP weather tool call failed: {e}")
        return ""
