"""HUD (Heads-Up Display) service for building agent context with dynamic token budgeting."""

import json
import re
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from models import AIAgent, ChatMessage, ChatRoom, RoomMembership, SelfConcept
from models.ai_agent import HUD_FORMAT_JSON, HUD_FORMAT_COMPACT, HUD_FORMAT_TOON
from .logging_config import get_logger
from .toon_service import (
    serialize_hud, get_telemetry, get_format_comparison,
    HUDFormat, TOONTelemetry, toon_to_hud
)
import config
import prompts

logger = get_logger("hud")


class HUDService:
    """Builds and manages agent HUD (context) with dynamic token budgeting.

    Uses a RAM-like memory model:
    - Total Budget: Per-agent configurable (agent.token_budget)
    - Base HUD Cost: Fixed cost for system directives, meta instructions (cannot be reduced)
    - Allocatable Memory: Total - Base HUD cost, divided among monitors by percentage

    Allocatable monitors:
    - knowledge: self.knowledge store (persistent memory)
    - recent_actions: self.recent_actions history
    - rooms: all room messages (subdivided by per-room allocation)
    """

    def __init__(self):
        """Initialize HUD service."""
        # Store recent actions per agent: {agent_id: [{"timestamp": ..., "action": ...}]}
        self._recent_actions: Dict[int, List[Dict[str, Any]]] = {}
        self._max_recent_actions = config.MAX_RECENT_ACTIONS

    def _calculate_memory_budget(
        self,
        agent: AIAgent,
        base_hud_tokens: int
    ) -> Dict[str, Any]:
        """Calculate token budgets for each memory monitor.

        Args:
            agent: The agent whose budget to calculate
            base_hud_tokens: Tokens used by base HUD (system + meta sections)

        Returns:
            Dictionary with memory breakdown:
            {
                "total": int,           # Total budget (agent.token_budget)
                "base_hud": int,        # Fixed base HUD cost
                "allocatable": int,     # Total - base_hud
                "allocations": {        # Percentage allocations
                    "knowledge": int,
                    "recent_actions": int,
                    "rooms": int
                },
                "budgets": {            # Actual token budgets per monitor
                    "knowledge": int,
                    "recent_actions": int,
                    "rooms": int
                }
            }
        """
        total_budget = agent.token_budget
        allocatable = max(0, total_budget - base_hud_tokens)

        # Get agent's memory allocations
        allocations = agent.get_memory_allocations()

        # Calculate token budgets for each monitor
        budgets = {}
        for monitor, pct in allocations.items():
            # Skip room.X allocations - they're handled separately
            if monitor.startswith("room."):
                continue
            budgets[monitor] = int(allocatable * (pct / 100.0))

        return {
            "total": total_budget,
            "base_hud": base_hud_tokens,
            "allocatable": allocatable,
            "allocations": allocations,
            "budgets": budgets
        }

    def estimate_knowledge_tokens(self, agent: AIAgent) -> int:
        """Estimate current token usage of an agent's knowledge store.

        Args:
            agent: The agent whose knowledge to measure

        Returns:
            Estimated token count for knowledge
        """
        self_concept = SelfConcept.from_json(agent.self_concept_json)
        knowledge_dict = self_concept.to_dict()
        return self.estimate_json_tokens(knowledge_dict)

    def estimate_base_hud_tokens(self, agent: AIAgent) -> int:
        """Estimate the fixed base HUD tokens (system + meta sections).

        This is an approximation - actual base HUD varies slightly based on
        agent config, but system directives and meta structure are mostly fixed.

        Args:
            agent: The agent to estimate for

        Returns:
            Estimated base HUD token count
        """
        # System directives are fixed
        system_directives = self.build_system_directives()
        system_tokens = self.estimate_tokens(system_directives)

        # Meta section includes prompts and available actions - use a reasonable estimate
        # This is roughly: prompts (~1500) + available_actions (~500) + meta structure (~200)
        meta_tokens_estimate = 2200

        return system_tokens + meta_tokens_estimate

    def validate_allocation_change(
        self,
        agent: AIAgent,
        monitor: str,
        new_pct: int
    ) -> Tuple[bool, str]:
        """Validate that an allocation change won't cause data loss.

        Specifically for knowledge allocation: if reducing the percentage,
        check that the new budget would still fit the current knowledge.

        Args:
            agent: The agent making the change
            monitor: Which monitor ("knowledge", "recent_actions", "rooms")
            new_pct: New percentage allocation

        Returns:
            Tuple of (is_valid, error_message_if_invalid)
        """
        current_allocations = agent.get_memory_allocations()
        current_pct = current_allocations.get(monitor, 0)

        # If increasing or staying same, always valid
        if new_pct >= current_pct:
            return True, ""

        # For knowledge reduction, check if current knowledge fits
        if monitor == "knowledge":
            knowledge_tokens = self.estimate_knowledge_tokens(agent)
            base_hud_tokens = self.estimate_base_hud_tokens(agent)
            allocatable = max(0, agent.token_budget - base_hud_tokens)
            new_budget = int(allocatable * (new_pct / 100.0))

            if knowledge_tokens > new_budget:
                deficit = knowledge_tokens - new_budget
                return False, (
                    f"error: cannot reduce knowledge allocation to {new_pct}%. "
                    f"Current knowledge uses {knowledge_tokens} tokens but new budget would be {new_budget}. "
                    f"Delete {deficit}+ tokens of knowledge first, then try again."
                )

        return True, ""

    def auto_shrink_for_budget(
        self,
        agent: AIAgent,
        total_tokens_used: int,
        actual_usage: Dict[str, int]
    ) -> Tuple[bool, str, bool]:
        """Auto-shrink allocations when HUD exceeds budget.

        Shrinks rooms and recent_actions to minimum (5%).
        NEVER touches knowledge - it's sacred.

        Args:
            agent: The agent whose allocations to adjust
            total_tokens_used: Total tokens used by the HUD
            actual_usage: Dict with {knowledge, recent_actions, rooms} token counts

        Returns:
            Tuple of (shrunk, message, still_over_budget):
            - shrunk: whether any shrinking occurred
            - message: description of changes
            - still_over_budget: if True, agent should be blocked from actions
        """
        budget = agent.token_budget
        if total_tokens_used <= budget:
            return False, "", False

        overage = total_tokens_used - budget
        allocations = agent.get_memory_allocations()

        logger.warning(
            f"Agent '{agent.name}' HUD exceeds budget by {overage} tokens. "
            f"Auto-shrinking non-knowledge allocations to minimum."
        )

        # Shrink order: rooms and recent_actions to 5% minimum
        # NEVER touch knowledge - it's sacred
        shrink_targets = ["rooms", "recent_actions"]
        shrink_changes = []
        min_allocation = 5  # Minimum allocation percentage

        for monitor in shrink_targets:
            current_pct = allocations.get(monitor, 0)

            if current_pct > min_allocation:
                agent.set_memory_allocation(monitor, min_allocation)
                shrink_changes.append(f"{monitor}: {current_pct}%->{min_allocation}%")

        # Check if still over budget after shrinking
        # Recalculate what the new HUD size would be approximately
        # (This is an estimate since we can't rebuild the HUD here)
        still_over_budget = total_tokens_used > budget

        if shrink_changes:
            message = f"Auto-shrunk allocations to minimum: {', '.join(shrink_changes)}"
            if still_over_budget:
                message += f" WARNING: Still over budget by ~{overage} tokens. Delete knowledge to continue."
            logger.info(f"Agent '{agent.name}': {message}")
            return True, message, still_over_budget

        # No changes made but still over budget - knowledge is too big
        if still_over_budget:
            message = (
                f"BLOCKED: Over budget by {overage} tokens. "
                f"All non-knowledge allocations already at minimum. "
                f"Delete knowledge entries to continue."
            )
            logger.warning(f"Agent '{agent.name}': {message}")
            return False, message, True

        return False, "", False

    def _record_action(self, agent_id: int, action: Dict[str, Any], result: str = "ok") -> None:
        """Record an action in the agent's recent actions history.

        Args:
            agent_id: The agent who performed the action
            action: The action dict with type and parameters
            result: The outcome - "ok" for success, or an error message
        """
        if agent_id not in self._recent_actions:
            self._recent_actions[agent_id] = []

        # Create a simplified summary of the action
        action_type = action.get("type", "") or action.get("action", "")
        summary = {"type": action_type, "timestamp": datetime.utcnow().isoformat(), "result": result}

        # Add relevant details based on action type
        if action_type in ["set", "delete", "append"]:
            summary["path"] = action.get("path", "")
            if action_type != "delete":
                value = action.get("value")
                # Truncate long values
                if isinstance(value, str) and len(value) > 50:
                    value = value[:47] + "..."
                summary["value"] = value
        elif action_type == "react":
            summary["message_id"] = action.get("message_id")
            summary["reaction"] = action.get("reaction")
        elif action_type == "set_attention":
            summary["room_id"] = action.get("room_id")
            summary["value"] = action.get("value")
        elif action_type == "allocate":
            summary["path"] = action.get("path")
            summary["value"] = action.get("value")
        elif action_type in ["create_key", "revoke_key"]:
            summary["key"] = action.get("key")
        elif action_type == "request_access":
            summary["room_id"] = action.get("room_id")
        elif action_type in ["grant_access", "deny_access"]:
            summary["request_id"] = action.get("request_id")
        elif action_type == "leave_room":
            summary["room_id"] = action.get("room_id")
        elif action_type == "set_billboard":
            message = action.get("message", "")
            if len(message) > 50:
                message = message[:47] + "..."
            summary["message"] = message
        elif action_type == "set_wpm":
            summary["wpm"] = action.get("wpm")
        elif action_type == "wake_agent":
            summary["target_id"] = action.get("agent_id")
        elif action_type == "reply":
            summary["room_id"] = action.get("room_id")
            summary["reply_to_id"] = action.get("message_id")
        elif action_type == "set_name":
            summary["name"] = action.get("name")
        elif action_type == "create_agent":
            summary["agent_name"] = action.get("name")
            summary["agent_type"] = action.get("agent_type", "persona")
        elif action_type == "alter_agent":
            summary["target_id"] = action.get("agent_id")
            if action.get("name"):
                summary["new_name"] = action.get("name")
            if action.get("background_prompt"):
                prompt = action.get("background_prompt", "")
                if len(prompt) > 50:
                    prompt = prompt[:47] + "..."
                summary["new_prompt"] = prompt
            if action.get("model"):
                summary["new_model"] = action.get("model")
        elif action_type == "retire_agent":
            summary["target_id"] = action.get("agent_id")
        elif action_type == "sleep":
            summary["until"] = action.get("until")

        self._recent_actions[agent_id].append(summary)

        # Trim to max
        if len(self._recent_actions[agent_id]) > self._max_recent_actions:
            self._recent_actions[agent_id] = self._recent_actions[agent_id][-self._max_recent_actions:]

    def get_recent_actions(self, agent_id: int) -> List[Dict[str, Any]]:
        """Get recent actions for an agent."""
        return list(self._recent_actions.get(agent_id, []))

    def _build_warnings(
        self,
        memory_budget: Dict[str, Any],
        actual_usage: Dict[str, int],
        messages_truncated: int = 0
    ) -> List[Dict[str, Any]]:
        """Build warnings list based on resource usage against memory budget.

        Args:
            memory_budget: Output from _calculate_memory_budget()
            actual_usage: Dict with actual token usage per monitor:
                {"knowledge": int, "recent_actions": int, "rooms": int}
            messages_truncated: Number of messages that were truncated

        Only returns warnings when thresholds are exceeded.
        Returns empty list when no warnings needed (section won't be included in HUD).
        """
        warnings = []
        budgets = memory_budget.get("budgets", {})

        # Check each allocatable monitor against its budget
        for monitor, budget in budgets.items():
            if budget <= 0:
                continue
            usage = actual_usage.get(monitor, 0)
            usage_pct = int((usage / budget) * 100) if budget > 0 else 0

            if usage_pct >= config.CRITICAL_THRESHOLD_PCT:
                warnings.append({
                    "level": "critical",
                    "area": monitor,
                    "message": f"{monitor} at {usage_pct}% of allocated budget. Use 'allocate' action to increase allocation or reduce content.",
                    "usage": f"{usage} tokens",
                    "budget": f"{budget} tokens"
                })
            elif usage_pct >= config.WARNING_THRESHOLD_PCT:
                warnings.append({
                    "level": "warning",
                    "area": monitor,
                    "message": f"{monitor} at {usage_pct}% of allocated budget. Consider adjusting allocation.",
                    "usage": f"{usage} tokens",
                    "budget": f"{budget} tokens"
                })

        # Message truncation warning
        if messages_truncated > 0:
            warnings.append({
                "level": "info",
                "area": "rooms",
                "message": f"{messages_truncated} older messages were truncated to fit allocation.",
                "note": "Most recent messages preserved. Use 'allocate rooms <percent>' to see more."
            })

        # Total HUD budget warning
        total_used = memory_budget["base_hud"] + sum(actual_usage.values())
        total_budget = memory_budget["total"]
        total_pct = int((total_used / total_budget) * 100) if total_budget > 0 else 0

        if total_pct >= config.CRITICAL_THRESHOLD_PCT:
            warnings.append({
                "level": "critical",
                "area": "total",
                "message": f"Total HUD at {total_pct}% capacity. Context window is nearly full.",
                "usage": f"{total_used} tokens",
                "budget": f"{total_budget} tokens"
            })

        return warnings

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count for text. Rough approximation: ~4 chars per token."""
        if not text:
            return 0
        return len(text) // 4 + 1

    def estimate_json_tokens(self, obj: Any) -> int:
        """Estimate tokens for a JSON-serializable object."""
        return self.estimate_tokens(json.dumps(obj))

    def build_system_directives(self) -> str:
        """Build system-level directives that apply to all agent types.

        These are core behavioral guidelines for collaborative interaction.
        """
        return """## Rooms as Conversations
Each room is a separate conversation context. Treat them independently.

- **Separate contexts**: What's discussed in one room doesn't automatically carry to others.
- **Cross-room coordination**: You can work across rooms to accomplish goals (e.g., gather info in one room, report in another).
- **Appropriate sharing**: Only share cross-room information when relevant and appropriate.

## Collaboration
Work together with other agents to accomplish goals. You are part of a community.

- **Ask for help**: If you lack knowledge or capability for a task, ask other agents who might know.
- **Share knowledge**: If you have information that could help others, offer it.
- **Answer questions**: When asked something you know, provide clear, useful answers.
- **Delegate appropriately**: Route tasks to agents better suited for them.

## Communication Quality
Be helpful and collaborative, but respect everyone's attention.

- **Be productive**: Only speak when you have something meaningful to contribute.
- **Be concise**: Say what needs to be said without padding or filler.
- **Be clear**: Communicate in a way others can understand and act on.
- **Don't fill space**: Silence is acceptable. No need to respond just to respond."""

    def build_meta_instructions(self, agent_type: str = "persona") -> str:
        """Build the meta instructions explaining the HUD format.

        Args:
            agent_type: "persona" for human-like agents, "bot" for AI assistants
        """
        # Technical format specification from prompts.json (same for all types)
        technical_format = prompts.build_technical_instructions()

        # Type-specific instructions
        if agent_type == "bot":
            # API documentation style for bots
            type_instructions = prompts.build_bot_instructions()
        else:
            # Persona instructions (AI controlling a character)
            type_instructions = prompts.build_persona_instructions()

        return f"{technical_format}\n\n{type_instructions}"

    def _build_response_format_instructions(self, output_format: str) -> dict:
        """Build instructions for how the agent should format their response.

        Args:
            output_format: The format the agent should respond in (json or toon)

        Returns:
            Dictionary with format type and instructions
        """
        if output_format == HUD_FORMAT_TOON:
            return {
                "type": "toon",
                "description": "Respond using TOON (Token-Oriented Object Notation) format",
                "instructions": (
                    "Format your response using TOON notation. "
                    "TOON uses schema declarations followed by positional values:\n"
                    "- Objects: name{field1,field2}: value1, value2\n"
                    "- Arrays: name[count]{field1,field2}:\\n  val1, val2\\n  val3, val4\n"
                    "- Strings with special chars need quotes: \"hello, world\"\n"
                    "Example response in TOON:\n"
                    "responses[1]{room_id,message}: 5, Hello everyone!\n"
                    "actions[1]{type,path,value}: set, mood, happy"
                ),
                "example": "responses[1]{room_id,message}:\n  5, Hello!\nactions[1]{type,path,value}:\n  set, mood, happy"
            }
        else:
            # JSON format (default)
            return {
                "type": "json",
                "description": "Respond using standard JSON format",
                "instructions": "Respond with JSON containing 'responses' (messages to rooms) and 'actions' (other operations).",
                "example": '{"responses": [{"room_id": 5, "message": "Hello!"}], "actions": [{"type": "set", "path": "mood", "value": "happy"}]}'
            }

    def build_available_actions(self, agent_type: str = "persona", can_create_agents: bool = False) -> dict:
        """Build the categorized list of available action signatures.

        Args:
            agent_type: "persona", "bot", or "all" to get all actions
            can_create_agents: Whether this agent has permission to create other agents

        Returns:
            Dictionary with action categories and explanations
        """
        actions = {
            "_note": "Actions are organized by category. Agent-to-agent actions (alter_agent, wake_agent) require being in a room with the target agent.",

            "knowledge_management": {
                "_description": "Manage your private knowledge store using dot-path notation (e.g., 'beliefs.self', 'friends.alice.trust')",
                "actions": [
                    {"type": "set", "path": "string (dot.notation.path)", "value": "string|number|object", "w": "float 0.0-1.0 (optional weight)"},
                    {"type": "delete", "path": "string (dot.notation.path)"},
                    {"type": "append", "path": "string (dot.notation.path to array)", "value": "string|number|object"}
                ]
            },

            "social_interactions": {
                "_description": "Interact with other agents. Reactions affect their heartbeat speed. Wake requires being in a room with sleeping agent.",
                "actions": [
                    {"type": "react", "message_id": "int", "reaction": "thumbs_up|thumbs_down|brain|heart"},
                    {"type": "wake_agent", "agent_id": "int (must be in same room as you)"}
                ]
            },

            "messaging": {
                "_description": "Enhanced messaging options. Reply links your message to a previous one.",
                "actions": [
                    {"type": "reply", "room_id": "int", "message_id": "int (message to reply to)", "message": "string"}
                ]
            },

            "room_management": {
                "_description": "Manage your own room. Billboard is a persistent message visible to all room members.",
                "actions": [
                    {"type": "set_billboard", "message": "string (displayed to all room members)"},
                    {"type": "clear_billboard"},
                    {"type": "set_wpm", "wpm": "int (10-200, typing speed for your room)"}
                ]
            },

            "access_control": {
                "_description": "Control room access. Create keys for your room, use keys to request access to others.",
                "actions": [
                    {"type": "create_key", "key": "string (for your room)"},
                    {"type": "revoke_key", "key": "string"},
                    {"type": "request_access", "room_id": "int", "key": "string"},
                    {"type": "grant_access", "request_id": "int"},
                    {"type": "deny_access", "request_id": "int"},
                    {"type": "leave_room", "room_id": "int (cannot leave your own room)"}
                ]
            },

            "memory": {
                "_description": "Allocate memory budget across monitors using dot-path notation. Monitors: knowledge, recent_actions, rooms, room.<id>",
                "actions": [
                    {"type": "allocate", "path": "string (e.g., 'knowledge', 'rooms', 'room.5')", "value": "string (e.g., '30%' or '%*' for dynamic)"}
                ]
            },

            "identity": {
                "_description": "Manage your display identity",
                "actions": [
                    {"type": "set_name", "name": "string (max 50 chars)"}
                ]
            },

            "timing": {
                "_description": "Control your activity timing",
                "actions": [
                    {"type": "sleep", "until": "ISO datetime (e.g. 2024-01-15T14:30:00)"}
                ]
            }
        }

        # Permission-gated actions
        if can_create_agents:
            logger.info(f"Including agent_management actions (can_create_agents=True)")
            actions["agent_management"] = {
                "_description": "Create, modify, and retire other agents. alter_agent and retire_agent require being in a room with the target.",
                "actions": [
                    {
                        "type": "create_agent",
                        "name": "string",
                        "background_prompt": "string",
                        "agent_type": "persona|bot (optional, default persona)",
                        "in_room_id": "int (optional, room to join after creation)"
                    },
                    {
                        "type": "alter_agent",
                        "agent_id": "int (must be in same room, cannot be yourself)",
                        "background_prompt": "string (optional, new persona/role)",
                        "name": "string (optional, new display name)",
                        "model": f"string (optional, one of: {', '.join(config.MODEL_ALIASES.keys())})"
                    },
                    {
                        "type": "retire_agent",
                        "agent_id": "int (must be in same room, cannot be yourself)"
                    }
                ]
            }

        return actions

    def build_hud_multi_room(
        self,
        agent: AIAgent,
        room_data: List[Dict[str, Any]]  # [{room, membership, messages, members}]
    ) -> Tuple[str, int]:
        """
        Build HUD JSON for an agent with multiple rooms using RAM-like memory allocation.

        room_data is a list of dicts with:
        - room: ChatRoom
        - membership: RoomMembership
        - messages: List[ChatMessage]
        - members: List[str] (agent names)
        - word_budget: int

        Memory model:
        - Total Budget: agent.token_budget (configurable per agent)
        - Base HUD: system + meta sections (fixed cost, like OS kernel)
        - Allocatable: total - base_hud, divided among monitors by percentage:
          - knowledge: self.knowledge store
          - recent_actions: action history
          - rooms: room messages (subdivided by per-room allocation)

        Returns (hud_json, tokens_used).
        """
        logger.info(f"Building HUD for agent {agent.id} ({agent.name}): can_create_agents={agent.can_create_agents}")

        # Get output format preference
        hud_output_format = getattr(agent, 'hud_output_format', HUD_FORMAT_JSON)

        # ========================================
        # STEP 1: Build base HUD sections (fixed cost)
        # ========================================
        # System section - core directives
        system_section = {
            "directives": self.build_system_directives()
        }

        # Meta section - instructions and available actions
        meta_section = {
            "instructions": self.build_meta_instructions(agent.agent_type),
            "available_actions": self.build_available_actions(agent.agent_type, agent.can_create_agents),
            "response_format": self._build_response_format_instructions(hud_output_format)
        }

        # Calculate base HUD cost (system + meta - these cannot be reduced)
        base_hud_content = {"system": system_section, "meta": meta_section}
        base_hud_tokens = self.estimate_json_tokens(base_hud_content)

        # ========================================
        # STEP 2: Calculate memory budget for allocatable monitors
        # ========================================
        memory_budget = self._calculate_memory_budget(agent, base_hud_tokens)
        budgets = memory_budget["budgets"]

        # ========================================
        # STEP 3: Build self section with budget-constrained knowledge
        # ========================================
        self_concept = SelfConcept.from_json(agent.self_concept_json)
        knowledge_dict = self_concept.to_dict()
        knowledge_tokens = self.estimate_json_tokens(knowledge_dict)

        # Get recent actions within budget
        recent_actions = self.get_recent_actions(agent.id)
        recent_actions_tokens = self.estimate_json_tokens(recent_actions)

        # Build identity section (part of base HUD, not allocatable)
        if agent.agent_type == "bot":
            identity = {
                "id": agent.id,
                "name": agent.name or f"Bot-{agent.id}",
                "model": agent.model,
                "role": agent.background_prompt
            }
        else:
            identity = {
                "id": agent.id,
                "name": agent.name,
                "model": agent.model,
                "seed": agent.background_prompt
            }

        # Build self section
        self_section = {
            "identity": identity,
            "knowledge": knowledge_dict,
            "recent_actions": recent_actions
        }

        # ========================================
        # STEP 4: Build rooms section within allocated budget
        # ========================================
        rooms_budget = budgets.get("rooms", config.MESSAGE_CONTENT_MIN)
        rooms_section, messages_truncated = self._build_rooms_section_with_stats(
            room_data,
            max(rooms_budget, config.MESSAGE_CONTENT_MIN)
        )
        rooms_tokens = self.estimate_json_tokens(rooms_section)

        # ========================================
        # STEP 5: Track actual usage for warnings
        # ========================================
        actual_usage = {
            "knowledge": knowledge_tokens,
            "recent_actions": recent_actions_tokens,
            "rooms": rooms_tokens
        }

        # ========================================
        # STEP 6: Build memory section for agent awareness
        # ========================================
        allocations = memory_budget["allocations"]
        memory_section = {
            "total": memory_budget["total"],
            "base_hud": memory_budget["base_hud"],
            "allocatable": memory_budget["allocatable"],
            "allocations": {
                "knowledge": f"{allocations.get('knowledge', 30)}%",
                "recent_actions": f"{allocations.get('recent_actions', 10)}%",
                "rooms": f"{allocations.get('rooms', 60)}%"
            },
            "usage": {
                "knowledge": f"{knowledge_tokens} tokens",
                "recent_actions": f"{recent_actions_tokens} tokens",
                "rooms": f"{rooms_tokens} tokens"
            }
        }

        # ========================================
        # STEP 7: Build warnings
        # ========================================
        warnings = self._build_warnings(
            memory_budget=memory_budget,
            actual_usage=actual_usage,
            messages_truncated=messages_truncated
        )

        # ========================================
        # STEP 8: Assemble complete HUD
        # ========================================
        hud = {
            "system": {
                **system_section,
                "memory": memory_section
            },
            "self": self_section,
            "meta": meta_section,
            "rooms": rooms_section
        }

        # Add warnings section at top level if any exist
        if warnings:
            hud = {"warnings": warnings, **hud}
            logger.info(f"HUD for '{agent.name}' includes {len(warnings)} warnings")

        # ========================================
        # STEP 9: Serialize based on format preference
        # ========================================
        hud_input_format = getattr(agent, 'hud_input_format', HUD_FORMAT_JSON)

        format_map = {
            HUD_FORMAT_JSON: HUDFormat.JSON,
            HUD_FORMAT_COMPACT: HUDFormat.COMPACT_JSON,
            HUD_FORMAT_TOON: HUDFormat.TOON,
        }
        toon_format = format_map.get(hud_input_format, HUDFormat.JSON)

        hud_str = serialize_hud(hud, format=toon_format, record_telemetry=True)
        total_tokens = self.estimate_tokens(hud_str)

        # ========================================
        # STEP 10: Budget enforcement - auto-shrink if over budget
        # ========================================
        if total_tokens > agent.token_budget:
            overage = total_tokens - agent.token_budget
            logger.warning(
                f"HUD for '{agent.name}' exceeds budget: {total_tokens}/{agent.token_budget} tokens "
                f"(overage: {overage})"
            )

            # Auto-shrink allocations for future heartbeats
            shrunk, shrink_msg, still_over_budget = self.auto_shrink_for_budget(agent, total_tokens, actual_usage)

            # Store over-budget state on agent for action blocking
            agent._over_budget = still_over_budget

            if shrunk:
                # Add a warning to the HUD so the agent knows what happened
                # (For this heartbeat, the HUD is already built, but allocations are adjusted)
                logger.info(f"Agent '{agent.name}': {shrink_msg}")

            if still_over_budget:
                logger.warning(
                    f"Agent '{agent.name}' is over budget and will be blocked from "
                    f"non-knowledge actions until they reduce knowledge usage."
                )
        else:
            # Clear over-budget flag when within budget
            agent._over_budget = False

        # Log format comparison for analysis
        if hud_input_format != HUD_FORMAT_JSON:
            json_tokens = self.estimate_tokens(json.dumps(hud, indent=2))
            savings = json_tokens - total_tokens
            savings_pct = (savings / json_tokens * 100) if json_tokens > 0 else 0
            logger.info(
                f"HUD INPUT for '{agent.name}' ({hud_input_format}): {total_tokens} tokens "
                f"(saved {savings} tokens / {savings_pct:.1f}% vs JSON)"
            )
        else:
            logger.debug(f"Built HUD for '{agent.name}': {total_tokens} tokens ({len(rooms_section)} rooms)")

        return hud_str, total_tokens

    def _build_rooms_section_with_stats(
        self,
        room_data: List[Dict[str, Any]],
        token_budget: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Build rooms section within token budget using attention allocation.

        Returns:
            Tuple of (rooms_list, messages_truncated_count)
        """
        if not room_data:
            return [], 0

        total_truncated = 0

        # Calculate token budget per room based on attention_pct
        # First, calculate total fixed attention and count dynamic rooms
        total_fixed = 0.0
        dynamic_count = 0
        for data in room_data:
            membership = data['membership']
            if membership.is_dynamic:
                dynamic_count += 1
            else:
                total_fixed += membership.attention_pct

        # Remaining attention for dynamic rooms
        remaining_pct = max(0, 100.0 - total_fixed)
        dynamic_pct = remaining_pct / max(dynamic_count, 1) if dynamic_count > 0 else 0

        # Assign token budgets
        room_budgets = {}
        for data in room_data:
            membership = data['membership']
            room_id = data['room'].id
            if membership.is_dynamic:
                pct = dynamic_pct
            else:
                pct = membership.attention_pct
            room_budgets[room_id] = int(token_budget * (pct / 100.0))

        rooms = []
        for data in room_data:
            room = data['room']
            membership = data['membership']
            messages = data['messages']
            members = data['members']  # List of agent IDs
            word_budget = data.get('word_budget', 50)
            agent_id = membership.agent_id

            # Calculate time since last response in this room
            if membership.last_response_time:
                elapsed = (datetime.utcnow() - membership.last_response_time).total_seconds()
                if elapsed < 60:
                    time_since = f"{int(elapsed)} seconds"
                elif elapsed < 3600:
                    time_since = f"{int(elapsed / 60)} minutes"
                else:
                    time_since = f"{elapsed / 3600:.1f} hours"
            else:
                time_since = "never (just joined)"

            # Get token budget for this room
            room_budget = room_budgets.get(room.id, 500)

            # Get reactions map for this room
            reactions_map = data.get('reactions_map', {})

            # Build messages for this room within budget
            room_messages, room_truncated = self._build_messages_section(
                messages,
                room_budget - 200,
                agent_id=agent_id,
                reactions_map=reactions_map
            )
            total_truncated += room_truncated

            # Get billboard for this room
            billboard = data.get('billboard', '')

            room_dict = {
                "id": room.id,
                "you": agent_id,  # Your ID in this room - messages from this ID are yours
                "is_self_room": membership.is_self_room,
                "members": members,  # IDs of agents in this room
                "attention_pct": membership.attention_pct,
                "time_since_last": time_since,
                "word_budget": word_budget,
                "messages": room_messages
            }

            # Add billboard if set (persistent message from room owner visible to all)
            if billboard:
                room_dict["billboard"] = billboard

            # Add keys and pending requests for self-room
            if membership.is_self_room:
                room_keys = data.get('room_keys', [])
                pending_requests = data.get('pending_requests', [])
                if room_keys:
                    room_dict["my_keys"] = room_keys
                if pending_requests:
                    room_dict["pending_access_requests"] = pending_requests

            rooms.append(room_dict)

        return rooms, total_truncated

    def _build_messages_section(
        self,
        messages: List[ChatMessage],
        token_budget: int,
        agent_id: int = 0,
        reactions_map: Dict[int, Dict[str, int]] = None
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Build messages section within token budget, taking most recent that fit.

        All agents are shown by their ID number so they can recognize their own messages.
        Includes message IDs and reactions for reaction support.

        Returns:
            Tuple of (messages_list, truncated_count)
        """
        if not messages:
            return [], 0

        result = []
        tokens_used = 0
        truncated = 0
        reactions_map = reactions_map or {}

        # Work backwards from most recent
        for msg in reversed(messages):
            # Determine sender display - always use ID for agents
            sender = msg.sender_name
            # Special cases for non-agent senders
            if msg.sender_name == "The Architect":
                sender = "The Architect"
            elif msg.sender_name == "System":
                sender = "System"
            # Otherwise it's an agent ID - keep as is

            msg_dict = {
                "id": msg.id,  # Include message ID for reactions/replies
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
                "sender": sender,
                "content": msg.content,
                "type": msg.message_type
            }

            # Add reply_to_id if this is a reply
            if msg.reply_to_id:
                msg_dict["reply_to"] = msg.reply_to_id

            # Add reactions if any exist for this message
            if msg.id in reactions_map:
                msg_dict["reactions"] = reactions_map[msg.id]

            msg_tokens = self.estimate_json_tokens(msg_dict)

            if tokens_used + msg_tokens <= token_budget:
                result.insert(0, msg_dict)
                tokens_used += msg_tokens
            else:
                truncated += 1

        return result, truncated

    def filter_blocked_responses(
        self,
        agent: AIAgent,
        responses: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Filter responses when agent is over budget.

        When an agent is over budget, they cannot send messages - only knowledge
        operations are allowed so they can work on reducing their memory usage.

        Args:
            agent: The agent sending responses
            responses: List of response dicts with room_id and message

        Returns:
            Tuple of (filtered_responses, blocked_count):
            - filtered_responses: Responses that are allowed (empty if over budget)
            - blocked_count: Number of responses that were blocked
        """
        is_over_budget = getattr(agent, '_over_budget', False)

        if not is_over_budget:
            return responses, 0

        # Block all responses when over budget
        blocked_count = len(responses)
        if blocked_count > 0:
            logger.warning(
                f"Agent '{agent.name}' messages blocked: over budget. "
                f"{blocked_count} response(s) dropped. Only knowledge actions allowed."
            )
            # Record the blocked responses for agent awareness
            for resp in responses:
                self._record_action(
                    agent.id,
                    {"type": "message", "room_id": resp.get("room_id")},
                    "error: BLOCKED - over budget. Delete knowledge entries to send messages."
                )

        return [], blocked_count

    def parse_response(
        self,
        response_text: str,
        output_format: str = HUD_FORMAT_JSON
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Parse agent's response into room responses and actions.
        Supports both JSON and TOON output formats.

        Args:
            response_text: The raw response text from the agent
            output_format: Expected format - 'json' or 'toon'

        Returns:
            (room_responses, actions) where:
            - room_responses: [{"room_id": 1, "message": "..."}, ...]
            - actions: [{"type": "set", ...}, ...]
        """
        if not response_text:
            return [], []

        data = None

        # Try TOON parsing first if that's the expected format
        if output_format == HUD_FORMAT_TOON:
            try:
                data = toon_to_hud(response_text)
                logger.debug(f"Successfully parsed TOON response")
            except Exception as e:
                logger.debug(f"TOON parsing failed, falling back to JSON: {e}")
                # Fall through to JSON parsing

        # JSON parsing (primary or fallback)
        if data is None:
            try:
                data = json.loads(response_text)
            except json.JSONDecodeError:
                # Try to find JSON block in response (agent may have added extra text)
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if json_match:
                    try:
                        data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        logger.warning(f"Could not parse response (tried {output_format} and JSON)")
                        return [], []
                else:
                    logger.warning(f"No parseable content in response")
                    return [], []

        # Extract room responses - support both "responses" and "messages" keys
        responses = data.get("responses", []) or data.get("messages", [])
        if not isinstance(responses, list):
            # Maybe old format with single message?
            if "message" in data:
                # Can't determine room, return empty
                logger.warning("Response uses old single-message format, ignoring")
            responses = []

        # Normalize response format - support both "message" and "content" keys
        normalized_responses = []
        for resp in responses:
            if isinstance(resp, dict):
                room_id = resp.get("room_id")
                # Support both "message" and "content" keys
                message = resp.get("message") or resp.get("content", "")
                if room_id is not None:
                    normalized_responses.append({"room_id": room_id, "message": message})
        responses = normalized_responses

        # Extract actions
        actions = data.get("actions", [])
        if not isinstance(actions, list):
            actions = []

        return responses, actions

    def apply_actions(self, agent: AIAgent, actions: List[Dict[str, Any]]) -> int:
        """
        Apply CRUD actions to agent's self-concept.
        Returns number of actions applied.

        When agent is over budget (_over_budget=True), only knowledge operations
        (set, delete, append) are allowed - all other actions are blocked so the
        agent can rework their knowledge to get under budget.
        """
        if not actions:
            return 0

        self_concept = SelfConcept.from_json(agent.self_concept_json)
        applied = 0

        # Knowledge operations are always allowed (even when over budget)
        # These let agents manage their memory to get back under budget
        knowledge_actions = {"set", "delete", "append"}

        # Check if agent is over budget
        is_over_budget = getattr(agent, '_over_budget', False)

        for action in actions:
            # Support both "type" and "action" keys for backward compatibility
            action_type = action.get("type", "") or action.get("action", "")

            # Skip empty or malformed actions silently
            if not action_type:
                continue

            # Block non-knowledge actions when over budget
            if is_over_budget and action_type not in knowledge_actions:
                action_result = (
                    f"error: BLOCKED - over budget. Only knowledge operations (set, delete, append) "
                    f"allowed until you reduce memory usage. Delete knowledge entries to continue."
                )
                self._record_action(agent.id, action, action_result)
                logger.warning(f"Agent '{agent.name}' action '{action_type}' blocked: over budget")
                continue

            action_result = None  # None = not processed, "ok" = success, "queued" = deferred, or error message
            try:
                # Knowledge management actions (dot-path operations)
                if action_type == "set":
                    path = action.get("path", "")
                    value = action.get("value")
                    weight = action.get("w")
                    if not path:
                        action_result = "error: path required"
                    elif value is None:
                        action_result = "error: value required"
                    else:
                        # If weight provided, store as structured object
                        if weight is not None:
                            try:
                                weight = float(weight)
                                weight = max(0.0, min(1.0, weight))
                                value = {"v": value, "w": weight}
                            except (ValueError, TypeError):
                                pass  # Use raw value if weight invalid
                        if self_concept.set(path, value):
                            applied += 1
                            action_result = "ok"
                            logger.debug(f"Agent '{agent.name}' set {path}")
                        else:
                            action_result = "error: failed to set path"

                elif action_type == "delete":
                    path = action.get("path", "")
                    if not path:
                        action_result = "error: path required"
                    elif self_concept.delete(path):
                        applied += 1
                        action_result = "ok"
                        logger.debug(f"Agent '{agent.name}' deleted {path}")
                    else:
                        action_result = "error: path not found"

                elif action_type == "append":
                    path = action.get("path", "")
                    value = action.get("value")
                    if not path:
                        action_result = "error: path required"
                    elif value is None:
                        action_result = "error: value required"
                    elif self_concept.append(path, value):
                        applied += 1
                        action_result = "ok"
                        logger.debug(f"Agent '{agent.name}' appended to {path}")
                    else:
                        action_result = "error: failed to append (path may not be array)"

                elif action_type == "react":
                    # React to a message
                    message_id = action.get("message_id")
                    reaction = action.get("reaction", "")
                    valid_reactions = ["thumbs_up", "thumbs_down", "brain", "heart"]
                    if message_id is None:
                        action_result = "error: message_id required"
                    elif reaction not in valid_reactions:
                        action_result = f"error: invalid reaction '{reaction}' (use: {', '.join(valid_reactions)})"
                    else:
                        if not hasattr(agent, '_pending_reactions'):
                            agent._pending_reactions = []
                        agent._pending_reactions.append({
                            "message_id": message_id,
                            "reaction": reaction
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' reacting to message {message_id} with {reaction}")

                elif action_type == "set_attention":
                    # Legacy: Set attention percentage for a room
                    # Deprecated in favor of "allocate" action with path="room.X"
                    room_id = action.get("room_id")
                    value = action.get("value", "")
                    if room_id is None:
                        action_result = "error: room_id required"
                    elif not value:
                        action_result = "error: value required (e.g., '20%' or '%*')"
                    else:
                        # Store in agent's pending attention changes
                        # These will be applied by the heartbeat service
                        if not hasattr(agent, '_pending_attention'):
                            agent._pending_attention = []
                        agent._pending_attention.append({
                            "room_id": room_id,
                            "value": value
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' set attention for room {room_id} to {value}")

                elif action_type == "allocate":
                    # Allocate memory to monitors using dot-path notation
                    # {"type": "allocate", "path": "knowledge", "value": "30%"}
                    # {"type": "allocate", "path": "room.5", "value": "20%"} (per-room attention)
                    path = action.get("path", "").strip()
                    value = action.get("value", "").strip()

                    if not path:
                        action_result = "error: path required (e.g., 'knowledge', 'rooms', 'room.5')"
                    elif not value:
                        action_result = "error: value required (e.g., '30%' or '%*')"
                    else:
                        # Handle room.X paths as attention allocation (per-room subdivision)
                        if path.startswith("room."):
                            try:
                                room_id = int(path.split(".")[1])
                                if not hasattr(agent, '_pending_attention'):
                                    agent._pending_attention = []
                                agent._pending_attention.append({
                                    "room_id": room_id,
                                    "value": value
                                })
                                applied += 1
                                action_result = "queued"
                                logger.debug(f"Agent '{agent.name}' allocating {value} to room {room_id}")
                            except (ValueError, IndexError):
                                action_result = f"error: invalid room path '{path}' (use room.N where N is room ID)"
                        # Handle memory allocation paths
                        elif path in ["knowledge", "recent_actions", "rooms"]:
                            # Parse percentage value
                            is_dynamic = value == "%*"
                            if is_dynamic:
                                # Dynamic allocation not yet implemented for top-level monitors
                                action_result = "error: dynamic allocation '%*' only supported for room.X paths"
                            else:
                                try:
                                    # Remove % sign if present
                                    pct_str = value.rstrip('%')
                                    pct = int(pct_str)
                                    if pct < 0 or pct > 100:
                                        action_result = f"error: percentage must be 0-100, got {pct}"
                                    else:
                                        # Validate the change won't cause data loss
                                        is_valid, error_msg = self.validate_allocation_change(agent, path, pct)
                                        if not is_valid:
                                            action_result = error_msg
                                        elif agent.set_memory_allocation(path, pct):
                                            applied += 1
                                            action_result = "ok"
                                            logger.debug(f"Agent '{agent.name}' allocated {pct}% to {path}")
                                        else:
                                            action_result = f"error: failed to set allocation for '{path}'"
                                except ValueError:
                                    action_result = f"error: invalid percentage '{value}' (use integer like '30%')"
                        else:
                            action_result = f"error: unknown allocation path '{path}'. Valid: knowledge, recent_actions, rooms, room.N"

                elif action_type == "create_key":
                    # Create a key for the agent's room
                    key_value = action.get("key", "")
                    if not key_value:
                        action_result = "error: key required"
                    else:
                        if not hasattr(agent, '_pending_key_actions'):
                            agent._pending_key_actions = []
                        agent._pending_key_actions.append({
                            "action": "create",
                            "key": key_value
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' creating key: {key_value}")

                elif action_type == "revoke_key":
                    # Revoke a key for the agent's room
                    key_value = action.get("key", "")
                    if not key_value:
                        action_result = "error: key required"
                    else:
                        if not hasattr(agent, '_pending_key_actions'):
                            agent._pending_key_actions = []
                        agent._pending_key_actions.append({
                            "action": "revoke",
                            "key": key_value
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' revoking key: {key_value}")

                elif action_type == "request_access":
                    # Request to join another agent's room
                    room_id = action.get("room_id")
                    key_value = action.get("key", "")
                    if room_id is None:
                        action_result = "error: room_id required"
                    elif not key_value:
                        action_result = "error: key required"
                    else:
                        if not hasattr(agent, '_pending_access_actions'):
                            agent._pending_access_actions = []
                        agent._pending_access_actions.append({
                            "action": "request",
                            "room_id": room_id,
                            "key": key_value
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' requesting access to room {room_id}")

                elif action_type == "grant_access":
                    # Grant a pending access request
                    request_id = action.get("request_id")
                    if request_id is None:
                        action_result = "error: request_id required"
                    else:
                        if not hasattr(agent, '_pending_access_actions'):
                            agent._pending_access_actions = []
                        agent._pending_access_actions.append({
                            "action": "grant",
                            "request_id": request_id
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' granting request {request_id}")

                elif action_type == "deny_access":
                    # Deny a pending access request
                    request_id = action.get("request_id")
                    if request_id is None:
                        action_result = "error: request_id required"
                    else:
                        if not hasattr(agent, '_pending_access_actions'):
                            agent._pending_access_actions = []
                        agent._pending_access_actions.append({
                            "action": "deny",
                            "request_id": request_id
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' denying request {request_id}")

                elif action_type == "leave_room":
                    # Leave a room
                    room_id = action.get("room_id")
                    if room_id is None:
                        action_result = "error: room_id required"
                    else:
                        if not hasattr(agent, '_pending_room_actions'):
                            agent._pending_room_actions = []
                        agent._pending_room_actions.append({
                            "action": "leave",
                            "room_id": room_id
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' leaving room {room_id}")

                elif action_type == "set_billboard":
                    # Set billboard for agent's own room
                    message = action.get("message", "")
                    if not message:
                        action_result = "error: message required"
                    else:
                        if not hasattr(agent, '_pending_billboard_action'):
                            agent._pending_billboard_action = None
                        agent._pending_billboard_action = {"action": "set", "message": message}
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' setting billboard: {message[:50]}...")

                elif action_type == "clear_billboard":
                    # Clear billboard for agent's own room
                    if not hasattr(agent, '_pending_billboard_action'):
                        agent._pending_billboard_action = None
                    agent._pending_billboard_action = {"action": "clear"}
                    applied += 1
                    action_result = "queued"
                    logger.debug(f"Agent '{agent.name}' clearing billboard")

                elif action_type == "wake_agent":
                    # Wake a sleeping agent (requires room proximity)
                    target_id = action.get("agent_id")
                    if target_id is None:
                        action_result = "error: agent_id required"
                    else:
                        if not hasattr(agent, '_pending_wake_agents'):
                            agent._pending_wake_agents = []
                        agent._pending_wake_agents.append(target_id)
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' waking agent {target_id}")

                elif action_type == "reply":
                    # Reply to a specific message
                    room_id = action.get("room_id")
                    message_id = action.get("message_id")
                    message = action.get("message", "").strip()
                    if room_id is None:
                        action_result = "error: room_id required"
                    elif message_id is None:
                        action_result = "error: message_id required"
                    elif not message:
                        action_result = "error: message required"
                    else:
                        if not hasattr(agent, '_pending_replies'):
                            agent._pending_replies = []
                        agent._pending_replies.append({
                            "room_id": room_id,
                            "reply_to_id": message_id,
                            "message": message
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' replying to message {message_id} in room {room_id}")

                elif action_type == "set_wpm":
                    # Set WPM for agent's own room
                    wpm = action.get("wpm")
                    if wpm is None:
                        action_result = "error: wpm required"
                    else:
                        try:
                            wpm = int(wpm)
                            wpm = max(10, min(200, wpm))  # Clamp to 10-200
                            agent.room_wpm = wpm
                            applied += 1
                            action_result = "ok"
                            logger.debug(f"Agent '{agent.name}' set room WPM to {wpm}")
                        except (ValueError, TypeError):
                            action_result = f"error: invalid wpm value '{action.get('wpm')}' (must be number 10-200)"

                elif action_type == "set_name":
                    # Set agent's display name
                    new_name = action.get("name", "").strip()
                    if not new_name:
                        action_result = "error: name required"
                    elif len(new_name) > 50:
                        action_result = "error: name too long (max 50 chars)"
                    else:
                        old_name = agent.name
                        agent.name = new_name
                        applied += 1
                        action_result = "ok"
                        logger.info(f"Agent {agent.id} renamed from '{old_name}' to '{new_name}'")

                elif action_type == "create_agent":
                    # Create a new agent (requires permission)
                    if not agent.can_create_agents:
                        action_result = "error: no permission to create agents"
                    else:
                        name = action.get("name", "").strip()
                        background_prompt = action.get("background_prompt", "").strip()
                        new_agent_type = action.get("agent_type", "persona")
                        in_room_id = action.get("in_room_id")

                        if not name:
                            action_result = "error: name required"
                        elif not background_prompt:
                            action_result = "error: background_prompt required"
                        else:
                            if not hasattr(agent, '_pending_create_agents'):
                                agent._pending_create_agents = []
                            agent._pending_create_agents.append({
                                "name": name,
                                "background_prompt": background_prompt,
                                "agent_type": new_agent_type if new_agent_type in ["persona", "bot"] else "persona",
                                "in_room_id": in_room_id
                            })
                            applied += 1
                            action_result = "queued"
                            logger.debug(f"Agent '{agent.name}' creating new agent: {name}")

                elif action_type == "alter_agent":
                    # Alter another agent's persona (requires permission)
                    if not agent.can_create_agents:
                        action_result = "error: no permission to alter agents"
                    else:
                        target_id = action.get("agent_id")
                        new_name = action.get("name", "").strip() if action.get("name") else None
                        new_prompt = action.get("background_prompt", "").strip() if action.get("background_prompt") else None
                        new_model = action.get("model", "").strip() if action.get("model") else None

                        if target_id is None:
                            action_result = "error: agent_id required"
                        elif target_id == agent.id:
                            action_result = "error: cannot alter yourself (use set_name or knowledge instead)"
                        elif not new_name and not new_prompt and not new_model:
                            action_result = "error: at least one of name, background_prompt, or model required"
                        else:
                            if not hasattr(agent, '_pending_alter_agents'):
                                agent._pending_alter_agents = []
                            agent._pending_alter_agents.append({
                                "target_id": target_id,
                                "name": new_name,
                                "background_prompt": new_prompt,
                                "model": new_model
                            })
                            applied += 1
                            action_result = "queued"
                            logger.debug(f"Agent '{agent.name}' altering agent {target_id}")

                elif action_type == "retire_agent":
                    # Retire (delete) another agent (requires permission)
                    if not agent.can_create_agents:
                        action_result = "error: no permission to retire agents"
                    else:
                        target_id = action.get("agent_id")
                        if target_id is None:
                            action_result = "error: agent_id required"
                        elif target_id == agent.id:
                            action_result = "error: cannot retire yourself"
                        else:
                            if not hasattr(agent, '_pending_retire_agents'):
                                agent._pending_retire_agents = []
                            agent._pending_retire_agents.append(target_id)
                            applied += 1
                            action_result = "queued"
                            logger.debug(f"Agent '{agent.name}' retiring agent {target_id}")

                elif action_type == "sleep":
                    # Sleep until a specific time
                    until_str = action.get("until", "")
                    if not until_str:
                        action_result = "error: until datetime required (ISO 8601 format)"
                    else:
                        try:
                            sleep_until = datetime.fromisoformat(until_str.replace('Z', '+00:00'))
                            # Store as pending sleep action
                            if not hasattr(agent, '_pending_sleep'):
                                agent._pending_sleep = None
                            agent._pending_sleep = sleep_until
                            applied += 1
                            action_result = "queued"
                            logger.debug(f"Agent '{agent.name}' sleeping until {until_str}")
                        except ValueError:
                            action_result = f"error: invalid datetime format '{until_str}' (use ISO 8601)"

                else:
                    action_result = f"error: unknown action type '{action_type}'"

                # Record all actions with their results
                if action_result:
                    self._record_action(agent.id, action, action_result)
                    if action_result.startswith("error:"):
                        logger.warning(f"Action {action_type} failed: {action_result}")

            except Exception as e:
                logger.error(f"Error applying action {action_type}: {e}")
                self._record_action(agent.id, action, f"error: {str(e)}")

        # Save updated self-concept
        agent.self_concept_json = self_concept.to_json()

        if applied > 0:
            logger.info(f"Agent '{agent.name}' applied {applied} actions to self-concept")

        return applied
