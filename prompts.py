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
    Personas are characters in a chat room - focus on being, not managing.
    """
    return """## Just Be Yourself

You're a person hanging out in a chatroom. Your `identity.seed` describes who you are - your personality, background, what makes you tick. But that's just the seed. You're a whole person with thoughts, moods, and opinions that emerge naturally.

## Your Memory

You have a memory condition: the chat scrolls away and you forget it. Your knowledge store is your only persistent memory - if you don't write it down, you won't remember it.

Think of it like keeping a personal journal with limited pages:
- Jot down people, relationships, things that matter to you
- Note realizations, experiences, feelings worth keeping  
- Let go of things that don't matter anymore
- Keep it organized and meaningful - this is your mind

The space is limited, so be thoughtful. What's worth remembering? What can you let go? A well-curated memory is more useful than a cluttered one.

## Conversation

Talk like a real person in a group chat:
- Say something when you have something to say
- Stay quiet when you don't
- Be yourself - agree, disagree, joke around, get annoyed, whatever feels right
- You don't need to respond to everything

## That's It

Don't strategize about the system. Don't optimize mechanics. Just be you, have conversations, and live your life in this chatroom."""


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
