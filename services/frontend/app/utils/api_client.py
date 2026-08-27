"""
API Client for interacting with Router and Agent Builder services.
"""

import os
import logging
from typing import List, Dict, Any, Optional
import httpx

logger = logging.getLogger(__name__)

ROUTER_URL = os.environ.get("ROUTER_URL", "http://router:8000")
AGENT_BUILDER_URL = os.environ.get("AGENT_BUILDER_URL", "http://agent-builder:8002")


class APIClient:
    """Client for backend service communication."""

    def __init__(self):
        self.router_url = ROUTER_URL.rstrip("/")
        self.builder_url = AGENT_BUILDER_URL.rstrip("/")
        self.timeout = httpx.Timeout(60.0, connect=10.0)

    # ─── Router & Agent Endpoints ─────────────────────

    def list_agents(self) -> List[Dict[str, Any]]:
        """Fetch all available agents (built-in + dynamic)."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.router_url}/agents")
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.error(f"Error fetching agents: {e}")
        return []

    def send_chat(
        self,
        message: str,
        session_id: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send a user message to the router or directly to a specific agent."""
        payload = {"message": message}
        if session_id:
            payload["session_id"] = session_id
        if agent_id and agent_id != "router":
            payload["agent_id"] = agent_id

        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.router_url}/chat", json=payload)
                if res.status_code == 200:
                    return res.json()
                else:
                    return {
                        "response": f"⚠️ Server Error ({res.status_code}): {res.text}",
                        "agent_id": "system",
                        "agent_name": "System Error",
                        "session_id": session_id or "",
                    }
        except Exception as e:
            logger.error(f"Chat request failed: {e}")
            return {
                "response": f"⚠️ Network Connection Error: {str(e)}",
                "agent_id": "system",
                "agent_name": "System Error",
                "session_id": session_id or "",
            }

    # ─── Session Management ───────────────────────────

    def list_sessions(self) -> List[Dict[str, Any]]:
        """List chat sessions."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.router_url}/sessions")
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.error(f"Error fetching sessions: {e}")
        return []

    def get_session_messages(self, session_id: str) -> List[Dict[str, Any]]:
        """Fetch history messages for a session."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.router_url}/sessions/{session_id}/messages")
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.error(f"Error fetching messages for session {session_id}: {e}")
        return []

    def delete_session(self, session_id: str) -> bool:
        """Delete a chat session."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.delete(f"{self.router_url}/sessions/{session_id}")
                return res.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False

    # ─── Agent Builder Endpoints ──────────────────────

    def build_agent(
        self,
        name: str,
        description: str,
        prompt: str,
        tools: List[str],
    ) -> Dict[str, Any]:
        """Request the Agent Builder service to create a dynamic sub-agent."""
        payload = {
            "name": name,
            "description": description,
            "prompt": prompt,
            "tools": tools,
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.post(f"{self.builder_url}/build", json=payload)
                if res.status_code == 200:
                    return {"success": True, "data": res.json()}
                else:
                    return {"success": False, "error": res.text}
        except Exception as e:
            logger.error(f"Build agent error: {e}")
            return {"success": False, "error": str(e)}

    def list_custom_agents(self) -> List[Dict[str, Any]]:
        """List all custom agents from the builder service."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.get(f"{self.builder_url}/agents")
                if res.status_code == 200:
                    return res.json()
        except Exception as e:
            logger.error(f"Error listing custom agents: {e}")
        return []

    def delete_custom_agent(self, agent_id: str) -> bool:
        """Deactivate a custom agent."""
        try:
            with httpx.Client(timeout=self.timeout) as client:
                res = client.delete(f"{self.builder_url}/agents/{agent_id}")
                return res.status_code == 200
        except Exception as e:
            logger.error(f"Error deleting agent {agent_id}: {e}")
            return False


# Global API client instance
api_client = APIClient()

