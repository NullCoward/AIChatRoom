"""Database service for SQLite operations."""

import sqlite3
import json
import os
from typing import List, Optional
from models import AIAgent, ChatMessage, ChatRoom, RoomMembership
from .logging_config import get_logger

logger = get_logger("database")


class DatabaseService:
    """Handles all SQLite database operations for persistent storage.

    Manages the following entities:
    - **Agents**: AI agents and The Architect (human user)
    - **Messages**: Chat messages in rooms
    - **Room Memberships**: Agent membership in rooms (agent.id = room.id)
    - **Room Keys**: Access control keys for private rooms
    - **Access Requests**: Pending requests to join rooms
    - **Reactions**: Message reactions (thumbs_up, thumbs_down, brain, heart)

    The database uses SQLite with automatic schema migrations. New columns
    are added automatically when the application starts.

    Usage:
        db = DatabaseService("aichatroom.db")
        agent = db.get_agent(1)
        messages = db.get_messages_for_room(room_id)
    """

    def __init__(self, db_path: str = "aichatroom.db"):
        """Initialize database service with given path."""
        self.db_path = db_path
        self._initialize_database()
        logger.info(f"Database initialized at {db_path}")

    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _initialize_database(self) -> None:
        """Create database tables if they don't exist."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            # Create agents table - each agent IS a room (agent.id = room.id)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS agents (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    background_prompt TEXT NOT NULL,
                    previous_response_id TEXT DEFAULT '',
                    created_at TEXT NOT NULL,
                    model TEXT DEFAULT 'gpt-4o-mini',
                    temperature REAL DEFAULT 0.7,
                    is_architect INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'idle',
                    total_tokens_used INTEGER DEFAULT 0,
                    next_heartbeat_offset REAL DEFAULT 0.0,
                    self_concept_json TEXT DEFAULT ''
                )
            ''')

            # Create messages table with new fields
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sender_name TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    sequence_number INTEGER NOT NULL,
                    message_type TEXT DEFAULT 'text',
                    image_url TEXT,
                    image_path TEXT
                )
            ''')

            # Create settings table for app config
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
            ''')

            # Create rooms table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS rooms (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            ''')

            # Create room_members junction table with attention allocation
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS room_members (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL,
                    room_id INTEGER NOT NULL,
                    joined_at TEXT NOT NULL,
                    last_message_id TEXT DEFAULT '0',
                    status TEXT DEFAULT 'idle',
                    last_response_time TEXT,
                    last_response_word_count INTEGER DEFAULT 0,
                    next_heartbeat_offset REAL DEFAULT 0.0,
                    attention_pct REAL DEFAULT 10.0,
                    is_dynamic INTEGER DEFAULT 0,
                    is_self_room INTEGER DEFAULT 0,
                    FOREIGN KEY (agent_id) REFERENCES agents(id) ON DELETE CASCADE,
                    FOREIGN KEY (room_id) REFERENCES agents(id) ON DELETE CASCADE,
                    UNIQUE(agent_id, room_id)
                )
            ''')

            # Create room_keys table for access control
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS room_keys (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    room_id INTEGER NOT NULL,
                    key_value TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    revoked INTEGER DEFAULT 0,
                    FOREIGN KEY (room_id) REFERENCES agents(id) ON DELETE CASCADE
                )
            ''')

            # Create access_requests table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS access_requests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requester_id INTEGER NOT NULL,
                    room_id INTEGER NOT NULL,
                    key_value TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (requester_id) REFERENCES agents(id) ON DELETE CASCADE,
                    FOREIGN KEY (room_id) REFERENCES agents(id) ON DELETE CASCADE
                )
            ''')

            # Create message_reactions table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS message_reactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id INTEGER NOT NULL,
                    reactor_id INTEGER NOT NULL,
                    reaction_type TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (message_id) REFERENCES messages(id) ON DELETE CASCADE,
                    FOREIGN KEY (reactor_id) REFERENCES agents(id) ON DELETE CASCADE,
                    UNIQUE(message_id, reactor_id, reaction_type)
                )
            ''')

            conn.commit()

            # Migrate existing tables if needed
            self._migrate_tables(conn)

    def _migrate_tables(self, conn: sqlite3.Connection) -> None:
        """Add new columns to existing tables if they don't exist."""
        cursor = conn.cursor()

        # Check and add new agent columns
        cursor.execute("PRAGMA table_info(agents)")
        agent_columns = {row[1] for row in cursor.fetchall()}

        new_agent_columns = [
            ("model", "TEXT DEFAULT 'gpt-4o-mini'"),
            ("temperature", "REAL DEFAULT 0.7"),
            ("status", "TEXT DEFAULT 'idle'"),
            ("total_tokens_used", "INTEGER DEFAULT 0"),
            ("next_heartbeat_offset", "REAL DEFAULT 0.0"),
            ("previous_response_id", "TEXT DEFAULT ''"),
            ("self_concept_json", "TEXT DEFAULT ''"),
            ("is_architect", "INTEGER DEFAULT 0"),
            ("room_billboard", "TEXT DEFAULT ''"),
            ("heartbeat_interval", "REAL DEFAULT 5.0"),
            ("room_wpm", "INTEGER DEFAULT 80"),
            ("agent_type", "TEXT DEFAULT 'persona'"),
            ("can_create_agents", "INTEGER DEFAULT 0"),
            ("sleep_until", "TEXT DEFAULT NULL"),
            ("hud_format", "TEXT DEFAULT 'json'"),  # Legacy - migrated to split fields
            ("hud_input_format", "TEXT DEFAULT 'json'"),
            ("hud_output_format", "TEXT DEFAULT 'json'"),
            ("token_budget", "INTEGER DEFAULT 10000"),
            ("memory_allocations_json", "TEXT DEFAULT ''")
        ]

        for col_name, col_def in new_agent_columns:
            if col_name not in agent_columns:
                cursor.execute(f"ALTER TABLE agents ADD COLUMN {col_name} {col_def}")
                logger.info(f"Added column {col_name} to agents table")

        # Check and add new room_members columns
        cursor.execute("PRAGMA table_info(room_members)")
        member_columns = {row[1] for row in cursor.fetchall()}

        new_member_columns = [
            ("attention_pct", "REAL DEFAULT 10.0"),
            ("is_dynamic", "INTEGER DEFAULT 0"),
            ("is_self_room", "INTEGER DEFAULT 0")
        ]

        for col_name, col_def in new_member_columns:
            if col_name not in member_columns:
                cursor.execute(f"ALTER TABLE room_members ADD COLUMN {col_name} {col_def}")
                logger.info(f"Added column {col_name} to room_members table")

        # Check and add new message columns
        cursor.execute("PRAGMA table_info(messages)")
        message_columns = {row[1] for row in cursor.fetchall()}

        new_message_columns = [
            ("message_type", "TEXT DEFAULT 'text'"),
            ("image_url", "TEXT"),
            ("image_path", "TEXT"),
            ("room_id", "INTEGER DEFAULT 0"),
            ("reply_to_id", "INTEGER DEFAULT NULL")
        ]

        for col_name, col_def in new_message_columns:
            if col_name not in message_columns:
                cursor.execute(f"ALTER TABLE messages ADD COLUMN {col_name} {col_def}")
                logger.info(f"Added column {col_name} to messages table")

        conn.commit()

    # Agent operations
    def get_all_agents(self) -> List[AIAgent]:
        """Get all agents from database."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM agents ORDER BY created_at')
            rows = cursor.fetchall()
            agents = [AIAgent.from_dict(dict(row)) for row in rows]
            logger.debug(f"Retrieved {len(agents)} agents")
            return agents

    def get_agent(self, agent_id: int) -> Optional[AIAgent]:
        """Get a specific agent by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM agents WHERE id = ?', (agent_id,))
            row = cursor.fetchone()
            return AIAgent.from_dict(dict(row)) if row else None

    def save_agent(self, agent: AIAgent) -> int:
        """Save or update an agent. Returns the agent ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if agent.id is None:
                # Insert new agent
                cursor.execute('''
                    INSERT INTO agents (name, background_prompt, previous_response_id,
                                       created_at, agent_type, model, temperature, is_architect,
                                       hud_input_format, hud_output_format,
                                       status, total_tokens_used, next_heartbeat_offset,
                                       self_concept_json, room_billboard, heartbeat_interval,
                                       room_wpm, can_create_agents, sleep_until,
                                       token_budget, memory_allocations_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    agent.name,
                    agent.background_prompt,
                    agent.previous_response_id,
                    agent.created_at.isoformat() if agent.created_at else None,
                    agent.agent_type,
                    agent.model,
                    agent.temperature,
                    int(agent.is_architect),
                    agent.hud_input_format,
                    agent.hud_output_format,
                    agent.status,
                    agent.total_tokens_used,
                    agent.next_heartbeat_offset,
                    agent.self_concept_json,
                    agent.room_billboard,
                    agent.heartbeat_interval,
                    agent.room_wpm,
                    int(agent.can_create_agents),
                    agent.sleep_until.isoformat() if agent.sleep_until else None,
                    agent.token_budget,
                    agent.memory_allocations_json
                ))
                agent.id = cursor.lastrowid
                logger.info(f"Created {agent.agent_type} '{agent.name}' with ID {agent.id}")
            else:
                # Update existing agent
                cursor.execute('''
                    UPDATE agents SET name = ?, background_prompt = ?,
                                     previous_response_id = ?, agent_type = ?,
                                     model = ?, temperature = ?, is_architect = ?,
                                     hud_input_format = ?, hud_output_format = ?,
                                     status = ?, total_tokens_used = ?,
                                     next_heartbeat_offset = ?, self_concept_json = ?,
                                     room_billboard = ?, heartbeat_interval = ?,
                                     room_wpm = ?, can_create_agents = ?, sleep_until = ?,
                                     token_budget = ?, memory_allocations_json = ?
                    WHERE id = ?
                ''', (
                    agent.name,
                    agent.background_prompt,
                    agent.previous_response_id,
                    agent.agent_type,
                    agent.model,
                    agent.temperature,
                    int(agent.is_architect),
                    agent.hud_input_format,
                    agent.hud_output_format,
                    agent.status,
                    agent.total_tokens_used,
                    agent.next_heartbeat_offset,
                    agent.self_concept_json,
                    agent.room_billboard,
                    agent.heartbeat_interval,
                    agent.room_wpm,
                    int(agent.can_create_agents),
                    agent.sleep_until.isoformat() if agent.sleep_until else None,
                    agent.token_budget,
                    agent.memory_allocations_json,
                    agent.id
                ))
                logger.debug(f"Updated {agent.agent_type} '{agent.name}' (ID {agent.id})")

            conn.commit()
            return agent.id

    def delete_agent(self, agent_id: int) -> bool:
        """Delete an agent by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM agents WHERE id = ?', (agent_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted agent ID {agent_id}")
            return deleted

    def get_architect(self) -> Optional[AIAgent]:
        """Get The Architect agent (the app/user)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM agents WHERE is_architect = 1')
            row = cursor.fetchone()
            return AIAgent.from_dict(dict(row)) if row else None

    def get_ai_agents(self) -> List[AIAgent]:
        """Get all non-Architect agents (the AI agents that get polled)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM agents WHERE is_architect = 0 ORDER BY created_at')
            rows = cursor.fetchall()
            return [AIAgent.from_dict(dict(row)) for row in rows]

    # Message operations
    def get_all_messages(self) -> List[ChatMessage]:
        """Get all messages ordered by sequence number."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM messages ORDER BY sequence_number')
            rows = cursor.fetchall()
            return [ChatMessage.from_dict(dict(row)) for row in rows]

    def get_messages_since(self, sequence_number: int) -> List[ChatMessage]:
        """Get messages after a given sequence number."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM messages
                WHERE sequence_number > ?
                ORDER BY sequence_number
            ''', (sequence_number,))
            rows = cursor.fetchall()
            return [ChatMessage.from_dict(dict(row)) for row in rows]

    def get_next_sequence_number(self) -> int:
        """Get the next sequence number for a message."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT MAX(sequence_number) FROM messages')
            result = cursor.fetchone()[0]
            return (result or 0) + 1

    def save_message(self, message: ChatMessage) -> int:
        """Save a message. Returns the message ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if message.id is None:
                cursor.execute('''
                    INSERT INTO messages (room_id, sender_name, content, timestamp, sequence_number,
                                         message_type, image_url, image_path, reply_to_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    message.room_id,
                    message.sender_name,
                    message.content,
                    message.timestamp.isoformat() if message.timestamp else None,
                    message.sequence_number,
                    message.message_type,
                    message.image_url,
                    message.image_path,
                    message.reply_to_id
                ))
                message.id = cursor.lastrowid
                logger.debug(f"Saved message from '{message.sender_name}' in room {message.room_id}")
            else:
                cursor.execute('''
                    UPDATE messages SET room_id = ?, sender_name = ?, content = ?,
                                       timestamp = ?, sequence_number = ?,
                                       message_type = ?, image_url = ?, image_path = ?, reply_to_id = ?
                    WHERE id = ?
                ''', (
                    message.room_id,
                    message.sender_name,
                    message.content,
                    message.timestamp.isoformat() if message.timestamp else None,
                    message.sequence_number,
                    message.message_type,
                    message.image_url,
                    message.image_path,
                    message.reply_to_id,
                    message.id
                ))

            conn.commit()
            return message.id

    def clear_messages(self) -> None:
        """Delete all messages."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM messages')
            conn.commit()
            logger.info("Cleared all messages")

    # Settings operations
    def get_setting(self, key: str, default: str = None) -> Optional[str]:
        """Get a setting value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT value FROM settings WHERE key = ?', (key,))
            row = cursor.fetchone()
            return row[0] if row else default

    def set_setting(self, key: str, value: str) -> None:
        """Set a setting value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)
            ''', (key, value))
            conn.commit()

    def get_total_tokens_used(self) -> int:
        """Get total tokens used across all agents."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT SUM(total_tokens_used) FROM agents')
            result = cursor.fetchone()[0]
            return result or 0

    # Session save/load
    def export_session(self) -> dict:
        """Export current session data."""
        return {
            'agents': [a.to_dict() for a in self.get_all_agents()],
            'messages': [m.to_dict() for m in self.get_all_messages()]
        }

    def import_session(self, data: dict) -> None:
        """Import session data (messages only, preserves agents)."""
        self.clear_messages()

        for msg_data in data.get('messages', []):
            msg = ChatMessage.from_dict(msg_data)
            msg.id = None  # Force new insert
            self.save_message(msg)

        logger.info(f"Imported session with {len(data.get('messages', []))} messages")

    # Room operations
    def get_all_rooms(self) -> List[ChatRoom]:
        """Get all rooms."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM rooms ORDER BY created_at')
            rows = cursor.fetchall()
            return [ChatRoom.from_dict(dict(row)) for row in rows]

    def get_room(self, room_id: int) -> Optional[ChatRoom]:
        """Get a room by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM rooms WHERE id = ?', (room_id,))
            row = cursor.fetchone()
            return ChatRoom.from_dict(dict(row)) if row else None

    def save_room(self, room: ChatRoom) -> int:
        """Save or update a room. Returns the room ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if room.id is None:
                cursor.execute('''
                    INSERT INTO rooms (name, created_at)
                    VALUES (?, ?)
                ''', (
                    room.name,
                    room.created_at.isoformat() if room.created_at else None
                ))
                room.id = cursor.lastrowid
                logger.info(f"Created room '{room.name}' with ID {room.id}")
            else:
                cursor.execute('''
                    UPDATE rooms SET name = ? WHERE id = ?
                ''', (room.name, room.id))
                logger.debug(f"Updated room '{room.name}' (ID {room.id})")

            conn.commit()
            return room.id

    def delete_room(self, room_id: int) -> bool:
        """Delete a room and its memberships."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Delete memberships first (cascade should handle this but be explicit)
            cursor.execute('DELETE FROM room_members WHERE room_id = ?', (room_id,))
            cursor.execute('DELETE FROM rooms WHERE id = ?', (room_id,))
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted room ID {room_id}")
            return deleted

    # Room membership operations
    def get_room_members(self, room_id: int) -> List[RoomMembership]:
        """Get all memberships for a room."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM room_members WHERE room_id = ?', (room_id,))
            rows = cursor.fetchall()
            return [RoomMembership.from_dict(dict(row)) for row in rows]

    def get_agent_memberships(self, agent_id: int) -> List[RoomMembership]:
        """Get all room memberships for an agent."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM room_members WHERE agent_id = ?', (agent_id,))
            rows = cursor.fetchall()
            return [RoomMembership.from_dict(dict(row)) for row in rows]

    def get_membership(self, agent_id: int, room_id: int) -> Optional[RoomMembership]:
        """Get a specific membership."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM room_members WHERE agent_id = ? AND room_id = ?',
                (agent_id, room_id)
            )
            row = cursor.fetchone()
            return RoomMembership.from_dict(dict(row)) if row else None

    def save_membership(self, membership: RoomMembership) -> int:
        """Save or update a membership. Returns the membership ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            if membership.id is None:
                cursor.execute('''
                    INSERT INTO room_members (agent_id, room_id, joined_at, last_message_id,
                                             status, last_response_time, last_response_word_count,
                                             next_heartbeat_offset, attention_pct, is_dynamic, is_self_room)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    membership.agent_id,
                    membership.room_id,
                    membership.joined_at.isoformat() if membership.joined_at else None,
                    membership.last_message_id,
                    membership.status,
                    membership.last_response_time.isoformat() if membership.last_response_time else None,
                    membership.last_response_word_count,
                    membership.next_heartbeat_offset,
                    membership.attention_pct,
                    int(membership.is_dynamic),
                    int(membership.is_self_room)
                ))
                membership.id = cursor.lastrowid
                logger.info(f"Created membership: agent {membership.agent_id} in room {membership.room_id}")
            else:
                cursor.execute('''
                    UPDATE room_members SET last_message_id = ?, status = ?,
                                           last_response_time = ?, last_response_word_count = ?,
                                           next_heartbeat_offset = ?, attention_pct = ?,
                                           is_dynamic = ?, is_self_room = ?
                    WHERE id = ?
                ''', (
                    membership.last_message_id,
                    membership.status,
                    membership.last_response_time.isoformat() if membership.last_response_time else None,
                    membership.last_response_word_count,
                    membership.next_heartbeat_offset,
                    membership.attention_pct,
                    int(membership.is_dynamic),
                    int(membership.is_self_room),
                    membership.id
                ))
                logger.debug(f"Updated membership ID {membership.id}")

            conn.commit()
            return membership.id

    def delete_membership(self, agent_id: int, room_id: int) -> bool:
        """Delete a membership."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'DELETE FROM room_members WHERE agent_id = ? AND room_id = ?',
                (agent_id, room_id)
            )
            conn.commit()
            deleted = cursor.rowcount > 0
            if deleted:
                logger.info(f"Deleted membership: agent {agent_id} from room {room_id}")
            return deleted

    def get_messages_for_room(self, room_id: int) -> List[ChatMessage]:
        """Get all messages for a specific room."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                'SELECT * FROM messages WHERE room_id = ? ORDER BY sequence_number',
                (room_id,)
            )
            rows = cursor.fetchall()
            return [ChatMessage.from_dict(dict(row)) for row in rows]

    def get_messages_for_room_since(self, room_id: int, sequence_number: int) -> List[ChatMessage]:
        """Get messages for a room after a given sequence number."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM messages
                WHERE room_id = ? AND sequence_number > ?
                ORDER BY sequence_number
            ''', (room_id, sequence_number))
            rows = cursor.fetchall()
            return [ChatMessage.from_dict(dict(row)) for row in rows]

    def clear_room_messages(self, room_id: int) -> None:
        """Delete all messages in a room."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('DELETE FROM messages WHERE room_id = ?', (room_id,))
            conn.commit()
            logger.info(f"Cleared messages for room {room_id}")

    # Room key operations
    def create_room_key(self, room_id: int, key_value: str) -> int:
        """Create a new key for a room. Returns the key ID."""
        from datetime import datetime
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO room_keys (room_id, key_value, created_at, revoked)
                VALUES (?, ?, ?, 0)
            ''', (room_id, key_value, datetime.utcnow().isoformat()))
            conn.commit()
            key_id = cursor.lastrowid
            logger.info(f"Created key for room {room_id}: {key_value}")
            return key_id

    def get_room_keys(self, room_id: int, include_revoked: bool = False) -> List[dict]:
        """Get all keys for a room."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            if include_revoked:
                cursor.execute('SELECT * FROM room_keys WHERE room_id = ?', (room_id,))
            else:
                cursor.execute('SELECT * FROM room_keys WHERE room_id = ? AND revoked = 0', (room_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_key_by_value(self, key_value: str) -> Optional[dict]:
        """Get a key by its value."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM room_keys WHERE key_value = ?', (key_value,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def revoke_room_key(self, room_id: int, key_value: str) -> bool:
        """Revoke a key for a room."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE room_keys SET revoked = 1
                WHERE room_id = ? AND key_value = ?
            ''', (room_id, key_value))
            conn.commit()
            revoked = cursor.rowcount > 0
            if revoked:
                logger.info(f"Revoked key for room {room_id}: {key_value}")
            return revoked

    # Access request operations
    def create_access_request(self, requester_id: int, room_id: int, key_value: str) -> int:
        """Create an access request. Returns the request ID."""
        from datetime import datetime
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO access_requests (requester_id, room_id, key_value, status, created_at)
                VALUES (?, ?, ?, 'pending', ?)
            ''', (requester_id, room_id, key_value, datetime.utcnow().isoformat()))
            conn.commit()
            request_id = cursor.lastrowid
            logger.info(f"Created access request: agent {requester_id} for room {room_id}")
            return request_id

    def get_pending_requests_for_room(self, room_id: int) -> List[dict]:
        """Get all pending access requests for a room."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM access_requests
                WHERE room_id = ? AND status = 'pending'
                ORDER BY created_at
            ''', (room_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_access_request(self, request_id: int) -> Optional[dict]:
        """Get an access request by ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM access_requests WHERE id = ?', (request_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def get_pending_request(self, requester_id: int, room_id: int) -> Optional[dict]:
        """Get a pending request for a specific requester and room."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM access_requests
                WHERE requester_id = ? AND room_id = ? AND status = 'pending'
            ''', (requester_id, room_id))
            row = cursor.fetchone()
            return dict(row) if row else None

    def update_request_status(self, request_id: int, status: str) -> bool:
        """Update the status of an access request (pending, granted, denied)."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE access_requests SET status = ?
                WHERE id = ?
            ''', (status, request_id))
            conn.commit()
            updated = cursor.rowcount > 0
            if updated:
                logger.info(f"Updated request {request_id} status to {status}")
            return updated

    # Message reaction operations
    def add_reaction(self, message_id: int, reactor_id: int, reaction_type: str) -> int:
        """Add a reaction to a message. Returns the reaction ID."""
        from datetime import datetime
        with self._get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO message_reactions (message_id, reactor_id, reaction_type, created_at)
                    VALUES (?, ?, ?, ?)
                ''', (message_id, reactor_id, reaction_type, datetime.utcnow().isoformat()))
                conn.commit()
                reaction_id = cursor.lastrowid
                logger.info(f"Agent {reactor_id} reacted to message {message_id} with {reaction_type}")
                return reaction_id
            except sqlite3.IntegrityError:
                # Already reacted with this type
                logger.debug(f"Agent {reactor_id} already reacted to message {message_id} with {reaction_type}")
                return 0

    def remove_reaction(self, message_id: int, reactor_id: int, reaction_type: str) -> bool:
        """Remove a reaction from a message."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM message_reactions
                WHERE message_id = ? AND reactor_id = ? AND reaction_type = ?
            ''', (message_id, reactor_id, reaction_type))
            conn.commit()
            removed = cursor.rowcount > 0
            if removed:
                logger.info(f"Agent {reactor_id} removed {reaction_type} from message {message_id}")
            return removed

    def get_message_reactions(self, message_id: int) -> List[dict]:
        """Get all reactions for a message."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM message_reactions WHERE message_id = ?
            ''', (message_id,))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_reactions_summary(self, message_id: int) -> dict:
        """Get reaction counts for a message by type."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT reaction_type, COUNT(*) as count
                FROM message_reactions
                WHERE message_id = ?
                GROUP BY reaction_type
            ''', (message_id,))
            rows = cursor.fetchall()
            return {row['reaction_type']: row['count'] for row in rows}

    def get_reactions_for_agent_messages(self, agent_id: int, since_time: str = None) -> List[dict]:
        """Get all reactions to messages by this agent, optionally since a time."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            # Find messages sent by this agent and their reactions
            if since_time:
                cursor.execute('''
                    SELECT r.*, m.room_id, m.content
                    FROM message_reactions r
                    JOIN messages m ON r.message_id = m.id
                    WHERE m.sender_name = ? AND r.created_at > ?
                    ORDER BY r.created_at DESC
                ''', (str(agent_id), since_time))
            else:
                cursor.execute('''
                    SELECT r.*, m.room_id, m.content
                    FROM message_reactions r
                    JOIN messages m ON r.message_id = m.id
                    WHERE m.sender_name = ?
                    ORDER BY r.created_at DESC
                ''', (str(agent_id),))
            rows = cursor.fetchall()
            return [dict(row) for row in rows]

    def get_message_by_id(self, message_id: int) -> Optional[ChatMessage]:
        """Get a message by its ID."""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM messages WHERE id = ?', (message_id,))
            row = cursor.fetchone()
            return ChatMessage.from_dict(dict(row)) if row else None
