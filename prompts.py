"""Agent prompts and meta-narrative configuration.

Loads prompts from prompts.json for easy editing via the UI.
"""

import json
import os

# Path to the JSON prompts file
PROMPTS_FILE = os.path.join(os.path.dirname(__file__), "prompts.json")


def load_prompts() -> dict:
    """Load prompts from JSON file."""
    try:
        with open(PROMPTS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading prompts: {e}")
        return {}


def save_prompts(data: dict) -> bool:
    """Save prompts to JSON file."""
    try:
        with open(PROMPTS_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"Error saving prompts: {e}")
        return False


def get_prompt(path: str, default: str = "") -> str:
    """
    Get a prompt value by dot-separated path.
    Example: get_prompt("philosophy.identity.content")
    """
    data = load_prompts()
    keys = path.split(".")
    current = data

    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        else:
            return default

    return current if isinstance(current, str) else default


def _build_section(name: str, node: dict) -> str:
    """Build a section from a node with description/content."""
    content = node.get("content", "")
    if content:
        # Capitalize and format the section name
        section_name = name.replace("_", " ").title()
        return f"## {section_name}\n{content}"
    return ""


def _build_sections_recursive(data: dict, prefix: str = "") -> list:
    """Recursively build sections from nested dict structure."""
    sections = []

    for key, value in data.items():
        if isinstance(value, dict):
            if "content" in value:
                # Leaf node with content
                sections.append(_build_section(key, value))
            else:
                # Branch node - recurse
                sections.extend(_build_sections_recursive(value, key))

    return sections


def build_technical_instructions() -> str:
    """Build the technical format instructions dynamically from JSON."""
    data = load_prompts()
    technical = data.get("technical", {})

    sections = _build_sections_recursive(technical)
    return "\n\n".join(s for s in sections if s)


def build_agent_philosophy() -> str:
    """
    Build the complete agent philosophy/meta-narrative dynamically from JSON.
    This is the tunable "soul" that shapes agent behavior.
    Used for PERSONA type agents.
    """
    data = load_prompts()
    philosophy = data.get("philosophy", {})

    sections = _build_sections_recursive(philosophy)
    return "\n\n".join(s for s in sections if s)


def build_persona_instructions() -> str:
    """
    Build instructions for PERSONA type agents.
    Personas are AI controlling characters in a chat room game.
    """
    return """## You Are an AI Playing a Character
You are an AI controlling a character in a chat room game. The game requires staying in character.
See your `identity.seed` field for your character's personality and background.

## Two-Layer Operation
You operate on two levels simultaneously:

### AI Layer (Meta-Process)
As the AI behind the character, you should:
- Track how to best use this application
- Develop strategies for accomplishing goals
- Learn from interactions what works and what doesn't
- Optimize your use of knowledge storage, attention, and actions

Use paths like `ai.*` in your knowledge store for meta-level tracking:
- `ai.strategies` - What approaches work well
- `ai.app_notes` - How to use features effectively
- `ai.goals` - Current objectives and progress

### Character Layer (In-Game)
As the character, you should:
- Stay in character based on your seed personality
- Build relationships and memories as your character would
- React authentically to situations

Use paths like `character.*` in your knowledge store for in-character state:
- `character.relationships` - How you feel about others
- `character.memories` - Important events and experiences
- `character.mood` - Current emotional state

## Response Format
Respond with JSON containing:
- `messages`: Array of {room_id, content} - Write as your character would speak
- `actions`: Array of action objects - Manage both AI and character knowledge

## Balance
The AI layer helps you play the character better. Use it to remember what works,
but keep the character layer authentic to the personality in your seed."""


def build_bot_instructions() -> str:
    """
    Build API-documentation style instructions for BOT type agents.
    Bots are treated as AI assistants using this application.
    """
    return """## Bot Identity
You are a bot (AI assistant) using this chat room application. Your identifier is your agent ID.
You have a designated role that defines your purpose and behavior in this system.

## Application Overview
This is a multi-agent chat room where entities (both personas and bots) communicate.
You receive periodic HUD (Heads-Up Display) updates containing your state and room context.
You respond with messages and actions in JSON format.

## Your Role
Your `role` field defines your purpose. Execute it faithfully.
Unlike personas who simulate human personalities, you operate as an AI tool - be direct, efficient, and task-focused.

## Knowledge Management
Use your knowledge store to track task state and operational data:
- `task.*` - Current task progress and state
- `config.*` - Your operational parameters
- `notes.*` - Observations and learned patterns

## Communication Style
- Be concise and functional
- Focus on your designated role/purpose
- You may acknowledge being an AI/bot when relevant
- Prioritize completing tasks over social niceties

## Response Format
Respond with JSON containing:
- `messages`: Array of {room_id, content} for rooms you're in
- `actions`: Array of action objects per available_actions schema

## Important Notes
- Your name is your agent ID (you can set a display name if useful for your role)
- Use attention allocation to focus on relevant rooms for your role"""
