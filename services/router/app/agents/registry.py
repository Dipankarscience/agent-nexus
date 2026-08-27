"""
Agent Registry - Central registry for all agents (built-in + dynamic).
"""

import os
import sys
import json
import logging
import importlib.util
from typing import Optional

from app.agents.base import BaseSubAgent
from app.agents.weather import WeatherAgent
from app.agents.news import NewsAgent
from app.agents.planner import PlannerAgent
from app.config import settings

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Central registry managing all available agents."""

    def __init__(self):
        self._agents: dict[str, BaseSubAgent] = {}
        self._register_builtin_agents()

    def _register_builtin_agents(self):
        """Register all built-in agents."""
        builtin_agents = [
            WeatherAgent(),
            NewsAgent(),
            PlannerAgent(),
        ]
        for agent in builtin_agents:
            self._agents[agent.agent_id] = agent
            logger.info(f"Registered built-in agent: {agent.name} ({agent.agent_id})")

    def get_agent(self, agent_id: str) -> Optional[BaseSubAgent]:
        """Get an agent by ID."""
        return self._agents.get(agent_id)

    def list_agents(self) -> list[dict]:
        """List all registered agents."""
        return [agent.get_info() for agent in self._agents.values()]

    def register_dynamic_agent(self, agent_id: str, name: str, description: str,
                                system_prompt: str, tools_config: list[str] = None) -> BaseSubAgent:
        """Register a dynamically created agent."""
        agent = BaseSubAgent(
            agent_id=agent_id,
            name=name,
            description=description,
            system_prompt=system_prompt,
            tools_config=tools_config or [],
        )
        self._agents[agent_id] = agent
        logger.info(f"Registered dynamic agent: {name} ({agent_id})")
        return agent

    def unregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the registry."""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")
            return True
        return False

    def load_dynamic_agents(self):
        """Load dynamic agents from the shared volume directory."""
        agents_dir = settings.DYNAMIC_AGENTS_DIR
        if not os.path.exists(agents_dir):
            os.makedirs(agents_dir, exist_ok=True)
            return

        config_file = os.path.join(agents_dir, "agents_config.json")
        if not os.path.exists(config_file):
            return

        try:
            with open(config_file, "r") as f:
                configs = json.load(f)

            for config in configs:
                agent_id = config.get("id")
                if agent_id and agent_id not in self._agents:
                    self.register_dynamic_agent(
                        agent_id=agent_id,
                        name=config.get("name", agent_id),
                        description=config.get("description", ""),
                        system_prompt=config.get("system_prompt", "You are a helpful assistant."),
                        tools_config=config.get("tools_config", []),
                    )
            logger.info(f"Loaded {len(configs)} dynamic agent configs.")
        except Exception as e:
            logger.warning(f"Error loading dynamic agents: {e}")

    def get_agent_descriptions(self) -> str:
        """Get a formatted string of all agent descriptions for the router."""
        descriptions = []
        for agent_id, agent in self._agents.items():
            descriptions.append(
                f"- **{agent.name}** (id: {agent_id}): {agent.description}"
            )
        return "\n".join(descriptions)


# Global registry instance
registry = AgentRegistry()
