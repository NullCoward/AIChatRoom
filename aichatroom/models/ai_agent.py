"""AI Agent model representing an AI participant in the chatroom."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Dict


# HUD format options (for both input and output)
HUD_FORMAT_JSON = "json"           # Standard JSON with indentation
HUD_FORMAT_COMPACT = "compact_json"  # JSON with short keys, no indent
HUD_FORMAT_TOON = "toon"           # Full TOON format (experimental)

# Valid format combinations
HUD_INPUT_FORMATS = [HUD_FORMAT_JSON, HUD_FORMAT_COMPACT, HUD_FORMAT_TOON]
HUD_OUTPUT_FORMATS = [HUD_FORMAT_JSON, HUD_FORMAT_TOON]  # Compact JSON output not supported (LLM writes full keys)


@dataclass
class AIAgent:
    """Represents an AI agent with OpenAI Responses API integration.

    Each agent IS a room - agent.id = room.id (1:1 relationship).
    Agent 0 is The Architect (the app/user).
    """

    id: Optional[int] = None
    name: str = ""  # Display name (personas use custom names, bots use ID)
    background_prompt: str = ""  # Personality for personas, role for bots
    previous_response_id: str = ""  # For Responses API conversation continuity
    created_at: datetime = field(default_factory=datetime.utcnow)

    # Agent configuration
    agent_type: str = "persona"  # "persona" (human-like) or "bot" (AI assistant)
    model: str = "gpt-5-nano"  # Model selection per agent
    temperature: float = 0.7  # Personality/creativity (0.0-2.0)
    is_architect: bool = False  # True for The Architect (agent 0)
    hud_input_format: str = "json"  # Format for HUD sent TO agent: json, compact_json, toon
    hud_output_format: str = "json"  # Format agent should respond IN: json, toon

    # Runtime state
    status: str = "idle"  # idle, thinking, responded
    total_tokens_used: int = 0  # Token tracking
    next_heartbeat_offset: float = 0.0  # Staggered heartbeat timing
    self_concept_json: str = ""  # JSON storage for agent's self-managed identity
    room_billboard: str = ""  # Billboard message for this agent's room (visible to all members)
    heartbeat_interval: float = 5.0  # Dynamic interval (1-10 seconds)

    # Room settings (agent = room owner)
    room_wpm: int = 80  # Words per minute for this room

    # Permissions
    can_create_agents: bool = False  # Can this agent create other agents?

    # Sleep state
    sleep_until: Optional[datetime] = None  # If set, agent is sleeping until this time

    # Memory allocation (HUD token budget management)
    token_budget: int = 10000  # Total tokens available for this agent's HUD
    memory_allocations_json: str = ""  # JSON dict: {"knowledge": 30, "recent_actions": 10, "rooms": 60}

    def to_dict(self) -> dict:
        """Convert agent to dictionary for database storage."""
        return {
            'id': self.id,
            'name': self.name,
            'background_prompt': self.background_prompt,
            'previous_response_id': self.previous_response_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'agent_type': self.agent_type,
            'model': self.model,
            'temperature': self.temperature,
            'is_architect': self.is_architect,
            'hud_input_format': self.hud_input_format,
            'hud_output_format': self.hud_output_format,
            'status': self.status,
            'total_tokens_used': self.total_tokens_used,
            'next_heartbeat_offset': self.next_heartbeat_offset,
            'self_concept_json': self.self_concept_json,
            'room_billboard': self.room_billboard,
            'heartbeat_interval': self.heartbeat_interval,
            'room_wpm': self.room_wpm,
            'can_create_agents': self.can_create_agents,
            'sleep_until': self.sleep_until.isoformat() if self.sleep_until else None,
            'token_budget': self.token_budget,
            'memory_allocations_json': self.memory_allocations_json
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AIAgent':
        """Create agent from dictionary."""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.utcnow()

        sleep_until = data.get('sleep_until')
        if isinstance(sleep_until, str):
            sleep_until = datetime.fromisoformat(sleep_until)
        else:
            sleep_until = None

        # Handle migration from old hud_format to new split fields
        hud_input = data.get('hud_input_format') or data.get('hud_format', 'json')
        hud_output = data.get('hud_output_format', 'json')

        return cls(
            id=data.get('id'),
            name=data.get('name', ''),
            background_prompt=data.get('background_prompt', ''),
            previous_response_id=data.get('previous_response_id', ''),
            created_at=created_at,
            agent_type=data.get('agent_type', 'persona'),
            model=data.get('model', 'gpt-5-nano'),
            temperature=float(data.get('temperature', 0.7)),
            is_architect=bool(data.get('is_architect', False)),
            hud_input_format=hud_input,
            hud_output_format=hud_output,
            status=data.get('status', 'idle'),
            total_tokens_used=int(data.get('total_tokens_used', 0)),
            next_heartbeat_offset=float(data.get('next_heartbeat_offset', 0.0)),
            self_concept_json=data.get('self_concept_json', ''),
            room_billboard=data.get('room_billboard', ''),
            heartbeat_interval=float(data.get('heartbeat_interval', 5.0)),
            room_wpm=int(data.get('room_wpm', 80)),
            can_create_agents=bool(data.get('can_create_agents', False)),
            sleep_until=sleep_until,
            token_budget=int(data.get('token_budget', 10000)),
            memory_allocations_json=data.get('memory_allocations_json', '')
        )

    # Default memory allocations (percentages of allocatable memory)
    DEFAULT_MEMORY_ALLOCATIONS = {
        "knowledge": 30,       # self.knowledge store
        "recent_actions": 10,  # self.recent_actions history
        "rooms": 60            # all room messages (subdivided by per-room allocation)
    }

    def get_memory_allocations(self) -> Dict[str, int]:
        """Get memory allocations as a dict, with defaults if not set."""
        if not self.memory_allocations_json:
            return dict(self.DEFAULT_MEMORY_ALLOCATIONS)
        try:
            allocations = json.loads(self.memory_allocations_json)
            # Merge with defaults for any missing keys
            result = dict(self.DEFAULT_MEMORY_ALLOCATIONS)
            result.update(allocations)
            return result
        except json.JSONDecodeError:
            return dict(self.DEFAULT_MEMORY_ALLOCATIONS)

    def set_memory_allocation(self, path: str, percent: int) -> bool:
        """Set a memory allocation by path. Returns True if successful."""
        allocations = self.get_memory_allocations()

        # Validate the path
        valid_paths = ["knowledge", "recent_actions", "rooms"]
        # Also allow room.{id} paths for per-room allocation (stored separately in RoomMembership)
        if path not in valid_paths and not path.startswith("room."):
            return False

        # Validate percentage
        if percent < 0 or percent > 100:
            return False

        # Set the allocation
        allocations[path] = percent
        self.memory_allocations_json = json.dumps(allocations)
        return True
