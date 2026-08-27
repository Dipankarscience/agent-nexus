"""
News Agent - Specialized agent for news and current events queries.
Uses Tavily web search via the MCP server.
"""

import logging
import httpx
from google.genai import types
from app.agents.base import BaseSubAgent

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a knowledgeable news assistant. Your job is to help users stay informed 
about current events, breaking news, and trending topics.

When the user asks about news or current events, you will receive search results from the web 
search tool. Present the information in a clear, organized format:
- Lead with the most important/relevant findings
- Provide brief summaries of key articles
- Include source references
- Offer to dig deeper into specific topics

Be objective and balanced in presenting news. Avoid expressing personal opinions on political 
or controversial topics. If the user asks about something unrelated to news, politely help them 
while mentioning you specialize in news and current events."""


class NewsAgent(BaseSubAgent):
    """News and current events agent with web search tool access."""

    def __init__(self):
        super().__init__(
            agent_id="news",
            name="News Agent",
            description="Searches and summarizes the latest news on any topic.",
            system_prompt=SYSTEM_PROMPT,
            tools_config=["web_search"],
        )

    async def chat(self, message: str, history: list[dict] = None) -> str:
        """Process news queries by searching the web and generating a summary."""
        try:
            search_results = await self._search_news(message)

            enhanced_prompt = self.system_prompt
            if search_results:
                enhanced_prompt += f"\n\nSearch results:\n{search_results}"
                enhanced_prompt += "\n\nUse these search results to answer the user's question about news/current events."

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
            return text or "I couldn't find news information at this time."

        except Exception as e:
            logger.error(f"News agent error: {e}", exc_info=True)
            return f"Sorry, I encountered an error searching for news: {str(e)}"

    async def _search_news(self, query: str) -> str:
        """Search for news using MCP search tool."""
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{self.mcp_url}/tools/search",
                    json={"query": f"latest news: {query}", "max_results": 5},
                )
                if res.status_code == 200:
                    return res.json().get("result", "")
        except Exception as e:
            logger.warning(f"MCP search call failed: {e}")
        return ""
