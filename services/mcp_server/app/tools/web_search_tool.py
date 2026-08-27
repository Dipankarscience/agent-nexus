"""
Web Search Tool - Uses Tavily API for live web search.
"""

import os
import logging
import httpx
from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

TAVILY_API_URL = "https://api.tavily.com/search"


async def fetch_web_search(query: str, max_results: int = 5) -> str:
    """Execute web search using Tavily API."""
    api_key = os.environ.get("TAVILY_API_KEY", "")

    if not api_key:
        return (
            "Web search is not available: TAVILY_API_KEY is not configured in .env. "
            "Please set the TAVILY_API_KEY environment variable to enable web search."
        )

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                TAVILY_API_URL,
                json={
                    "api_key": api_key,
                    "query": query,
                    "max_results": min(max_results, 10),
                    "include_answer": True,
                    "search_depth": "basic",
                },
            )
            response.raise_for_status()
            data = response.json()

            results = []
            answer = data.get("answer")
            if answer:
                results.append(f"📋 Summary: {answer}\n")

            results.append("🔍 Search Results:\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

            search_results = data.get("results", [])
            if not search_results:
                return f"No results found for: {query}"

            for i, item in enumerate(search_results, 1):
                title = item.get("title", "No title")
                url = item.get("url", "")
                snippet = item.get("content", "No description available")
                if len(snippet) > 300:
                    snippet = snippet[:300] + "..."

                results.append(
                    f"\n{i}. {title}\n"
                    f"   🔗 {url}\n"
                    f"   {snippet}"
                )

            return "\n".join(results)

    except httpx.HTTPStatusError as e:
        logger.error(f"Tavily API error: {e}")
        return f"Search error: HTTP {e.response.status_code}"
    except Exception as e:
        logger.error(f"Web search error: {e}")
        return f"Error performing web search: {str(e)}"


def register_search_tools(mcp: FastMCP):
    """Register search tool with FastMCP."""
    @mcp.tool()
    async def web_search(query: str, max_results: int = 5) -> str:
        """
        Search the web for information on any topic.

        Args:
            query: The search query string
            max_results: Maximum results to return (default: 5)
        """
        return await fetch_web_search(query, max_results)
