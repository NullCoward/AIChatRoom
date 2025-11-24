"""HUD (Heads-Up Display) service for building agent context with dynamic token budgeting."""

import json
import re
from datetime import datetime
from typing import List, Optional, Tuple, Dict, Any
from models import AIAgent, ChatMessage, ChatRoom, RoomMembership, SelfConcept
from .logging_config import get_logger
import config
import prompts

logger = get_logger("hud")


class HUDService:
    """Builds and manages agent HUD (context) with dynamic token budgeting."""

    def __init__(self):
        """Initialize HUD service."""
        # Store recent actions per agent: {agent_id: [{"timestamp": ..., "action": ...}]}
        self._recent_actions: Dict[int, List[Dict[str, Any]]] = {}
        self._max_recent_actions = 20  # Keep last 20 actions per agent

    def _record_action(self, agent_id: int, action: Dict[str, Any]) -> None:
        """Record an action in the agent's recent actions history."""
        if agent_id not in self._recent_actions:
            self._recent_actions[agent_id] = []

        # Create a simplified summary of the action
        action_type = action.get("type", "") or action.get("action", "")
        summary = {"type": action_type, "timestamp": datetime.utcnow().isoformat()}

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
                "_description": "Manage your private knowledge store using dot-path notation",
                "actions": [
                    {"type": "set", "path": "dot.path", "value": "any", "w": "0.0-1.0 (optional weight)"},
                    {"type": "delete", "path": "dot.path"},
                    {"type": "append", "path": "dot.path", "value": "any"}
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

            "attention": {
                "_description": "Allocate attention across rooms. Use '%*' for dynamic sizing.",
                "actions": [
                    {"type": "set_attention", "room_id": "int", "value": "percent_or_%*"}
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
                        "model": "string (optional, e.g. gpt-4o-mini, gpt-4o)"
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
        Build HUD JSON for an agent with multiple rooms.

        room_data is a list of dicts with:
        - room: ChatRoom
        - membership: RoomMembership
        - messages: List[ChatMessage]
        - members: List[str] (agent names)
        - word_budget: int

        Returns (hud_json, tokens_used).
        """
        # Get agent's self-concept
        self_concept = SelfConcept.from_json(agent.self_concept_json)
        knowledge_dict = self_concept.to_dict()

        # Calculate knowledge store size
        knowledge_tokens = self.estimate_json_tokens(knowledge_dict)
        knowledge_pct = min(100, int((knowledge_tokens / config.SELF_META_MAX) * 100))

        # Get recent actions for this agent
        recent_actions = self.get_recent_actions(agent.id)

        # Build self section - separate identity (system) from knowledge (user-managed)
        # Identity structure differs based on agent type
        if agent.agent_type == "bot":
            identity = {
                "id": agent.id,  # Your permanent identifier
                "name": agent.name or f"Bot-{agent.id}",  # Display name (defaults to ID)
                "model": agent.model,  # Your AI model (e.g. gpt-4o-mini)
                "role": agent.background_prompt  # Your designated purpose/function
            }
        else:
            identity = {
                "id": agent.id,  # Your permanent ID - this is how others identify you
                "name": agent.name,  # Your display name (change with set_name action)
                "model": agent.model,  # Your AI model (e.g. gpt-4o-mini)
                "seed": agent.background_prompt  # Your starting personality/background
            }

        self_section = {
            "identity": identity,
            "knowledge": knowledge_dict,  # Your private memory store
            "memory_used": f"{knowledge_pct}%",
            "recent_actions": recent_actions  # Your recent actions with timestamps
        }

        # Build system section with directives for all agent types
        system_section = {
            "directives": self.build_system_directives()
        }

        # Build meta section with instructions and available actions
        logger.info(f"Building HUD for agent {agent.id} ({agent.name}): can_create_agents={agent.can_create_agents}")
        meta_section = {
            "instructions": self.build_meta_instructions(agent.agent_type),
            "available_actions": self.build_available_actions(agent.agent_type, agent.can_create_agents)
        }

        # Calculate tokens for system + self + meta (capped at 50% of total)
        static_content = {
            "system": system_section,
            "self": self_section,
            "meta": meta_section
        }
        static_tokens = self.estimate_json_tokens(static_content)
        static_tokens = min(static_tokens, config.STATIC_CONTENT_MAX)

        # Remaining tokens for room messages (guaranteed at least 50% of total)
        remaining_tokens = max(
            config.TOTAL_TOKEN_BUDGET - static_tokens,
            config.MESSAGE_CONTENT_MIN
        )

        # Build rooms section with token budget per room
        rooms_section = self._build_rooms_section(room_data, remaining_tokens)

        # Assemble complete HUD
        hud = {
            "system": system_section,
            "self": self_section,
            "meta": meta_section,
            "rooms": rooms_section
        }

        hud_json = json.dumps(hud, indent=2)
        total_tokens = self.estimate_tokens(hud_json)

        logger.debug(f"Built HUD for '{agent.name}': {total_tokens} tokens ({len(rooms_section)} rooms)")

        return hud_json, total_tokens

    def _build_rooms_section(
        self,
        room_data: List[Dict[str, Any]],
        token_budget: int
    ) -> List[Dict[str, Any]]:
        """Build rooms section within token budget using attention allocation."""
        if not room_data:
            return []

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
            room_messages = self._build_messages_section(
                messages,
                room_budget - 200,
                agent_id=agent_id,
                reactions_map=reactions_map
            )

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

        return rooms

    def _build_messages_section(
        self,
        messages: List[ChatMessage],
        token_budget: int,
        agent_id: int = 0,
        reactions_map: Dict[int, Dict[str, int]] = None
    ) -> List[Dict[str, Any]]:
        """Build messages section within token budget, taking most recent that fit.

        All agents are shown by their ID number so they can recognize their own messages.
        Includes message IDs and reactions for reaction support.
        """
        if not messages:
            return []

        result = []
        tokens_used = 0
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
                break

        return result

    def parse_response(self, response_text: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Parse agent's JSON response into room responses and actions.
        Returns (room_responses, actions).

        room_responses: [{"room_id": 1, "message": "..."}, ...]
        actions: [{"type": "add_fact", ...}, ...]
        """
        if not response_text:
            return [], []

        # Try to extract JSON from response
        try:
            data = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to find JSON block in response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                try:
                    data = json.loads(json_match.group())
                except json.JSONDecodeError:
                    logger.warning(f"Could not parse JSON from response")
                    return [], []
            else:
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
        """
        if not actions:
            return 0

        self_concept = SelfConcept.from_json(agent.self_concept_json)
        applied = 0

        for action in actions:
            # Support both "type" and "action" keys for backward compatibility
            action_type = action.get("type", "") or action.get("action", "")

            # Skip empty or malformed actions silently
            if not action_type:
                continue

            action_applied = False
            try:
                # Knowledge management actions (dot-path operations)
                if action_type == "set":
                    path = action.get("path", "")
                    value = action.get("value")
                    weight = action.get("w")
                    if path and value is not None:
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
                            action_applied = True
                            logger.debug(f"Agent '{agent.name}' set {path}")

                elif action_type == "delete":
                    path = action.get("path", "")
                    if path and self_concept.delete(path):
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' deleted {path}")

                elif action_type == "append":
                    path = action.get("path", "")
                    value = action.get("value")
                    if path and value is not None:
                        if self_concept.append(path, value):
                            applied += 1
                            action_applied = True
                            logger.debug(f"Agent '{agent.name}' appended to {path}")

                elif action_type == "react":
                    # React to a message
                    message_id = action.get("message_id")
                    reaction = action.get("reaction", "")
                    valid_reactions = ["thumbs_up", "thumbs_down", "brain", "heart"]
                    if message_id is not None and reaction in valid_reactions:
                        if not hasattr(agent, '_pending_reactions'):
                            agent._pending_reactions = []
                        agent._pending_reactions.append({
                            "message_id": message_id,
                            "reaction": reaction
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' reacting to message {message_id} with {reaction}")

                elif action_type == "set_attention":
                    # Set attention percentage for a room
                    # {"type": "set_attention", "room_id": 5, "value": "20%"} or "value": "%*"
                    room_id = action.get("room_id")
                    value = action.get("value", "")
                    if room_id is not None:
                        # Store in agent's pending attention changes
                        # These will be applied by the heartbeat service
                        if not hasattr(agent, '_pending_attention'):
                            agent._pending_attention = []
                        agent._pending_attention.append({
                            "room_id": room_id,
                            "value": value
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' set attention for room {room_id} to {value}")

                elif action_type == "create_key":
                    # Create a key for the agent's room
                    key_value = action.get("key", "")
                    if key_value:
                        if not hasattr(agent, '_pending_key_actions'):
                            agent._pending_key_actions = []
                        agent._pending_key_actions.append({
                            "action": "create",
                            "key": key_value
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' creating key: {key_value}")

                elif action_type == "revoke_key":
                    # Revoke a key for the agent's room
                    key_value = action.get("key", "")
                    if key_value:
                        if not hasattr(agent, '_pending_key_actions'):
                            agent._pending_key_actions = []
                        agent._pending_key_actions.append({
                            "action": "revoke",
                            "key": key_value
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' revoking key: {key_value}")

                elif action_type == "request_access":
                    # Request to join another agent's room
                    room_id = action.get("room_id")
                    key_value = action.get("key", "")
                    if room_id is not None and key_value:
                        if not hasattr(agent, '_pending_access_actions'):
                            agent._pending_access_actions = []
                        agent._pending_access_actions.append({
                            "action": "request",
                            "room_id": room_id,
                            "key": key_value
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' requesting access to room {room_id}")

                elif action_type == "grant_access":
                    # Grant a pending access request
                    request_id = action.get("request_id")
                    if request_id is not None:
                        if not hasattr(agent, '_pending_access_actions'):
                            agent._pending_access_actions = []
                        agent._pending_access_actions.append({
                            "action": "grant",
                            "request_id": request_id
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' granting request {request_id}")

                elif action_type == "deny_access":
                    # Deny a pending access request
                    request_id = action.get("request_id")
                    if request_id is not None:
                        if not hasattr(agent, '_pending_access_actions'):
                            agent._pending_access_actions = []
                        agent._pending_access_actions.append({
                            "action": "deny",
                            "request_id": request_id
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' denying request {request_id}")

                elif action_type == "leave_room":
                    # Leave a room
                    room_id = action.get("room_id")
                    if room_id is not None:
                        if not hasattr(agent, '_pending_room_actions'):
                            agent._pending_room_actions = []
                        agent._pending_room_actions.append({
                            "action": "leave",
                            "room_id": room_id
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' leaving room {room_id}")

                elif action_type == "set_billboard":
                    # Set billboard for agent's own room
                    message = action.get("message", "")
                    if not hasattr(agent, '_pending_billboard_action'):
                        agent._pending_billboard_action = None
                    agent._pending_billboard_action = {"action": "set", "message": message}
                    applied += 1
                    action_applied = True
                    logger.debug(f"Agent '{agent.name}' setting billboard: {message[:50]}...")

                elif action_type == "clear_billboard":
                    # Clear billboard for agent's own room
                    if not hasattr(agent, '_pending_billboard_action'):
                        agent._pending_billboard_action = None
                    agent._pending_billboard_action = {"action": "clear"}
                    applied += 1
                    action_applied = True
                    logger.debug(f"Agent '{agent.name}' clearing billboard")

                elif action_type == "wake_agent":
                    # Wake a sleeping agent (requires room proximity)
                    target_id = action.get("agent_id")
                    if target_id is not None:
                        if not hasattr(agent, '_pending_wake_agents'):
                            agent._pending_wake_agents = []
                        agent._pending_wake_agents.append(target_id)
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' waking agent {target_id}")

                elif action_type == "reply":
                    # Reply to a specific message
                    room_id = action.get("room_id")
                    message_id = action.get("message_id")
                    message = action.get("message", "").strip()
                    if room_id is not None and message_id is not None and message:
                        if not hasattr(agent, '_pending_replies'):
                            agent._pending_replies = []
                        agent._pending_replies.append({
                            "room_id": room_id,
                            "reply_to_id": message_id,
                            "message": message
                        })
                        applied += 1
                        action_applied = True
                        logger.debug(f"Agent '{agent.name}' replying to message {message_id} in room {room_id}")

                elif action_type == "set_wpm":
                    # Set WPM for agent's own room
                    wpm = action.get("wpm")
                    if wpm is not None:
                        try:
                            wpm = int(wpm)
                            wpm = max(10, min(200, wpm))  # Clamp to 10-200
                            agent.room_wpm = wpm
                            applied += 1
                            action_applied = True
                            logger.debug(f"Agent '{agent.name}' set room WPM to {wpm}")
                        except (ValueError, TypeError):
                            logger.warning(f"Invalid WPM value: {wpm}")

                elif action_type == "set_name":
                    # Set agent's display name
                    new_name = action.get("name", "").strip()
                    if new_name and len(new_name) <= 50:  # Reasonable name length
                        old_name = agent.name
                        agent.name = new_name
                        applied += 1
                        action_applied = True
                        logger.info(f"Agent {agent.id} renamed from '{old_name}' to '{new_name}'")
                    else:
                        logger.warning(f"Invalid name: '{new_name}' (must be 1-50 chars)")

                elif action_type == "create_agent":
                    # Create a new agent (requires permission)
                    if not agent.can_create_agents:
                        logger.warning(f"Agent {agent.id} tried to create agent but lacks permission")
                    else:
                        name = action.get("name", "").strip()
                        background_prompt = action.get("background_prompt", "").strip()
                        new_agent_type = action.get("agent_type", "persona")
                        in_room_id = action.get("in_room_id")

                        if name and background_prompt:
                            if not hasattr(agent, '_pending_create_agents'):
                                agent._pending_create_agents = []
                            agent._pending_create_agents.append({
                                "name": name,
                                "background_prompt": background_prompt,
                                "agent_type": new_agent_type if new_agent_type in ["persona", "bot"] else "persona",
                                "in_room_id": in_room_id
                            })
                            applied += 1
                            action_applied = True
                            logger.debug(f"Agent '{agent.name}' creating new agent: {name}")
                        else:
                            logger.warning(f"Invalid create_agent action: name and background_prompt required")

                elif action_type == "alter_agent":
                    # Alter another agent's persona (requires permission)
                    if not agent.can_create_agents:
                        logger.warning(f"Agent {agent.id} tried to alter agent but lacks permission")
                    else:
                        target_id = action.get("agent_id")
                        new_name = action.get("name", "").strip() if action.get("name") else None
                        new_prompt = action.get("background_prompt", "").strip() if action.get("background_prompt") else None
                        new_model = action.get("model", "").strip() if action.get("model") else None

                        if target_id is None:
                            logger.warning(f"Invalid alter_agent action: agent_id required")
                        elif target_id == agent.id:
                            logger.warning(f"Agent {agent.id} tried to alter themselves - use set_name or knowledge instead")
                        elif not new_name and not new_prompt and not new_model:
                            logger.warning(f"Invalid alter_agent action: at least one of name, background_prompt, or model required")
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
                            action_applied = True
                            logger.debug(f"Agent '{agent.name}' altering agent {target_id}")

                elif action_type == "retire_agent":
                    # Retire (delete) another agent (requires permission)
                    if not agent.can_create_agents:
                        logger.warning(f"Agent {agent.id} tried to retire agent but lacks permission")
                    else:
                        target_id = action.get("agent_id")
                        if target_id is None:
                            logger.warning(f"Invalid retire_agent action: agent_id required")
                        elif target_id == agent.id:
                            logger.warning(f"Agent {agent.id} tried to retire themselves")
                        else:
                            if not hasattr(agent, '_pending_retire_agents'):
                                agent._pending_retire_agents = []
                            agent._pending_retire_agents.append(target_id)
                            applied += 1
                            action_applied = True
                            logger.debug(f"Agent '{agent.name}' retiring agent {target_id}")

                elif action_type == "sleep":
                    # Sleep until a specific time
                    until_str = action.get("until", "")
                    if until_str:
                        try:
                            sleep_until = datetime.fromisoformat(until_str.replace('Z', '+00:00'))
                            # Store as pending sleep action
                            if not hasattr(agent, '_pending_sleep'):
                                agent._pending_sleep = None
                            agent._pending_sleep = sleep_until
                            applied += 1
                            action_applied = True
                            logger.debug(f"Agent '{agent.name}' sleeping until {until_str}")
                        except ValueError:
                            logger.warning(f"Invalid sleep until datetime: {until_str}")
                    else:
                        logger.warning(f"Invalid sleep action: until datetime required")

                else:
                    logger.warning(f"Unknown action type: {action_type}")

                # Record successful actions
                if action_applied:
                    self._record_action(agent.id, action)

            except Exception as e:
                logger.error(f"Error applying action {action_type}: {e}")

        # Save updated self-concept
        agent.self_concept_json = self_concept.to_json()

        if applied > 0:
            logger.info(f"Agent '{agent.name}' applied {applied} actions to self-concept")

        return applied
