"""
Agent Builder Core Engine.
Uses Gemini to refine the agent specification and Jinja2 templates to generate code & configs.
"""

import os
import re
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from jinja2 import Environment, FileSystemLoader
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).parent / "templates"
DYNAMIC_AGENTS_DIR = Path(os.environ.get("DYNAMIC_AGENTS_DIR", "/app/dynamic_agents"))

POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
POSTGRES_USER = os.environ.get("POSTGRES_USER", "adk_user")
POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "adk_password_change_me")
POSTGRES_DB = os.environ.get("POSTGRES_DB", "adk_agent_hub")
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")


def slugify(text: str) -> str:
    """Convert text into a safe identifier slug."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_")


def to_pascal_case(text: str) -> str:
    """Convert snake_case or words into PascalCase class name."""
    words = re.split(r"[_\s-]+", text)
    return "".join(word.capitalize() for word in words if word) + "Agent"


async def get_db_connection():
    """Create a database connection."""
    return await asyncpg.connect(
        host=POSTGRES_HOST,
        port=POSTGRES_PORT,
        user=POSTGRES_USER,
        password=POSTGRES_PASSWORD,
        database=POSTGRES_DB,
    )


async def refine_system_prompt(name: str, description: str, user_prompt: str, tools: list[str]) -> str:
    """Use Gemini models to create a structured, highly capable system prompt for the new sub-agent."""
    if not GOOGLE_API_KEY:
        # Fallback if no API key is provided
        tools_str = ", ".join(tools) if tools else "general reasoning"
        return f"You are {name}, a specialized assistant. {description}\n\nInstructions:\n{user_prompt}\n\nAvailable tools: {tools_str}."

    try:
        client = genai.Client(api_key=GOOGLE_API_KEY)
        meta_prompt = f"""
You are an expert AI agent architect. Generate a comprehensive and effective system prompt for a specialized AI sub-agent.

Agent Name: {name}
Agent Description: {description}
User's Instructions: {user_prompt}
Equipped Tools: {json.dumps(tools)}

Requirements:
1. Define the persona, role, and boundaries.
2. Provide step-by-step guidelines on how to handle user queries.
3. Explicitly describe how and when to use the equipped tools ({tools}).
4. Ensure the output is only the raw system prompt text without Markdown wrapping or code fences.
"""

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(role="user", parts=[types.Part.from_text(text=meta_prompt)])],
            config=types.GenerateContentConfig(
                temperature=0.3,
                max_output_tokens=1500,
            ),
        )
        return response.text.strip() if response.text else user_prompt

    except Exception as e:
        logger.warning(f"Failed to refine system prompt with Gemini: {e}. Using raw user prompt.")
        return user_prompt


async def build_agent(name: str, description: str, prompt: str, tools: list[str]) -> dict:
    """
    Build a new sub-agent:
    1. Refine system prompt
    2. Render template code
    3. Save to disk (shared volume)
    4. Save to PostgreSQL
    """
    agent_id = slugify(name)
    class_name = to_pascal_case(agent_id)

    # 1. Refine system prompt
    system_prompt = await refine_system_prompt(name, description, prompt, tools)

    # 2. Render code template
    env = Environment(loader=FileSystemLoader(str(TEMPLATES_DIR)))
    template = env.get_template("agent_template.py.j2")
    rendered_code = template.render(
        agent_id=agent_id,
        name=name,
        description=description,
        system_prompt=system_prompt,
        class_name=class_name,
        tools_config=json.dumps(tools),
    )

    # 3. Save to dynamic agents directory
    DYNAMIC_AGENTS_DIR.mkdir(parents=True, exist_ok=True)
    agent_file_path = DYNAMIC_AGENTS_DIR / f"{agent_id}.py"
    with open(agent_file_path, "w", encoding="utf-8") as f:
        f.write(rendered_code)

    # Update agents_config.json in shared volume
    config_file = DYNAMIC_AGENTS_DIR / "agents_config.json"
    configs = []
    if config_file.exists():
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                configs = json.load(f)
        except Exception:
            configs = []

    # Remove existing if any
    configs = [c for c in configs if c.get("id") != agent_id]
    agent_entry = {
        "id": agent_id,
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "tools_config": tools,
        "file": f"{agent_id}.py",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    configs.append(agent_entry)

    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(configs, f, indent=2)

    # 4. Save/Update in PostgreSQL
    conn = await get_db_connection()
    try:
        now = datetime.now(timezone.utc)
        await conn.execute(
            """
            INSERT INTO agents (id, name, description, system_prompt, tools_config, is_active, is_builtin, created_at, updated_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                description = EXCLUDED.description,
                system_prompt = EXCLUDED.system_prompt,
                tools_config = EXCLUDED.tools_config,
                updated_at = EXCLUDED.updated_at
            """,
            agent_id,
            name,
            description,
            system_prompt,
            json.dumps(tools),
            True,
            False,
            now,
            now,
        )
    finally:
        await conn.close()

    logger.info(f"Successfully built dynamic agent: {name} (ID: {agent_id})")

    return {
        "id": agent_id,
        "name": name,
        "description": description,
        "system_prompt": system_prompt,
        "tools_config": tools,
        "is_active": True,
        "is_builtin": False,
        "created_at": agent_entry["created_at"],
    }

