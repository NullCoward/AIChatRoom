"""Chat message model representing a message in the chatroom."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class ChatMessage:
    """Represents a chat message in a chatroom."""

    id: Optional[int] = None
    room_id: int = 0  # Which room this message belongs to
    sender_id: Optional[int] = None  # Foreign key to agents.id (None for system messages)
    sender_name: str = ""  # Display name (kept for convenience, but sender_id is source of truth)
    content: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    sequence_number: int = 0

    # Additional fields
    message_type: str = "text"  # text, image, system (join/leave), starter
    image_url: Optional[str] = None  # For DALL-E generated images
    image_path: Optional[str] = None  # Local path if saved
    reply_to_id: Optional[int] = None  # ID of message being replied to

    def to_dict(self) -> dict:
        """Convert message to dictionary for database storage."""
        return {
            'id': self.id,
            'room_id': self.room_id,
            'sender_id': self.sender_id,
            'sender_name': self.sender_name,
            'content': self.content,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'sequence_number': self.sequence_number,
            'message_type': self.message_type,
            'image_url': self.image_url,
            'image_path': self.image_path,
            'reply_to_id': self.reply_to_id
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'ChatMessage':
        """Create message from dictionary."""
        timestamp = data.get('timestamp')
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            timestamp = datetime.utcnow()

        return cls(
            id=data.get('id'),
            room_id=int(data.get('room_id', 0)),
            sender_id=data.get('sender_id'),
            sender_name=data.get('sender_name', ''),
            content=data.get('content', ''),
            timestamp=timestamp,
            sequence_number=data.get('sequence_number', 0),
            message_type=data.get('message_type', 'text'),
            image_url=data.get('image_url'),
            image_path=data.get('image_path'),
            reply_to_id=data.get('reply_to_id')
        )

    @property
    def is_system_message(self) -> bool:
        """Check if this is a system message (join/leave)."""
        return self.message_type == "system"

    @property
    def is_image(self) -> bool:
        """Check if this message contains an image."""
        return self.message_type == "image"
