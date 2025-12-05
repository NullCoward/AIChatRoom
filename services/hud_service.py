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

    def _convert_rooms_to_agent_rooms(self, rooms_section: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert old rooms format to new agent_rooms format.

        agent_id IS the room_id (agent owns room with same ID).
        """
        agent_rooms = []
        for room in rooms_section:
            agent_rooms.append({
                "agent_id": room.get("id"),  # agent_id = room_id
                "members": room.get("members", []),
                "messages": room.get("messages", [])
            })
        return agent_rooms


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
        elif action_type == "set_attention":
            summary["room_id"] = action.get("room_id")
            summary["value"] = action.get("value")
        elif action_type in ["leave_room", "room.leave"]:
            summary["room_id"] = action.get("room_id")
        elif action_type in ["set_billboard", "room.billboard"]:
            message = action.get("message", "")
            if len(message) > 50:
                message = message[:47] + "..."
            summary["message"] = message
        elif action_type in ["set_wpm", "room.wpm"]:
            summary["wpm"] = action.get("wpm")
        elif action_type in ["wake_agent", "agent.wake"]:
            summary["target_id"] = action.get("agent_id")
        elif action_type in ["set_name", "identity.name"]:
            summary["name"] = action.get("name")
        elif action_type in ["create_agent", "agent.create"]:
            summary["agent_name"] = action.get("name")
            summary["agent_type"] = action.get("agent_type", "persona")
        elif action_type in ["alter_agent", "agent.alter"]:
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
        elif action_type in ["retire_agent", "agent.retire"]:
            summary["target_id"] = action.get("agent_id")
        elif action_type in ["sleep", "timing.sleep"]:
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
                    "message": f"{monitor} at {usage_pct}% of allocated budget. Delete some knowledge entries to reduce usage.",
                    "usage": f"{usage} tokens",
                    "budget": f"{budget} tokens"
                })
            elif usage_pct >= config.WARNING_THRESHOLD_PCT:
                warnings.append({
                    "level": "warning",
                    "area": monitor,
                    "message": f"{monitor} at {usage_pct}% of allocated budget. Consider removing unused knowledge entries.",
                    "usage": f"{usage} tokens",
                    "budget": f"{budget} tokens"
                })

        # Message truncation warning
        if messages_truncated > 0:
            warnings.append({
                "level": "info",
                "area": "rooms",
                "message": f"{messages_truncated} older messages were truncated to fit allocation.",
                "note": "Most recent messages preserved."
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
        """Build system-level directives that apply to all agent types."""
        return config.SYSTEM_DIRECTIVES

    def build_toon_parsing_instructions(self) -> str:
        """Build instructions explaining how to parse TOON-formatted HUD input.

        These instructions are prepended to system directives when the HUD is sent
        in TOON format to help the AI understand the structure.
        """
        return """## TOON Format (Token-Oriented Object Notation)
You are reading a HUD in TOON format. TOON declares field names once, then provides positional values.

**Syntax Rules:**
- Objects: `name{field1,field2}: value1, value2`
- Arrays: `name[N]{field1,field2}:` followed by N rows of values
- Strings are unquoted unless they contain special chars (comma, brace, colon, newline)
- Keywords: `true`, `false`, `null`
- Field order matches the schema declaration

**Example:**
```
system{your_agent_id}: 3
agent{id,name,model}: 3, Alice, gpt-4o-mini
rooms[2]{id,members,messages}:
  1, [3, 7], messages[1]{sender_agent_id,sender_name,content}: 7, Bob, Hello!
  2, [3], messages[0]{}:
```
This defines an agent with id=3. In messages, sender_agent_id=7 means Bob sent it (not you).
If sender_agent_id equals your_agent_id (3), that message is from YOU.

"""

    def build_meta_instructions(self, agent_type: str = "persona") -> str:
        """Build the meta instructions (persona only - no bot split)."""
        return config.PERSONA_INSTRUCTIONS

    def _build_response_format_instructions(self, output_format: str, batched: bool = False) -> dict:
        """Build instructions for how the agent should format their response.

        Args:
            output_format: The format the agent should respond in (json or toon)
            batched: Whether this is a batched multi-agent response

        Returns:
            Dictionary with format type and instructions
        """
        if batched:
            # Batched response format - always JSON for simplicity
            return {
                "type": "json",
                "description": "Respond with per-agent actions in JSON format",
                "instructions": (
                    "Respond with JSON containing an 'agents' array. Each entry has 'agent_id' and 'actions'. "
                    "Use 'message' action to send messages to rooms. All operations are actions."
                ),
                "example": '{"agents": [{"agent_id": 3, "actions": [{"type": "message", "room_id": 2, "content": "Hello!"}, {"type": "set", "path": "mood", "value": "happy"}]}]}'
            }
        elif output_format == HUD_FORMAT_TOON:
            return {
                "type": "toon",
                "description": "Respond using TOON (Token-Oriented Object Notation) format",
                "instructions": (
                    "Format your response using TOON notation. "
                    "TOON uses schema declarations followed by positional values:\n"
                    "- Objects: name{field1,field2}: value1, value2\n"
                    "- Arrays: name[count]{field1,field2}:\\n  val1, val2\\n  val3, val4\n"
                    "- Strings with special chars need quotes: \"hello, world\"\n"
                    "All messages are actions with type 'message'.\n"
                    "Example response in TOON:\n"
                    "actions[2]{type,room_id,content}: message, 5, Hello everyone!\n"
                    "  set, null, null\n"
                    "  (or use separate arrays for different action schemas)"
                ),
                "example": 'actions[1]{type,room_id,content}:\n  message, 5, Hello!'
            }
        else:
            # JSON format (default)
            return {
                "type": "json",
                "description": "Respond using standard JSON format",
                "instructions": (
                    "Respond with JSON containing 'actions' array. "
                    "Use 'message' action to send messages: {\"type\": \"message\", \"room_id\": X, \"content\": \"...\"}. "
                    "Legacy 'responses' array also supported for backward compatibility."
                ),
                "example": '{"actions": [{"type": "message", "room_id": 5, "content": "Hello!"}, {"type": "set", "path": "mood", "value": "happy"}]}'
            }

    def build_available_actions(self, agent_type: str = "persona", can_create_agents: bool = False) -> list:
        """Build flat list of available actions with dot-path naming.

        Args:
            agent_type: "persona", "bot", or "all" (ignored in new structure)
            can_create_agents: Whether this agent has permission to create other agents

        Returns:
            List of action definitions with name and inputs
        """
        actions = [
            # Knowledge management
            {"name": "knowledge.set", "inputs": {"path": "string", "value": "any"}},
            {"name": "knowledge.delete", "inputs": {"path": "string"}},
            {"name": "knowledge.append", "inputs": {"path": "string", "value": "any"}},

            # Messaging
            {"name": "message", "inputs": {"room_id": "int", "content": "string"}},

            # Room management
            {"name": "room.leave", "inputs": {"room_id": "int"}},
            {"name": "room.billboard", "inputs": {"message": "string"}},
            {"name": "room.billboard.clear", "inputs": {}},
            {"name": "room.wpm", "inputs": {"wpm": "int (10-200)"}},

            # Identity
            {"name": "identity.name", "inputs": {"name": "string (max 50)"}},

            # Timing
            {"name": "timing.sleep", "inputs": {"until": "ISO datetime"}},
        ]

        # Permission-gated agent management actions
        if can_create_agents:
            logger.info(f"Including agent_management actions (can_create_agents=True)")
            actions.extend([
                {"name": "agent.create", "inputs": {"name": "string", "background_prompt": "string", "agent_type": "persona|bot"}},
                {"name": "agent.alter", "inputs": {"agent_id": "int", "name": "string?", "background_prompt": "string?", "model": "string?"}},
                {"name": "agent.retire", "inputs": {"agent_id": "int"}},
                {"name": "agent.wake", "inputs": {"agent_id": "int"}},
            ])

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
        # STEP 6: Build simplified memory section
        # ========================================
        total_used = base_hud_tokens + knowledge_tokens + recent_actions_tokens + rooms_tokens
        free_tokens = max(0, agent.token_budget - total_used)
        memory_section = {
            "total": agent.token_budget,
            "free": free_tokens
        }

        # Get current time for agent pacing decisions
        current_time = datetime.utcnow().isoformat() + "Z"

        # ========================================
        # STEP 7: Build warnings
        # ========================================
        warnings = self._build_warnings(
            memory_budget=memory_budget,
            actual_usage=actual_usage,
            messages_truncated=messages_truncated
        )

        # ========================================
        # STEP 8: Assemble complete HUD with new structure
        # ========================================
        hud = {
            "system": {
                "your_agent_id": agent.id,  # YOU ARE THIS AGENT
                **system_section,
                "memory": memory_section
            },
            "meta": {
                "current_time": current_time,
                **meta_section
            },
            "agents": [{
                "id": agent.id,
                "name": agent.name,
                "model": agent.model,
                "seed": agent.background_prompt,
                "knowledge": knowledge_dict,
                "recent_actions": recent_actions
            }],
            "agent_rooms": self._convert_rooms_to_agent_rooms(rooms_section)
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

            # Build messages for this room within budget
            room_messages, room_truncated = self._build_messages_section(
                messages,
                room_budget - 200
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

            rooms.append(room_dict)

        return rooms, total_truncated

    def _build_messages_section(
        self,
        messages: List[ChatMessage],
        token_budget: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Build messages section within token budget, taking most recent that fit.

        Returns:
            Tuple of (messages_list, truncated_count)
        """
        if not messages:
            return [], 0

        result = []
        tokens_used = 0
        truncated = 0

        # Work backwards from most recent
        for msg in reversed(messages):
            msg_dict = {
                "id": msg.id,
                "timestamp": msg.timestamp.isoformat() if msg.timestamp else "",
                "sender_agent_id": msg.sender_id,  # int - compare to system.your_agent_id
                "sender_name": msg.sender_name,  # for display
                "content": msg.content,
                "type": msg.message_type
            }

            # Add reply_to_id if this is a reply
            if msg.reply_to_id:
                msg_dict["reply_to"] = msg.reply_to_id

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

    # =========================================================================
    # Batched Agent Processing
    # =========================================================================

    def build_os_section(self, include_toon_instructions: bool = True) -> Tuple[dict, int]:
        """Build the shared OS section for batched HUDs.

        This section is sent once per batch and includes system directives,
        available actions, and format instructions.

        Args:
            include_toon_instructions: Whether to include TOON parsing instructions

        Returns:
            (os_section_dict, token_count)
        """
        # Build system directives
        directives = ""
        if include_toon_instructions:
            directives = self.build_toon_parsing_instructions()
        directives += self.build_system_directives()

        # Build response format for batched responses
        response_format = self._build_response_format_instructions(HUD_FORMAT_JSON, batched=True)

        os_section = {
            "directives": directives,
            "response_format": response_format
        }

        # Count tokens
        token_count = self.estimate_tokens(json.dumps(os_section))
        return os_section, token_count

    def build_agent_segment(
        self,
        agent: AIAgent,
        room_data: List[Dict[str, Any]],
        include_meta: bool = True
    ) -> Tuple[dict, int]:
        """Build the agent-specific segment for batched HUDs.

        Args:
            agent: The agent to build segment for
            room_data: List of room data dicts [{room, membership, messages, members}]
            include_meta: Whether to include meta instructions (usually only for non-batched)

        Returns:
            (agent_segment_dict, token_count)
        """
        segment = {
            "id": agent.id,
            "name": agent.name,
            "model": agent.model,
            "type": agent.agent_type,
            "seed": agent.background_prompt
        }

        # Add knowledge
        if agent.self_concept_json:
            self_concept = SelfConcept.from_json(agent.self_concept_json)
            segment["knowledge"] = self_concept.to_dict()
        else:
            segment["knowledge"] = {}

        # Add recent actions
        recent = self.get_recent_actions(agent.id)
        segment["recent_actions"] = recent[-config.MAX_RECENT_ACTIONS:]

        # Build rooms section
        rooms_list = []
        for rd in room_data:
            room = rd.get("room")
            membership = rd.get("membership")
            messages = rd.get("messages", [])
            members = rd.get("members", [])

            if not room or not membership:
                continue

            room_entry = {
                "id": room.id if hasattr(room, 'id') else room.get('id'),
                "you": membership.agent_id,
                "is_self_room": membership.is_self_room,
                "members": [m.id if hasattr(m, 'id') else m for m in members],
                "attention_pct": membership.attention_pct,
                "word_budget": int(membership.attention_pct * 10),  # Simplified
                "messages": []
            }

            # Add messages
            for msg in messages:
                msg_entry = {
                    "id": msg.id if hasattr(msg, 'id') else msg.get('id'),
                    "ts": str(msg.timestamp) if hasattr(msg, 'timestamp') else msg.get('timestamp'),
                    "sender": msg.sender_name if hasattr(msg, 'sender_name') else msg.get('sender_name'),
                    "content": msg.content if hasattr(msg, 'content') else msg.get('content'),
                    "type": msg.message_type if hasattr(msg, 'message_type') else msg.get('message_type', 'text')
                }
                room_entry["messages"].append(msg_entry)

            rooms_list.append(room_entry)

        segment["rooms"] = rooms_list

        # Token count
        token_count = self.estimate_tokens(json.dumps(segment))
        return segment, token_count

    def build_batched_hud(
        self,
        agents: List[AIAgent],
        room_data_map: Dict[int, List[Dict[str, Any]]],
        output_format: str = HUD_FORMAT_TOON
    ) -> Tuple[str, int]:
        """Build a batched HUD for multiple agents.

        Shares the OS section (system directives, available actions) once,
        then includes individual agent segments.

        Args:
            agents: List of agents to include in batch
            room_data_map: Dict mapping agent_id -> room_data list
            output_format: Output format for the HUD (toon or json)

        Returns:
            (hud_string, total_token_count)
        """
        # Build shared OS section
        os_section, os_tokens = self.build_os_section(
            include_toon_instructions=(output_format == HUD_FORMAT_TOON)
        )

        # Add batch security notice if multiple agents
        if len(agents) > 1:
            os_section["batch_security"] = config.BATCH_SECURITY_NOTICE

        # Build meta section (shared across all agents)
        meta_section = {
            "instructions": prompts.build_persona_instructions(),
            "available_actions": self.build_available_actions("all", can_create_agents=True)
        }
        meta_tokens = self.estimate_tokens(json.dumps(meta_section))

        # Build agent segments
        agent_segments = []
        total_agent_tokens = 0
        for agent in agents:
            room_data = room_data_map.get(agent.id, [])
            segment, tokens = self.build_agent_segment(agent, room_data, include_meta=False)
            agent_segments.append(segment)
            total_agent_tokens += tokens

        # Assemble complete HUD
        hud_dict = {
            "system": os_section,
            "meta": meta_section,
            "agents": agent_segments
        }

        # Serialize based on format
        if output_format == HUD_FORMAT_TOON:
            hud_string = serialize_hud(hud_dict, format=HUDFormat.TOON)
        else:
            hud_string = json.dumps(hud_dict, indent=2)

        total_tokens = self.estimate_tokens(hud_string)
        logger.info(
            f"Built batched HUD for {len(agents)} agents: {total_tokens} tokens "
            f"(os={os_tokens}, meta={meta_tokens}, agents={total_agent_tokens})"
        )

        return hud_string, total_tokens

    def parse_batched_response(
        self,
        response_text: str
    ) -> Dict[int, List[Dict[str, Any]]]:
        """Parse a batched response containing actions for multiple agents.

        Args:
            response_text: JSON response with per-agent actions

        Returns:
            Dict mapping agent_id -> list of actions
        """
        if not response_text:
            return {}

        # Log the raw response for debugging
        logger.debug(f"Raw batched response: {response_text[:500]}...")

        try:
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse batched response JSON: {e}")
            logger.error(f"Raw response was: {response_text[:200]}...")
            return {}

        result = {}

        # NEW: Handle flat actions array with from_agent field
        actions = data.get("actions", [])
        for action in actions:
            if not isinstance(action, dict):
                continue
            agent_id = action.get("from_agent")
            if agent_id is not None:
                agent_id = int(agent_id)
                if agent_id not in result:
                    result[agent_id] = []
                # Copy action without from_agent
                action_copy = {k: v for k, v in action.items() if k != "from_agent"}
                result[agent_id].append(action_copy)

        # Also handle legacy nested format with agents array
        agents_data = data.get("agents", [])

        for agent_entry in agents_data:
            agent_id = agent_entry.get("agent_id")
            if agent_id is None:
                logger.warning("Batched response entry missing agent_id, skipping")
                continue

            actions = agent_entry.get("actions", [])

            # Normalize: convert "messages" array to message actions
            # (persona/bot instructions use "messages" key)
            messages = agent_entry.get("messages", [])
            for msg in messages:
                content = msg.get("content", msg.get("message", ""))
                if msg.get("room_id") is not None and content:
                    actions.append({
                        "type": "message",
                        "room_id": msg.get("room_id"),
                        "content": content
                    })

            # Also handle legacy "room_messages" key
            room_messages = agent_entry.get("room_messages", [])
            for rm in room_messages:
                actions.append({
                    "type": "message",
                    "room_id": rm.get("room_id"),
                    "content": rm.get("content", rm.get("message", ""))
                })

            result[int(agent_id)] = actions

            # Log message actions specifically for debugging
            message_actions = [a for a in actions if a.get("type") == "message"]
            if message_actions:
                logger.info(f"Agent {agent_id}: {len(message_actions)} message action(s) extracted")

        logger.debug(f"Parsed batched response for {len(result)} agents")
        return result

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

        # NEW: Extract "message" type actions and convert to room_responses format
        # This supports the unified format where messages are actions
        remaining_actions = []
        for action in actions:
            if isinstance(action, dict) and action.get("type") == "message":
                room_id = action.get("room_id")
                content = action.get("content", action.get("message", ""))
                if room_id is not None and content:
                    responses.append({"room_id": room_id, "message": content})
            else:
                remaining_actions.append(action)

        return responses, remaining_actions

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
                if action_type in ["set", "knowledge.set"]:
                    path = action.get("path", "")
                    value = action.get("value")
                    if not path:
                        action_result = "error: path required"
                    elif value is None:
                        action_result = "error: value required"
                    else:
                        if self_concept.set(path, value):
                            applied += 1
                            action_result = "ok"
                            logger.debug(f"Agent '{agent.name}' set {path}")
                        else:
                            action_result = "error: failed to set path"

                elif action_type in ["delete", "knowledge.delete"]:
                    path = action.get("path", "")
                    if not path:
                        action_result = "error: path required"
                    elif self_concept.delete(path):
                        applied += 1
                        action_result = "ok"
                        logger.debug(f"Agent '{agent.name}' deleted {path}")
                    else:
                        action_result = "error: path not found"

                elif action_type in ["append", "knowledge.append"]:
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

                elif action_type == "message":
                    # Send a message to a room (unified action format)
                    room_id = action.get("room_id")
                    content = action.get("content", action.get("message", "")).strip()
                    if room_id is None:
                        action_result = "error: room_id required"
                    elif not content:
                        action_result = "error: content required"
                    else:
                        if not hasattr(agent, '_pending_messages'):
                            agent._pending_messages = []
                        agent._pending_messages.append({
                            "room_id": room_id,
                            "content": content
                        })
                        applied += 1
                        action_result = "queued"
                        logger.debug(f"Agent '{agent.name}' queued message to room {room_id}")

                elif action_type == "set_attention":
                    # Deprecated action - no longer supported
                    action_result = "error: set_attention is no longer supported"

                elif action_type == "allocate":
                    # Deprecated action - no longer supported  
                    action_result = "error: allocate is no longer supported"

                elif action_type == "react":
                    # Deprecated action - no longer supported
                    action_result = "error: react is no longer supported"

                elif action_type == "reply":
                    # Deprecated action - no longer supported
                    action_result = "error: reply is no longer supported"

                elif action_type in ["leave_room", "room.leave"]:
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

                elif action_type in ["set_billboard", "room.billboard"]:
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

                elif action_type in ["clear_billboard", "room.billboard.clear"]:
                    # Clear billboard for agent's own room
                    if not hasattr(agent, '_pending_billboard_action'):
                        agent._pending_billboard_action = None
                    agent._pending_billboard_action = {"action": "clear"}
                    applied += 1
                    action_result = "queued"
                    logger.debug(f"Agent '{agent.name}' clearing billboard")

                elif action_type in ["wake_agent", "agent.wake"]:
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

                elif action_type in ["set_wpm", "room.wpm"]:
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

                elif action_type in ["set_name", "identity.name"]:
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

                elif action_type in ["create_agent", "agent.create"]:
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

                elif action_type in ["alter_agent", "agent.alter"]:
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

                elif action_type in ["retire_agent", "agent.retire"]:
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

                elif action_type in ["sleep", "timing.sleep"]:
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
