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
# HUD (Heads-Up Display) Token Budgets
# =============================================================================

TOTAL_TOKEN_BUDGET = 10000  # Total tokens available for HUD

# Token allocation: up to 50% for non-message content, 50%+ for messages
# Non-message content includes: system directives, self (identity + knowledge), meta (instructions + actions)
# Message content includes: room context and chat messages
STATIC_CONTENT_MAX = 5000  # Max tokens for system + self + meta (50% of total)
MESSAGE_CONTENT_MIN = 5000  # Min tokens reserved for room messages (50% of total)

# =============================================================================
# Agent Defaults
# =============================================================================

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE = 0.7
DEFAULT_ROOM_WPM = 80  # Words per minute for typing simulation
DEFAULT_HEARTBEAT_INTERVAL = 5.0  # Seconds between heartbeats
MAX_AGENT_NAME_LENGTH = 50

# =============================================================================
# Attention Defaults
# =============================================================================

DEFAULT_ATTENTION_PCT = 10.0  # Default attention for joined rooms
SELF_ROOM_ATTENTION_PCT = 100.0  # Attention for self-room when solo
SHARED_ATTENTION_PCT = 50.0  # Attention when in multiple rooms

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
