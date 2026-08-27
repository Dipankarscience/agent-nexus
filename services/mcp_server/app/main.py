"""
MCP Tool Server - Main Entry Point.
Hosts Weather, Web Search, and ONNX RAG tools via FastMCP (SSE transport)
and provides HTTP REST endpoints alongside /health.
"""

import logging
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.requests import Request
import uvicorn

from app.tools.weather_tool import register_weather_tools, fetch_weather
from app.tools.web_search_tool import register_search_tools, fetch_web_search
from app.tools.rag_tool import register_rag_tools, fetch_rag_query
from app.vectorstore.loader import initialize_vectorstore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastMCP Server
mcp = FastMCP("adk-tool-server")

# Register all MCP tools
register_weather_tools(mcp)
register_search_tools(mcp)
register_rag_tools(mcp)


# ─── HTTP REST Endpoints ──────────────────────────────

async def health_check(request: Request):
    """Health check endpoint for Docker container checks."""
    return JSONResponse({"status": "healthy", "service": "mcp-tool-server"})


async def http_weather(request: Request):
    """HTTP endpoint to query weather."""
    data = await request.json() if request.method == "POST" else request.query_params
    city = data.get("city", "London")
    result = await fetch_weather(city)
    return JSONResponse({"result": result})


async def http_search(request: Request):
    """HTTP endpoint for web search."""
    data = await request.json() if request.method == "POST" else request.query_params
    query = data.get("query", "")
    max_results = int(data.get("max_results", 5))
    result = await fetch_web_search(query, max_results)
    return JSONResponse({"result": result})


async def http_rag(request: Request):
    """HTTP endpoint for vector RAG."""
    data = await request.json() if request.method == "POST" else request.query_params
    query = data.get("query", "")
    collection = data.get("collection", "medical_knowledge")
    n_results = int(data.get("n_results", 3))
    result = await fetch_rag_query(query, collection, n_results)
    return JSONResponse({"result": result})


@asynccontextmanager
async def lifespan(app):
    """Initialize ONNX vector store on startup."""
    logger.info("MCP Server starting up - Initializing ONNX vector store...")
    try:
        await initialize_vectorstore()
        logger.info("ONNX Vector store ready.")
    except Exception as e:
        logger.warning(f"Vector store initialization warning: {e}")
    yield
    logger.info("MCP Tool Server shut down.")


def create_app():
    """Create Starlette app containing FastMCP SSE app and HTTP routes."""
    # Obtain Starlette app from FastMCP for SSE endpoints
    try:
        sse_app = mcp.sse_app()
    except Exception:
        # Fallback if custom ASGI
        sse_app = None

    routes = [
        Route("/health", health_check, methods=["GET"]),
        Route("/tools/weather", http_weather, methods=["GET", "POST"]),
        Route("/tools/search", http_search, methods=["GET", "POST"]),
        Route("/tools/rag", http_rag, methods=["GET", "POST"]),
    ]

    # Combine with SSE if available
    app = Starlette(
        debug=False,
        lifespan=lifespan,
        routes=routes,
    )

    if sse_app:
        app.mount("/sse", sse_app)

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)
