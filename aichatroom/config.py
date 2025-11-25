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
# HUD (Heads-Up Display) Memory System
# =============================================================================
# The HUD uses a RAM-like memory model:
# - Total Budget: Per-agent configurable token budget
# - Base HUD Cost: Fixed cost for system directives, meta instructions, available actions
# - Allocatable Memory: Total - Base HUD cost, divided among monitors by agent preference
#
# Allocatable monitors (configurable by agent):
# - knowledge: self.knowledge store (persistent memory)
# - recent_actions: self.recent_actions history
# - rooms: all room messages (subdivided by per-room allocation)

DEFAULT_TOKEN_BUDGET = 10000  # Default total tokens per agent (configurable per-agent)

# Legacy constants (used as fallbacks when computing dynamic allocations)
# These are now calculated dynamically but serve as defaults
TOTAL_TOKEN_BUDGET = 10000   # Legacy: global budget (now per-agent)
STATIC_CONTENT_MAX = 5000    # Legacy: max for base HUD (system + meta)
MESSAGE_CONTENT_MIN = 3000   # Minimum tokens reserved for room messages
SELF_META_MAX = 3000         # Legacy: max for knowledge store (now allocation-based)

# Default memory allocations (percentages of allocatable memory)
DEFAULT_MEMORY_ALLOCATIONS = {
    "knowledge": 30,       # 30% for self.knowledge store
    "recent_actions": 10,  # 10% for action history
    "rooms": 60            # 60% for room messages (subdivided by per-room allocation)
}

# Recent actions limits
MAX_RECENT_ACTIONS = 50  # Maximum actions to store (will be truncated to fit allocation)

# =============================================================================
# Agent Defaults
# =============================================================================

# Approved models for agent use - centralized list for consistency
# These are actual OpenAI model IDs that support the Responses API
APPROVED_MODELS = [
    "gpt-4o",
    "gpt-4o-mini",
    "gpt-4-turbo",
    "gpt-4",
    "gpt-3.5-turbo",
    "o1-preview",
    "o1-mini",
]

# User-friendly model aliases for AI agents to use
# Maps alias -> actual model ID
MODEL_ALIASES = {
    "smart": "gpt-4o",
    "fast": "gpt-4o-mini",
    "cheap": "gpt-3.5-turbo",
}

# Reverse mapping: model ID -> alias (for display)
MODEL_ALIASES_REVERSE = {v: k for k, v in MODEL_ALIASES.items()}

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_ROOM_WPM = 80  # Words per minute for typing simulation
DEFAULT_HEARTBEAT_INTERVAL = 5.0  # Seconds between heartbeats
MAX_AGENT_NAME_LENGTH = 50

# =============================================================================
# Room Allocation Defaults (per-room memory subdivision)
# =============================================================================
# These control how the "rooms" allocation is subdivided among individual rooms

DEFAULT_ROOM_ALLOCATION_PCT = 10.0  # Default allocation for newly joined rooms
SELF_ROOM_ALLOCATION_PCT = 100.0  # Allocation for self-room when solo
SHARED_ROOM_ALLOCATION_PCT = 50.0  # Allocation when in multiple rooms

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
# UI Configuration
# =============================================================================

WINDOW_MIN_WIDTH = 1000
WINDOW_MIN_HEIGHT = 700
WINDOW_DEFAULT_WIDTH = 1400
WINDOW_DEFAULT_HEIGHT = 900
