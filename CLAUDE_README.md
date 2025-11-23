# AI Developer Quick Start

**Read this first if you're a new Claude Code session picking up development.**

## Getting Oriented (5 minutes)

1. **Read DESIGN.md** - Contains full architecture documentation
2. **Understand the core concept**: Each agent IS a room (agent.id = room.id)

## Key Files to Know

### Configuration
- `config.py` - All constants (token budgets, defaults, rate limits)
- `prompts.py` - Agent meta-narrative/philosophy (tunable "soul")

### Models (in `models/`)
- `ai_agent.py` - The main entity (agent = room)
- `chat_room.py` - RoomMembership for agent-in-room state
- `self_concept.py` - Flexible JSON knowledge store
- `chat_message.py` - Message model

### Services (in `services/`)
- `heartbeat_service.py` - Core polling loop, sends HUDs to agents
- `hud_service.py` - Builds context windows for agents
- `database_service.py` - SQLite persistence with auto-migrations
- `chatroom_service.py` - Main app coordinator
- `room_service.py` - Room-specific operations
- `openai_service.py` - OpenAI Responses API integration

### UI (in `ui/`)
- `main_window.py` - Main tkinter window
- `dialogs.py` - All dialog windows

## Common Tasks

### Running the app
```bash
python main.py
```

### Database location
`aichatroom.db` in project root (SQLite)

### Logs
`aichatroom.log` in project root (rotating, 10MB max, 5 backups)

### Adding a new agent field
1. Add to `AIAgent` dataclass in `models/ai_agent.py`
2. Add to `to_dict()` and `from_dict()` methods
3. Add migration in `database_service.py` `_migrate_tables()`
4. Update `save_agent()` INSERT and UPDATE queries

### Adding a new command
1. Define in HUD's `available_commands` in `hud_service.py`
2. Handle in `heartbeat_service.py` command processing

## Architecture Gotchas

1. **Agent 0 is The Architect** - The human user, not an AI agent
2. **Self-room** - Each agent's own room where they're always a member. **Important**: Agents remain fully in character in their self-room - it's NOT a meta/behind-the-scenes space. The agent is always their persona, never "the AI."
3. **Attention %** - Controls context window allocation per room
4. **Token budgeting** - HUD service allocates tokens: 4000 for self+meta, rest for rooms

## Current State

- Database schema is current (migrations auto-apply on startup)
- Logging is configured with rotation
- Config is centralized in `config.py`
- All cleanup tasks from previous sessions are complete

## If Something's Broken

1. Check `aichatroom.log` for errors
2. Database issues: Delete `aichatroom.db` to reset (loses all data)
3. Import errors: Run `pip install -r requirements.txt`

## Development Philosophy

- Agent = Room is the core abstraction, don't fight it
- Prefer editing existing files over creating new ones
- Keep constants in `config.py`
- Log important operations for debugging
- Auto-migrate database schema, don't require manual steps
