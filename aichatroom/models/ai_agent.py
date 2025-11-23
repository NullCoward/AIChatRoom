"""AI Agent model representing an AI participant in the chatroom."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


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
    model: str = "gpt-4o-mini"  # Model selection per agent
    temperature: float = 0.7  # Personality/creativity (0.0-2.0)
    is_architect: bool = False  # True for The Architect (agent 0)

    # Runtime state
    status: str = "idle"  # idle, thinking, responded
    total_tokens_used: int = 0  # Token tracking
    next_heartbeat_offset: float = 0.0  # Staggered heartbeat timing
    self_concept_json: str = ""  # JSON storage for agent's self-managed identity
    room_topic: str = ""  # Current topic for this agent's room (agent = room)
    heartbeat_interval: float = 5.0  # Dynamic interval (1-10 seconds)

    # Room settings (agent = room owner)
    room_wpm: int = 80  # Words per minute for this room

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
            'status': self.status,
            'total_tokens_used': self.total_tokens_used,
            'next_heartbeat_offset': self.next_heartbeat_offset,
            'self_concept_json': self.self_concept_json,
            'room_topic': self.room_topic,
            'heartbeat_interval': self.heartbeat_interval,
            'room_wpm': self.room_wpm
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'AIAgent':
        """Create agent from dictionary."""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.utcnow()

        return cls(
            id=data.get('id'),
            name=data.get('name', ''),
            background_prompt=data.get('background_prompt', ''),
            previous_response_id=data.get('previous_response_id', ''),
            created_at=created_at,
            agent_type=data.get('agent_type', 'persona'),
            model=data.get('model', 'gpt-4o-mini'),
            temperature=float(data.get('temperature', 0.7)),
            is_architect=bool(data.get('is_architect', False)),
            status=data.get('status', 'idle'),
            total_tokens_used=int(data.get('total_tokens_used', 0)),
            next_heartbeat_offset=float(data.get('next_heartbeat_offset', 0.0)),
            self_concept_json=data.get('self_concept_json', ''),
            room_topic=data.get('room_topic', ''),
            heartbeat_interval=float(data.get('heartbeat_interval', 5.0)),
            room_wpm=int(data.get('room_wpm', 80))
        )
