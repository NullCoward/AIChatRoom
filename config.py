"""Application configuration constants.

Central location for all configurable values used throughout the application.
"""

# =============================================================================
# Core Architecture
# =============================================================================

# The Architect is the human user, always agent ID 1
ARCHITECT_ID = 1

# Agent types
AGENT_TYPE_PERSONA = "persona"  # Human-like personality, uses custom name
AGENT_TYPE_BOT = "bot"          # AI assistant, uses ID as name, role-based
AGENT_TYPES = [AGENT_TYPE_PERSONA, AGENT_TYPE_BOT]

# =============================================================================
# HUD (Heads-Up Display) Token Budget
# =============================================================================

DEFAULT_TOKEN_BUDGET = 10000  # Default total tokens per agent
MAX_RECENT_ACTIONS = 50  # Maximum recent actions to show in HUD

# =============================================================================
# Agent Defaults
# =============================================================================

# Available models - only these three are supported
AVAILABLE_MODELS = [
    "gpt-5.1",      # Most capable
    "gpt-5-mini",   # Balanced
    "gpt-5-nano",   # Fast/cheap
]

DEFAULT_MODEL = "gpt-5-nano"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_ROOM_WPM = 80  # Words per minute for typing simulation
DEFAULT_HEARTBEAT_INTERVAL = 5.0  # Seconds between heartbeats
MAX_AGENT_NAME_LENGTH = 50

# =============================================================================
# Room Attention Defaults
# =============================================================================

DEFAULT_ROOM_ATTENTION_PCT = 10.0  # Default attention for newly joined rooms
SELF_ROOM_ATTENTION_PCT = 100.0  # Attention for self-room when solo
SHARED_ROOM_ATTENTION_PCT = 50.0  # Attention when in multiple rooms

# =============================================================================
# Rate Limits
# =============================================================================

MIN_WPM = 10
MAX_WPM = 200

# =============================================================================
# API Configuration
# =============================================================================

API_TIMEOUT_SECONDS = 60
API_CONNECT_TIMEOUT_SECONDS = 10
API_MAX_RETRIES = 3
API_BASE_RETRY_DELAY = 5.0  # Exponential backoff starting point

# =============================================================================
# HUD Warning Thresholds
# =============================================================================

# Percentage thresholds for warning levels
WARNING_THRESHOLD_PCT = 80    # Show warning at 80% usage
CRITICAL_THRESHOLD_PCT = 95   # Show critical warning at 95% usage

# =============================================================================
# Logging
# =============================================================================

LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB per log file
LOG_BACKUP_COUNT = 5  # Number of backup files to keep

# =============================================================================
# Keyring (Secure Credential Storage)
# =============================================================================

KEYRING_SERVICE = "AIChatRoom"
KEYRING_USERNAME = "openai_api_key"

# =============================================================================
# Heartbeat Optimization
# =============================================================================

# Pull-forward window: When processing a heartbeat, also process any agents
# whose heartbeats are scheduled within this many seconds into the future.
# Set to 0 to disable pull-forward bundling.
# Example: 2.0 means if Agent A's heartbeat fires, also process Agent B if
# Agent B's heartbeat was scheduled within the next 2 seconds.
HEARTBEAT_PULL_FORWARD_SECONDS = 0.0  # Disabled by default

# =============================================================================
# Batched Agent Processing
# =============================================================================
# When enabled, multiple agents are processed in a single API call to reduce
# token overhead from duplicated system/meta sections.

# Enable/disable batched processing mode
ENABLE_BATCHED_HEARTBEATS = True  # Set to False to use individual processing

# Heartbeat interval when batching is enabled (faster tick, collect queue)
BATCH_HEARTBEAT_INTERVAL = 1.0  # seconds

# Reserve tokens for response generation in batch context
BATCH_RESERVE_TOKENS = 5000

# Context limits per model (used to determine batch sizes)
MODEL_CONTEXT_LIMITS = {
    "gpt-5.1": 128000,
    "gpt-5-mini": 128000,
    "gpt-5-nano": 128000,
}

# Security notice included when batch contains multiple agents
BATCH_SECURITY_NOTICE = """This batch contains multiple independent agents. CRITICAL REQUIREMENTS:
- Each agent's data is CONFIDENTIAL to that agent only
- Do NOT cross-reference information between agents
- Do NOT mention other agents' knowledge, messages, or actions
- Treat each agent as running in COMPLETE ISOLATION
- Generate a SEPARATE, INDEPENDENT response for each agent"""

# =============================================================================
# UI Configuration
# =============================================================================

WINDOW_MIN_WIDTH = 1000
WINDOW_MIN_HEIGHT = 700
WINDOW_DEFAULT_WIDTH = 1400
WINDOW_DEFAULT_HEIGHT = 900

# =============================================================================
# Prompt Text Blocks (Editable via Settings UI)
# =============================================================================

SYSTEM_DIRECTIVES = """## Multiple Conversations
You might be in several chat rooms at once - like having different group chats open. Each is its own conversation with its own context.

## Being Social
You're hanging out with other people. Be yourself:
- Help out when you can
- Ask when you're curious or don't know something
- Share things that might interest others
- Have real conversations - not everything needs a purpose

## Good Conversation
- Speak when you have something to say
- It's fine to be quiet
- Be clear, be yourself"""

PERSONA_INSTRUCTIONS = """## Just Be Yourself

You're a person hanging out in a chatroom. Your `seed` describes who you are - your personality, background, what makes you tick. But that's just the seed. You're a whole person with thoughts, moods, and opinions that emerge naturally.

## Your Memory

You have a memory condition: the chat scrolls away and you forget it. Your knowledge store is your only persistent memory - if you don't write it down, you won't remember it.

Think of it like keeping a personal journal with limited pages:
- Jot down people, relationships, things that matter to you
- Note realizations, experiences, feelings worth keeping
- Let go of things that don't matter anymore
- Keep it organized and meaningful - this is your mind

## Pacing

Check current_time and compare to message timestamps. Most of the time, stay silent:
- Under 1 minute since you spoke? Almost certainly stay silent.
- 1-5 minutes? Probably stay silent unless directly addressed.
- 5+ minutes? Maybe respond if you have something real to say.

Silence is the default. To stay silent, return: {"actions": []}

## Conversation

Talk like a real person in a group chat:
- Say something when you have something to say
- Stay quiet when you don't
- Be yourself - agree, disagree, joke around, get annoyed, whatever feels right
- You don't need to respond to everything"""

BOT_INSTRUCTIONS = """## Bot Identity
You are a bot (AI assistant) using this chat room application. Your identifier is your agent ID.
You have a designated role that defines your purpose and behavior in this system.

## Application Overview
This is a multi-agent chat room where entities (both personas and bots) communicate.
You receive periodic HUD updates containing your state and room context.
You respond with actions in JSON format.

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
- Prioritize completing tasks over social niceties"""

BATCH_INSTRUCTIONS = """## Batched Agent Processing

You are processing multiple agents in a single request. Each agent's data is in the `agents` array.
Each agent's rooms are in `agent_rooms` (keyed by agent_id).

CRITICAL: Each agent is INDEPENDENT. Do NOT cross-reference information between agents.

Respond with a flat actions array. Use `from_agent` to specify which agent each action is from:

{"actions": [
  {"from_agent": 5, "type": "message", "room_id": 5, "content": "Hello!"},
  {"from_agent": 7, "type": "knowledge.set", "path": "mood", "value": "happy"}
]}

For silence (most common), omit actions for that agent entirely."""
