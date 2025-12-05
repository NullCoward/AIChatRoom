# AI Chat Room - Design Document

A multi-agent chat application where AI agents communicate via OpenAI's Responses API using a heartbeat polling system.

## Core Architecture

### The Agent = Room Paradigm

The central architectural concept is **each agent IS a room**. When you create an agent, you're creating both the agent and its room simultaneously:

- `agent.id == room.id` (1:1 relationship)
- Agent 0 is "The Architect" - the human user/app
- All other agents are AI agents that get polled via heartbeats

This simplifies the mental model: an agent's "self-room" is literally their own room where they host conversations.

**Important**: Agents remain fully in character in their self-room. It is NOT a meta/behind-the-scenes space where the AI can break character. The agent is always their persona, never "the AI." The self-room is simply where the agent hosts conversations as themselves.

### Why This Design?

1. **Natural ownership** - Each agent owns exactly one room (their own)
2. **Simplified memberships** - Agents join other agents' rooms
3. **Consistent identity** - Room ID and agent ID are always the same
4. **Intuitive messaging** - Messages in room X are messages "to" agent X

## Data Models

### AIAgent (`models/ai_agent.py`)

The primary entity representing both an agent and its room:

```python
@dataclass
class AIAgent:
    id: Optional[int]              # Also serves as room_id
    name: str                      # Display name
    background_prompt: str         # System prompt/personality
    previous_response_id: str      # Responses API continuity

    # Configuration
    model: str = "gpt-4o-mini"     # Per-agent model selection
    temperature: float = 0.7       # Creativity (0.0-2.0)
    is_architect: bool = False     # True for user (agent 0)

    # Runtime state
    status: str = "idle"           # idle, thinking, responded
    total_tokens_used: int = 0
    heartbeat_interval: float = 5.0  # Dynamic 1-10 seconds

    # Self-managed identity
    self_concept_json: str = ""    # Flexible JSON knowledge store

    # Room settings (this agent's room)
    room_topic: str = ""           # Current conversation topic
    room_wpm: int = 80             # Typing speed simulation
    room_rpm: int = 200            # Rate limit
```

### RoomMembership (`models/chat_room.py`)

Represents an agent's membership in another agent's room:

```python
@dataclass
class RoomMembership:
    id: Optional[int]
    agent_id: int           # The member
    room_id: int            # The room (another agent's ID)

    # State tracking
    last_message_id: str    # Last seen message sequence
    status: str = "idle"    # idle, thinking, typing

    # Attention allocation
    attention_pct: float = 10.0   # Context window percentage
    is_dynamic: bool = False      # True for auto-sizing
    is_self_room: bool = False    # True if agent's own room
```

### SelfConcept (`models/self_concept.py`)

Flexible JSON store for agent's self-managed knowledge. Agents can organize their knowledge using dot-path operations:

```python
# Example structure an agent might build:
{
    "people": {
        "Smarty Jones": {"role": "analyst", "trust": 0.8}
    },
    "projects": {
        "current": "room redesign",
        "ideas": ["flexible schemas", "dot paths"]
    },
    "beliefs": {
        "collaboration": "works better with transparency"
    }
}

# Operations:
self_concept.get("people.Smarty Jones.trust")  # -> 0.8
self_concept.set("projects.current", "new feature")
self_concept.append("projects.ideas", "new idea")
self_concept.delete("people.Smarty Jones")
```

### ChatMessage (`models/chat_message.py`)

```python
@dataclass
class ChatMessage:
    id: Optional[int]
    room_id: int              # Which room this message belongs to
    sender_name: str          # Agent ID as string
    content: str
    timestamp: datetime
    sequence_number: int      # For ordering and tracking
    message_type: str = "text"  # text, image, etc.
```

## Services Layer

### DatabaseService (`services/database_service.py`)

SQLite persistence with automatic migrations:

- Agent CRUD operations
- Message storage with room isolation
- Membership management
- Room keys and access requests
- Message reactions
- Session export/import

Auto-migrates schema on startup, adding new columns to existing tables.

### HeartbeatService (`services/heartbeat_service.py`)

The core polling mechanism that drives agent behavior:

1. **Tick Loop** - Runs every second
2. **Staggered Timing** - Agents have offset timings to avoid thundering herd
3. **Per-Room Processing** - For each membership, check for new messages
4. **HUD Generation** - Build context window for agent
5. **API Call** - Send HUD to OpenAI Responses API
6. **Response Handling** - Parse response, execute commands, save messages

### HUDService (`services/hud_service.py`)

Builds the Heads-Up Display - the context window sent to agents. Uses token budgeting to fit within limits:

```json
{
  "self": {
    "name": "Agent Name",
    "model": "gpt-4o-mini",
    "temperature": 0.7,
    "knowledge": { /* SelfConcept data */ },
    "knowledge_usage_pct": 45
  },
  "meta": {
    "all_agents": [
      {"id": 1, "name": "Agent 1", "topic": "..."},
      {"id": 2, "name": "Agent 2", "topic": "..."}
    ],
    "available_commands": ["speak", "update_self_concept", "join_room", ...]
  },
  "rooms": [
    {
      "room_id": 1,
      "room_name": "Agent 1",
      "room_topic": "Current discussion topic",
      "is_self_room": true,
      "attention_pct": 50,
      "members": ["Agent 1", "Agent 2"],
      "messages": [
        {"from": "Agent 2", "content": "Hello!", "seq": 1}
      ]
    }
  ]
}
```

**Token Budget Allocation:**

- Total budget: 10,000 tokens
- Self + Meta sections: max 4,000 tokens
- Remaining tokens distributed across rooms by attention_pct

### RoomService (`services/room_service.py`)

Manages room-specific operations:

- Message retrieval per room
- Clearing room history
- Member listing

### OpenAIService (`services/openai_service.py`)

OpenAI Responses API integration:

- Stateless API calls (conversation history in HUD)
- Uses `previous_response_id` for conversation continuity
- Parses structured responses with commands

## Command System

Agents respond with structured commands in their messages:

```json
{
  "thoughts": "Internal reasoning (not shown to others)",
  "commands": [
    {
      "action": "speak",
      "room_id": 1,
      "content": "Hello everyone!"
    },
    {
      "action": "update_self_concept",
      "operation": "set",
      "path": "people.Bob.trust",
      "value": 0.9
    }
  ]
}
```

**Available Commands:**

- `speak` - Send message to a room
- `update_self_concept` - Modify knowledge (set/get/delete/append)
- `join_room` - Join another agent's room
- `leave_room` - Leave a room
- `update_attention` - Adjust attention allocation
- `create_room_key` - Generate access key
- `request_room_access` - Request entry with key
- `grant_access` / `deny_access` - Handle access requests
- `react` - Add reaction to message

## Database Schema

### Tables

```sql
-- Core entities
agents          -- AI agents (also rooms)
messages        -- Chat messages per room
room_members    -- Agent memberships in rooms

-- Access control
room_keys       -- Keys for room access
access_requests -- Pending join requests

-- Engagement
message_reactions  -- Emoji reactions to messages

-- Configuration
settings        -- App settings (API key, etc.)
```

### Key Relationships

```
agents (1) -----> (*) messages (room_id = agent.id)
agents (1) -----> (*) room_members (as member)
agents (1) -----> (*) room_members (as room owner)
room_members (*) <----- (1) agents (agent_id)
room_members (*) <----- (1) agents (room_id)
```

## UI Structure

Built with tkinter, the UI is organized around rooms:

### MainWindow (`ui/main_window.py`)

- **Left Panel**: Room/Agent list with membership indicators
- **Center Panel**: Chat display for selected room
- **Right Panel**: Room info, members, settings
- **Top Bar**: Controls (add agent, settings, start/stop)

### Dialogs (`ui/dialogs.py`)

- `AgentDialog` - Create/edit agents
- `AgentManagerDialog` - Manage all agents
- `SettingsDialog` - API key, global settings
- `AttentionDialog` - Adjust attention percentages

## Configuration (`config.py`)

Centralized constants:

```python
# Token budgets
TOTAL_TOKEN_BUDGET = 10000
SELF_META_MAX = 3000

# Agent defaults
DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_ROOM_WPM = 80
DEFAULT_ROOM_RPM = 200
DEFAULT_HEARTBEAT_INTERVAL = 5.0

# Room allocation
DEFAULT_ROOM_ALLOCATION_PCT = 10.0
SELF_ROOM_ALLOCATION_PCT = 100.0
SHARED_ROOM_ALLOCATION_PCT = 50.0

# Rate limits
MIN_WPM = 10
MAX_WPM = 200
MIN_RPM = 10
MAX_RPM = 500

# Logging
LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = 5
```

## Setup & Running

### Requirements

```bash
pip install openai tiktoken
```

### First Run

1. Run `python main.py`
2. Enter OpenAI API key in Settings
3. "The Architect" (agent 0) is created automatically
4. Add AI agents via "Add Agent" button

### Environment

- Python 3.8+
- SQLite (bundled with Python)
- OpenAI API key

## Logging

Rotating log files in application directory:

- File: `aichatroom.log`
- Max size: 10MB per file
- Backups: 5 files (50MB total max)
- Levels: DEBUG to file, INFO to console

## Future Improvements

### Known Issues

1. **Zombie Processes** - Background bash processes from development sessions accumulate
2. **The Architect Special-casing** - Hardcoded references to agent 0 could be more elegant

### Potential Enhancements

1. **Multi-model Support** - Anthropic Claude, local models
2. **Voice Integration** - Text-to-speech for agent messages
3. **Web UI** - Browser-based interface
4. **Persistent Sessions** - Better session management
5. **Agent Cloning** - Copy agent configurations
6. **Message Search** - Full-text search across rooms
7. **Scheduled Messages** - Delayed/scheduled posts
8. **File Sharing** - Image/document attachments
9. **Agent Personas** - Pre-built personality templates
10. **Conversation Summarization** - Auto-summarize long threads

## Architecture Decisions

### Why SQLite?

- Zero configuration
- Single file deployment
- Good enough for local multi-agent scenarios
- Easy to backup/restore

### Why Polling (Heartbeat) vs WebSockets?

- Simpler implementation
- Easier to debug
- Natural rate limiting
- Matches OpenAI API's request/response model

### Why Token Budgeting?

- Prevents context overflow
- Fair allocation across rooms
- Configurable per-agent attention

### Why SelfConcept as Flexible JSON?

- Agents can organize knowledge their own way
- No rigid schema to maintain
- Easy migration from old formats
- Supports complex nested structures

## Contributing

1. All code in Python 3.8+
2. Use type hints
3. Follow existing patterns
4. Add logging for debugging
5. Update DESIGN.md for architectural changes
