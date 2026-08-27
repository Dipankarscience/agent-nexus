"""
Router Service Configuration
"""

import os


class Settings:
    """Application settings from environment variables."""

    GOOGLE_API_KEY: str = os.environ.get("GOOGLE_API_KEY", "")
    GEMINI_MODEL: str = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")
    MCP_SERVER_URL: str = os.environ.get("MCP_SERVER_URL", "http://mcp-server:8003")

    # PostgreSQL
    POSTGRES_HOST: str = os.environ.get("POSTGRES_HOST", "postgres")
    POSTGRES_PORT: int = int(os.environ.get("POSTGRES_PORT", "5432"))
    POSTGRES_USER: str = os.environ.get("POSTGRES_USER", "adk_user")
    POSTGRES_PASSWORD: str = os.environ.get("POSTGRES_PASSWORD", "adk_password_change_me")
    POSTGRES_DB: str = os.environ.get("POSTGRES_DB", "adk_agent_hub")

    # Dynamic agents directory
    DYNAMIC_AGENTS_DIR: str = os.environ.get("DYNAMIC_AGENTS_DIR", "/app/dynamic_agents")


settings = Settings()
