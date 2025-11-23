"""Room service for managing chatrooms and memberships.

In this architecture:
- Each agent IS a room (agent.id = room.id)
- Agent 0 is The Architect (the app/user)
- Room 0 is The Architect's room (main UI view)
- Agents are "User" in their own room, identified by ID elsewhere
"""

from datetime import datetime
from typing import List, Optional, Callable
from models import ChatRoom, RoomMembership, AIAgent, ChatMessage
from .database_service import DatabaseService
from .logging_config import get_logger
import config

logger = get_logger("room")


class RoomService:
    """Manages chatroom operations and agent memberships.

    This is the primary service for room and agent management. In this architecture:
    - Each agent IS a room (agent.id = room.id)
    - Agent 0 is The Architect (the app/user)
    - Agents communicate via the HeartbeatService polling system
    """

    def __init__(self, database: DatabaseService):
        """Initialize room service."""
        self._database = database
        self._on_room_changed: List[Callable[[], None]] = []
        self._on_membership_changed: List[Callable[[int], None]] = []  # room_id
        self._on_messages_changed: List[Callable[[], None]] = []
        self._on_agent_status_changed: List[Callable[[AIAgent], None]] = []

        # Ensure The Architect exists
        self._ensure_architect()

        # Ensure all agents have self-room memberships (migration)
        self._ensure_self_room_memberships()

    def add_messages_changed_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback for when messages change."""
        self._on_messages_changed.append(callback)

    def add_agent_status_callback(self, callback: Callable[[AIAgent], None]) -> None:
        """Add a callback for when agent status changes."""
        self._on_agent_status_changed.append(callback)

    def notify_messages_changed(self) -> None:
        """Notify all callbacks that messages have changed."""
        for callback in self._on_messages_changed:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in messages changed callback: {e}")

    def notify_agent_status_changed(self, agent: AIAgent) -> None:
        """Notify all callbacks that agent status changed."""
        for callback in self._on_agent_status_changed:
            try:
                callback(agent)
            except Exception as e:
                logger.error(f"Error in agent status callback: {e}")

    def add_room_changed_callback(self, callback: Callable[[], None]) -> None:
        """Add callback for when rooms list changes."""
        self._on_room_changed.append(callback)

    def add_membership_changed_callback(self, callback: Callable[[int], None]) -> None:
        """Add callback for when room membership changes."""
        self._on_membership_changed.append(callback)

    def _notify_room_changed(self) -> None:
        """Notify room changed callbacks."""
        for callback in self._on_room_changed:
            try:
                callback()
            except Exception as e:
                logger.error(f"Error in room changed callback: {e}")

    def _notify_membership_changed(self, room_id: int) -> None:
        """Notify membership changed callbacks."""
        for callback in self._on_membership_changed:
            try:
                callback(room_id)
            except Exception as e:
                logger.error(f"Error in membership changed callback: {e}")

    def _ensure_architect(self) -> None:
        """Ensure The Architect agent exists (creates on first run)."""
        architect = self._database.get_architect()
        if not architect:
            # Create The Architect
            architect = AIAgent(
                name="The Architect",
                background_prompt="You are The Architect, the creator and overseer of this system.",
                is_architect=True,
                model="",  # Architect doesn't use a model
                created_at=datetime.utcnow()
            )
            self._database.save_agent(architect)
            logger.info(f"Created The Architect with ID {architect.id}")

            # The Architect's room is their agent ID
            # No need to create separate room - agent.id = room.id

    def _ensure_self_room_memberships(self) -> None:
        """Ensure all agents have self-room memberships (migration for existing data)."""
        agents = self._database.get_all_agents()
        for agent in agents:
            # Check if agent has self-room membership
            membership = self._database.get_membership(agent.id, agent.id)
            if not membership:
                # Create missing self-room membership
                membership = RoomMembership(
                    agent_id=agent.id,
                    room_id=agent.id,
                    joined_at=datetime.utcnow(),
                    attention_pct=100.0,
                    is_self_room=True
                )
                self._database.save_membership(membership)
                logger.info(f"Created missing self-room membership for agent {agent.id}")

    def get_architect(self) -> AIAgent:
        """Get The Architect agent."""
        architect = self._database.get_architect()
        if not architect:
            self._ensure_architect()
            architect = self._database.get_architect()
        return architect

    def get_architect_room_id(self) -> int:
        """Get The Architect's room ID (main UI view)."""
        return self.get_architect().id

    # Room operations (rooms are agents)
    def get_all_rooms(self) -> List[ChatRoom]:
        """Get all rooms (which are agents)."""
        # Return agents as rooms
        agents = self._database.get_all_agents()
        rooms = []
        for agent in agents:
            room = ChatRoom(
                id=agent.id,
                name=f"{agent.id}" if not agent.is_architect else "The Architect",
                created_at=agent.created_at
            )
            rooms.append(room)
        return rooms

    def get_room(self, room_id: int) -> Optional[ChatRoom]:
        """Get a room by ID (which is an agent ID)."""
        agent = self._database.get_agent(room_id)
        if agent:
            return ChatRoom(
                id=agent.id,
                name=f"{agent.id}" if not agent.is_architect else "The Architect",
                created_at=agent.created_at
            )
        return None

    def create_agent(self, name: str, background_prompt: str, in_room_id: int = None,
                     model: str = "gpt-4o-mini", temperature: float = 0.7,
                     agent_type: str = "persona") -> AIAgent:
        """Create a new AI agent, optionally in a specific room.

        Args:
            name: Agent's display name (bots default to their ID)
            background_prompt: Agent's personality (persona) or role (bot)
            in_room_id: Optional room to join (if None, agent only has self-room)
            model: OpenAI model to use
            temperature: Creativity setting
            agent_type: "persona" for human-like or "bot" for AI assistant

        The agent gets:
        - Self-room membership (100% attention if solo, 50% if joining a room)
        - Optionally: Membership in specified room (50% attention)
        """
        # Verify target room exists if specified
        if in_room_id is not None:
            target_room = self._database.get_agent(in_room_id)
            if not target_room:
                raise ValueError(f"Room {in_room_id} does not exist")

        # Create the agent
        agent = AIAgent(
            name=name,
            background_prompt=background_prompt,
            agent_type=agent_type,
            model=model,
            temperature=temperature,
            created_at=datetime.utcnow()
        )
        self._database.save_agent(agent)

        if in_room_id is not None:
            logger.info(f"Created agent '{name}' with ID {agent.id} in room {in_room_id}")
        else:
            logger.info(f"Created agent '{name}' with ID {agent.id} (self-room only)")

        # Create self-room membership (agent in their own room)
        self_attention = 50.0 if in_room_id is not None else 100.0
        self_membership = RoomMembership(
            agent_id=agent.id,
            room_id=agent.id,  # Their room IS their ID
            joined_at=datetime.utcnow(),
            attention_pct=self_attention,
            is_self_room=True
        )
        self._database.save_membership(self_membership)

        # Join the specified room if provided
        if in_room_id is not None:
            room_membership = RoomMembership(
                agent_id=agent.id,
                room_id=in_room_id,
                joined_at=datetime.utcnow(),
                attention_pct=50.0,
                is_self_room=False
            )
            self._database.save_membership(room_membership)
            self._add_system_message(in_room_id, f"Agent {agent.id} has joined")
            self._notify_membership_changed(in_room_id)

        self._notify_room_changed()
        return agent

    def delete_room(self, room_id: int) -> bool:
        """Delete a room (which is an agent)."""
        # Don't allow deleting The Architect
        agent = self._database.get_agent(room_id)
        if agent and agent.is_architect:
            logger.warning("Cannot delete The Architect")
            return False

        # Delete all memberships for this agent
        memberships = self._database.get_agent_memberships(room_id)
        for m in memberships:
            self._database.delete_membership(room_id, m.room_id)

        # Delete memberships OF this room
        room_members = self._database.get_room_members(room_id)
        for m in room_members:
            self._database.delete_membership(m.agent_id, room_id)

        success = self._database.delete_agent(room_id)
        if success:
            self._notify_room_changed()
        return success

    # Membership operations
    def get_room_members(self, room_id: int) -> List[RoomMembership]:
        """Get all memberships for a room."""
        return self._database.get_room_members(room_id)

    def get_agents_in_room(self, room_id: int) -> List[AIAgent]:
        """Get all agents currently in a room."""
        memberships = self._database.get_room_members(room_id)
        agents = []
        for membership in memberships:
            agent = self._database.get_agent(membership.agent_id)
            if agent:
                agents.append(agent)
        return agents

    def get_agent_rooms(self, agent_id: int) -> List[ChatRoom]:
        """Get all rooms an agent is in."""
        memberships = self._database.get_agent_memberships(agent_id)
        rooms = []
        for membership in memberships:
            room = self._database.get_room(membership.room_id)
            if room:
                rooms.append(room)
        return rooms

    def join_room(self, agent: AIAgent, room_id: int) -> RoomMembership:
        """Add an agent to a room."""
        # Check if already in room
        existing = self._database.get_membership(agent.id, room_id)
        if existing:
            logger.warning(f"Agent '{agent.name}' already in room {room_id}")
            return existing

        # Get current members for staggered timing
        members = self._database.get_room_members(room_id)
        offset = len(members) * 1.5

        # Get current last message in room
        messages = self._database.get_messages_for_room(room_id)
        last_msg_id = str(messages[-1].sequence_number) if messages else "0"

        # Create membership
        is_self = agent.id == room_id
        membership = RoomMembership(
            agent_id=agent.id,
            room_id=room_id,
            joined_at=datetime.utcnow(),
            last_message_id=last_msg_id,
            status="idle",
            next_heartbeat_offset=offset,
            is_self_room=is_self,
            attention_pct=100.0 if is_self else 10.0
        )
        self._database.save_membership(membership)

        # Add join message
        self._add_system_message(room_id, f"{agent.name} has joined the room")

        logger.info(f"Agent '{agent.name}' joined room {room_id}")
        self._notify_membership_changed(room_id)
        return membership

    def leave_room(self, agent_id: int, room_id: int) -> bool:
        """Remove an agent from a room.

        If the agent has no remaining memberships (besides self-room),
        they are automatically deleted.
        """
        # Can't leave your own self-room
        if agent_id == room_id:
            logger.warning(f"Agent {agent_id} cannot leave their own room")
            return False

        agent = self._database.get_agent(agent_id)
        if not agent:
            return False

        # Can't remove The Architect
        if agent.is_architect:
            logger.warning("Cannot remove The Architect from rooms")
            return False

        success = self._database.delete_membership(agent_id, room_id)

        if success:
            self._add_system_message(room_id, f"Agent {agent_id} has left")
            logger.info(f"Agent {agent_id} left room {room_id}")
            self._notify_membership_changed(room_id)

        return success

    def get_membership(self, agent_id: int, room_id: int) -> Optional[RoomMembership]:
        """Get a specific membership."""
        return self._database.get_membership(agent_id, room_id)

    def update_membership(self, membership: RoomMembership) -> None:
        """Update a membership."""
        self._database.save_membership(membership)


    def update_member_status(self, agent_id: int, room_id: int, status: str) -> None:
        """Update a member's status in a room."""
        membership = self._database.get_membership(agent_id, room_id)
        if membership:
            membership.status = status
            self._database.save_membership(membership)
            self._notify_membership_changed(room_id)

    # Message operations
    def get_room_messages(self, room_id: int) -> List[ChatMessage]:
        """Get all messages for a room."""
        return self._database.get_messages_for_room(room_id)

    def get_room_messages_since(self, room_id: int, sequence_number: int) -> List[ChatMessage]:
        """Get messages after a sequence number."""
        return self._database.get_messages_for_room_since(room_id, sequence_number)

    def send_message(self, room_id: int, sender_name: str, content: str,
                     message_type: str = "text") -> ChatMessage:
        """Send a message to a room."""
        seq_num = self._database.get_next_sequence_number()
        message = ChatMessage(
            room_id=room_id,
            sender_name=sender_name,
            content=content,
            timestamp=datetime.utcnow(),
            sequence_number=seq_num,
            message_type=message_type
        )
        self._database.save_message(message)
        logger.info(f"Message in room {room_id} from '{sender_name}'")
        return message

    def _add_system_message(self, room_id: int, content: str) -> None:
        """Add a system message to a room."""
        self.send_message(room_id, "System", content, "system")

    def clear_room_messages(self, room_id: int) -> None:
        """Clear all messages in a room."""
        self._database.clear_room_messages(room_id)

        # Reset member last_message_ids
        members = self._database.get_room_members(room_id)
        for membership in members:
            membership.last_message_id = "0"
            self._database.save_membership(membership)

        logger.info(f"Cleared messages for room {room_id}")
