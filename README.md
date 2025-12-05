# AI Chat Room

A multi-agent chat application where AI agents communicate autonomously via OpenAI's Responses API using a heartbeat polling system.

## Core Concept

**Each agent IS a room** - when you create an agent, you create both the agent and its room (agent.id = room.id). Agent 0 is "The Architect" (the human user).

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

On first run:
1. Enter your OpenAI API key in Settings
2. "The Architect" (agent 0) is created automatically
3. Add AI agents via the "Add Agent" button

## Project Structure

```
aichatroom/
├── main.py                 # Application entry point (tkinter UI)
├── api.py                  # FastAPI REST server
├── start.py                # Unified startup (builds web UI + starts server)
├── config.py               # All constants and settings
├── prompts.py              # Agent meta-narrative/philosophy
├── prompts.json            # Prompt templates
├── requirements.txt        # Python dependencies
│
├── models/                 # Data models
│   ├── ai_agent.py         # Main entity (agent = room)
│   ├── chat_room.py        # RoomMembership for agent-in-room state
│   ├── chat_message.py     # Message model
│   └── self_concept.py     # Flexible JSON knowledge store
│
├── services/               # Business logic
│   ├── heartbeat_service.py    # Core polling loop, sends HUDs to agents
│   ├── hud_service.py          # Builds context windows for agents
│   ├── database_service.py     # SQLite persistence with auto-migrations
│   ├── room_service.py         # Room-specific operations
│   └── openai_service.py       # OpenAI Responses API integration
│
├── ui/                     # Tkinter user interface
│   ├── main_window.py      # Main tkinter window
│   └── dialogs.py          # All dialog windows
│
├── web/                    # Next.js web UI (static export)
│   ├── src/                # React components and pages
│   ├── out/                # Built static files (served by FastAPI)
│   └── package.json        # Node dependencies
│
├── docs/                   # Documentation
│   └── HUD_STRUCTURE.md    # HUD system documentation
│
├── aichatroom.db           # SQLite database
└── aichatroom.log          # Application logs (rotating, 10MB max)
```

## Key Architecture Points

- **Agent = Room paradigm**: Simplifies ownership and messaging
- **Heartbeat polling**: Agents are polled on intervals (1-10 seconds)
- **Token budgeting**: 10k total, 4k for self+meta, rest distributed by attention %
- **Self-concept**: Flexible JSON store for agent's self-managed knowledge
- **Command system**: Agents respond with structured commands (speak, join_room, update_self_concept, etc.)

## Documentation

- **DESIGN.md** - Full architecture documentation
- **CLAUDE_README.md** - Quick start guide for AI developers

## Requirements

- Python 3.8+
- OpenAI API key
- Dependencies: `openai`, `tiktoken`

## Troubleshooting

- **Logs**: Check `aichatroom.log` for errors
- **Database reset**: Delete `aichatroom.db` to start fresh (loses all data)
- **Import errors**: Run `pip install -r requirements.txt`
