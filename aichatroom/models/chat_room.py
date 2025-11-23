"""ChatRoom and RoomMembership models.

In this architecture, each agent IS a room (agent.id = room.id).
ChatRoom is a lightweight view/DTO used when treating an agent as a room.
RoomMembership represents an agent's membership in another agent's room.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ChatRoom:
    """Lightweight view of an agent when treated as a room.

    Since agent.id = room.id, this is essentially a subset of AIAgent
    containing only room-relevant fields. Used for type distinction
    when code is operating on rooms rather than agents.

    Note: In most cases, you can work directly with AIAgent since
    each agent IS their own room.
    """

    id: Optional[int] = None
    name: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict:
        """Convert room to dictionary for database storage."""
        return {
            'id': self.id,
            'name': self.name,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ChatRoom':
        """Create room from dictionary."""
        created_at = data.get('created_at')
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.utcnow()

        return cls(
            id=data.get('id'),
            name=data.get('name', ''),
            created_at=created_at
        )


@dataclass
class RoomMembership:
    """Represents an agent's membership in a room with per-room state.

    Each agent has memberships in rooms (including their own self-room).
    attention_pct controls how much of the agent's context window is allocated to this room.
    """

    id: Optional[int] = None
    agent_id: int = 0  # The agent who is the member
    room_id: int = 0   # The room (which is also an agent's ID)
    joined_at: datetime = field(default_factory=datetime.utcnow)
    last_message_id: str = "0"  # Last message sequence number seen in this room
    status: str = "idle"  # idle, thinking, typing
    last_response_time: Optional[datetime] = None  # For WPM rate limiting
    last_response_word_count: int = 0  # For WPM calculation
    next_heartbeat_offset: float = 0.0  # Staggered timing

    # Attention allocation
    attention_pct: float = 10.0  # Percentage of context window for this room
    is_dynamic: bool = False  # True for %* (dynamic sizing)
    is_self_room: bool = False  # True if this is the agent's own room

    def to_dict(self) -> dict:
        """Convert membership to dictionary for database storage."""
        return {
            'id': self.id,
            'agent_id': self.agent_id,
            'room_id': self.room_id,
            'joined_at': self.joined_at.isoformat() if self.joined_at else None,
            'last_message_id': self.last_message_id,
            'status': self.status,
            'last_response_time': self.last_response_time.isoformat() if self.last_response_time else None,
            'last_response_word_count': self.last_response_word_count,
            'next_heartbeat_offset': self.next_heartbeat_offset,
            'attention_pct': self.attention_pct,
            'is_dynamic': self.is_dynamic,
            'is_self_room': self.is_self_room
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'RoomMembership':
        """Create membership from dictionary."""
        joined_at = data.get('joined_at')
        if isinstance(joined_at, str):
            joined_at = datetime.fromisoformat(joined_at)
        elif joined_at is None:
            joined_at = datetime.utcnow()

        last_response_time = data.get('last_response_time')
        if isinstance(last_response_time, str):
            last_response_time = datetime.fromisoformat(last_response_time)

        return cls(
            id=data.get('id'),
            agent_id=int(data.get('agent_id', 0)),
            room_id=int(data.get('room_id', 0)),
            joined_at=joined_at,
            last_message_id=data.get('last_message_id', '0'),
            status=data.get('status', 'idle'),
            last_response_time=last_response_time,
            last_response_word_count=int(data.get('last_response_word_count', 0)),
            next_heartbeat_offset=float(data.get('next_heartbeat_offset', 0.0)),
            attention_pct=float(data.get('attention_pct', 10.0)),
            is_dynamic=bool(data.get('is_dynamic', False)),
            is_self_room=bool(data.get('is_self_room', False))
        )
