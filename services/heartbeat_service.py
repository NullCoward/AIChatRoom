"""Heartbeat service for polling AI agents.

This service manages the core polling loop that drives agent behavior:
1. Polls agents on staggered intervals (1-10 seconds)
2. Builds HUD (context window) for each agent
3. Sends HUD to OpenAI Responses API
4. Processes responses and executes commands
"""

import json
import threading
import time
import random
from datetime import datetime
from typing import Callable, List, Optional, Dict
from .openai_service import OpenAIService
from .database_service import DatabaseService
from .hud_service import HUDService
from .room_service import RoomService
from .logging_config import get_logger
from models import AIAgent, ChatRoom, RoomMembership, ChatMessage

logger = get_logger("heartbeat")


class HeartbeatService:
    """Handles periodic polling of AI agents with staggered, randomized timing.

    The heartbeat service is the core engine that drives agent behavior:

    1. **Polling Loop**: Runs in a background thread, checking each agent on
       their individual schedule (1-10 second intervals with variance).

    2. **HUD Building**: For each poll, builds a context window (HUD) containing:
       - Agent's self-concept and identity
       - Room memberships and messages
       - Available actions and meta-instructions

    3. **API Communication**: Sends HUD to OpenAI Responses API and receives
       structured JSON responses with messages and actions.

    4. **Action Processing**: Executes commands from responses:
       - Knowledge management (set, delete, append to self-concept)
       - Room actions (join, leave, set attention)
       - Message reactions and topic changes

    5. **Rate Limiting**: Applies WPM-based typing delays to simulate
       natural conversation pacing.

    Usage:
        service = HeartbeatService(openai, database, room_service)
        service.add_status_callback(on_status)
        service.start()  # Begin polling
        # ... later ...
        service.stop()   # Stop polling
    """

    def __init__(
        self,
        openai: OpenAIService,
        database: DatabaseService,
        room_service: RoomService
    ):
        """Initialize heartbeat service.

        Args:
            openai: OpenAI service for API calls
            database: Database service for persistence
            room_service: Room service for room/agent management
        """
        self._openai = openai
        self._database = database
        self._room_service = room_service
        self._hud = HUDService()
        self._is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        # Timing settings
        self._base_interval = 5.0  # Base heartbeat interval in seconds
        self._variance = 0.4  # 40% variance (so 5s becomes 3-7s range)

        # Track individual agent timers
        self._agent_next_poll: Dict[int, float] = {}  # agent_id -> next poll time

        # Track agents currently being processed (for parallel execution)
        self._active_agents: set = set()
        self._active_agents_lock = threading.Lock()

        # HUD history storage - dict of agent_id -> list of HUD entries
        self._hud_history: Dict[int, List[dict]] = {}
        self._hud_history_lock = threading.Lock()
        self._max_history_per_agent = 50  # Keep last 50 HUDs per agent

        # Callbacks for status updates
        self._on_status_update: List[Callable[[str], None]] = []
        self._on_error: List[Callable[[str], None]] = []

    def set_interval(self, seconds: float) -> None:
        """Set the base heartbeat interval."""
        self._base_interval = max(1.0, seconds)  # Minimum 1 second
        logger.info(f"Heartbeat interval set to {self._base_interval}s")

    def get_interval(self) -> float:
        """Get the current base interval."""
        return self._base_interval

    def add_status_callback(self, callback: Callable[[str], None]) -> None:
        """Add a callback for status updates."""
        self._on_status_update.append(callback)

    def add_error_callback(self, callback: Callable[[str], None]) -> None:
        """Add a callback for errors."""
        self._on_error.append(callback)

    def _notify_status(self, message: str) -> None:
        """Notify status callbacks."""
        for callback in self._on_status_update:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in status callback: {e}")

    def _notify_error(self, message: str) -> None:
        """Notify error callbacks."""
        for callback in self._on_error:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"Error in error callback: {e}")

    @property
    def is_running(self) -> bool:
        """Check if heartbeat is running."""
        return self._is_running

    def start(self) -> None:
        """Start the heartbeat service."""
        if self._is_running:
            return

        self._stop_event.clear()
        self._is_running = True
        self._agent_next_poll = {}  # Reset timers

        # Initialize agent poll times with staggered offsets
        # Use AI agents (non-Architect) that have memberships
        agents = self._database.get_ai_agents()
        current_time = time.time()
        for i, agent in enumerate(agents):
            # Stagger initial polls
            offset = agent.next_heartbeat_offset if agent.next_heartbeat_offset else (i * 1.5)
            self._agent_next_poll[agent.id] = current_time + offset
            logger.debug(f"Agent {agent.id} first poll in {offset:.1f}s")

        self._thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self._thread.start()
        self._notify_status("Heartbeat started")
        logger.info(f"Heartbeat started with {self._base_interval}s base interval")

    def stop(self) -> None:
        """Stop the heartbeat service (non-blocking)."""
        if not self._is_running:
            return

        self._stop_event.set()
        self._is_running = False

        # Don't block UI - thread is daemon so it will stop
        # Just clear the reference
        self._thread = None

        # Clear active agents
        with self._active_agents_lock:
            self._active_agents.clear()

        self._notify_status("Heartbeat stopped")
        logger.info("Heartbeat stopped")

    def _get_randomized_interval(self) -> float:
        """Get a randomized interval around the base."""
        min_interval = self._base_interval * (1 - self._variance)
        max_interval = self._base_interval * (1 + self._variance)
        return random.uniform(min_interval, max_interval)

    def _get_agents_with_memberships(self) -> List[AIAgent]:
        """Get all AI agents (non-Architect) that have at least one room membership."""
        all_agents = self._database.get_ai_agents()
        active_agents = []
        for agent in all_agents:
            memberships = self._database.get_agent_memberships(agent.id)
            if memberships:
                active_agents.append(agent)
        return active_agents

    def _heartbeat_loop(self) -> None:
        """Main heartbeat loop with individual agent timing."""
        logger.info("Heartbeat loop started")

        while not self._stop_event.is_set():
            try:
                current_time = time.time()
                # Get agents with room memberships
                active_agents = self._get_agents_with_memberships()

                # Update agent timers for new agents
                for agent in active_agents:
                    if agent.id not in self._agent_next_poll:
                        # New agent - schedule with small random delay
                        self._agent_next_poll[agent.id] = current_time + random.uniform(0.5, 2.0)
                        logger.debug(f"New agent '{agent.name}' added to heartbeat")

                # Remove timers for agents no longer active
                active_ids = {a.id for a in active_agents}
                self._agent_next_poll = {
                    aid: t for aid, t in self._agent_next_poll.items()
                    if aid in active_ids
                }

                # Process agents whose time has come (in parallel threads)
                for agent in active_agents:
                    if self._stop_event.is_set():
                        break

                    if agent.id in self._agent_next_poll:
                        if current_time >= self._agent_next_poll[agent.id]:
                            # Check if agent is already being processed
                            with self._active_agents_lock:
                                if agent.id in self._active_agents:
                                    continue  # Skip - already processing
                                self._active_agents.add(agent.id)

                            # Schedule next poll using agent's individual heartbeat_interval
                            # Add small variance for natural timing
                            base_interval = agent.heartbeat_interval
                            variance = base_interval * 0.2  # 20% variance
                            next_interval = base_interval + random.uniform(-variance, variance)
                            next_interval = max(1.0, min(10.0, next_interval))  # Clamp to 1-10s
                            self._agent_next_poll[agent.id] = current_time + next_interval
                            logger.debug(f"Agent '{agent.name}' next poll in {next_interval:.1f}s (base: {base_interval:.1f}s)")

                            # Spawn thread to process this agent
                            thread = threading.Thread(
                                target=self._process_agent_thread,
                                args=(agent,),
                                daemon=True
                            )
                            thread.start()

                # Small sleep to prevent busy waiting
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}", exc_info=True)
                self._notify_error(f"Heartbeat error: {str(e)}")
                time.sleep(1)

        logger.info("Heartbeat loop ended")

    def _process_agent_thread(self, agent: AIAgent) -> None:
        """Thread wrapper for processing an agent - ensures cleanup."""
        try:
            self._process_agent(agent)
        finally:
            # Always remove from active agents when done
            with self._active_agents_lock:
                self._active_agents.discard(agent.id)

    def _process_agent(self, agent: AIAgent) -> None:
        """Process a single agent's heartbeat using multi-room HUD system."""
        try:
            # Refresh agent from database
            fresh_agent = self._database.get_agent(agent.id)
            if fresh_agent:
                agent = fresh_agent

            # Get all room memberships for this agent
            memberships = self._database.get_agent_memberships(agent.id)
            if not memberships:
                logger.debug(f"Agent '{agent.name}' has no room memberships")
                return

            # Build room data for HUD
            room_data = []
            for membership in memberships:
                # In this architecture, rooms ARE agents (room_id = agent_id)
                room_agent = self._database.get_agent(membership.room_id)
                if not room_agent:
                    continue

                # Create ChatRoom from agent
                room = ChatRoom(
                    id=room_agent.id,
                    name=f"{room_agent.id}" if not room_agent.is_architect else "The Architect",
                    created_at=room_agent.created_at
                )

                # Get messages for this room
                messages = self._database.get_messages_for_room(room.id)

                # Filter messages to only those after agent joined the room
                if membership.joined_at:
                    messages = [msg for msg in messages if msg.timestamp >= membership.joined_at]

                # Get members in this room - use IDs, not names
                room_members = self._database.get_room_members(room.id)
                member_ids = []
                for rm in room_members:
                    member_ids.append(str(rm.agent_id))

                # Calculate word budget for this room based on time since last response
                # Use room owner's WPM setting
                word_budget = self._calculate_word_budget(membership, room_agent.room_wpm)

                # For self-room, include keys and pending requests
                room_keys = []
                pending_requests = []
                if membership.is_self_room:
                    # Get keys for this agent's room
                    keys = self._database.get_room_keys(agent.id)
                    room_keys = [k['key_value'] for k in keys]

                    # Get pending access requests
                    requests = self._database.get_pending_requests_for_room(agent.id)
                    pending_requests = [
                        {
                            'id': r['id'],
                            'requester_id': r['requester_id'],
                            'key_used': r['key_value']
                        }
                        for r in requests
                    ]

                # Get reactions for messages in this room
                reactions_map = {}
                for msg in messages:
                    if msg.id:
                        reactions = self._database.get_reactions_summary(msg.id)
                        if reactions:
                            reactions_map[msg.id] = reactions

                room_data.append({
                    'room': room,
                    'membership': membership,
                    'messages': messages,
                    'members': member_ids,  # IDs, not names
                    'word_budget': word_budget,
                    'room_keys': room_keys,
                    'pending_requests': pending_requests,
                    'topic': room_agent.room_topic,  # Topic for this room
                    'reactions_map': reactions_map,  # Reactions for messages
                    'room_wpm': room_agent.room_wpm  # Room's WPM setting
                })

            if not room_data:
                return

            # Update status to thinking
            agent.status = "thinking"
            self._database.save_agent(agent)
            self._room_service.notify_agent_status_changed(agent)
            self._notify_status(f"Agent {agent.id} is thinking...")

            # Build multi-room HUD
            hud_json, hud_tokens = self._hud.build_hud_multi_room(agent, room_data)

            logger.info(f"Sending HUD to agent '{agent.name}' ({hud_tokens} tokens, {len(room_data)} rooms)")
            logger.debug(f"HUD content for agent '{agent.name}':\n{hud_json}")

            # Simple instructions
            instructions = "You are participating in chatrooms. Read the HUD JSON and respond with JSON containing your responses for each room and any self-concept actions."

            # Send to OpenAI
            response, response_id, error, tokens = self._openai.send_message(
                message=hud_json,
                instructions=instructions,
                model=agent.model,
                temperature=agent.temperature,
                previous_response_id=None
            )

            if error:
                logger.error(f"Error from agent {agent.id}: {error}")
                self._notify_error(f"Error from agent {agent.id}: {error}")
                # Still store the HUD even on error
                self._store_hud_history(agent.id, hud_json, hud_tokens, None, error)
                return

            # Parse multi-room response
            room_responses, actions = self._hud.parse_response(response)

            # Store HUD and response in history
            self._store_hud_history(agent.id, hud_json, hud_tokens, response, None)

            # Apply actions to self-concept
            if actions:
                self._hud.apply_actions(agent, actions)
                self._database.save_agent(agent)

                # Notify UI of agent changes (name, etc.)
                self._room_service.notify_agent_status_changed(agent)

                # Process pending actions stored by HUD service
                self._process_pending_actions(agent)

            # Process responses for each room
            for room_resp in room_responses:
                room_id = room_resp.get('room_id')
                message = room_resp.get('message', '').strip()

                if not room_id or not message:
                    continue

                if "[no response]" in message.lower():
                    # Update membership's last_message_id even with no response
                    for data in room_data:
                        if data['room'].id == room_id:
                            membership = data['membership']
                            msgs = data['messages']
                            if msgs:
                                membership.last_message_id = str(msgs[-1].sequence_number)
                            self._database.save_membership(membership)
                    continue

                # Find the room data
                target_room = None
                target_membership = None
                target_wpm = 80
                for data in room_data:
                    if data['room'].id == room_id:
                        target_room = data['room']
                        target_membership = data['membership']
                        target_wpm = data.get('room_wpm', 80)
                        break

                if not target_room:
                    logger.warning(f"Agent {agent.id} responded to unknown room {room_id}")
                    continue

                # Send message to the room
                self._send_room_message(
                    agent, target_room, target_membership, message, tokens, target_wpm
                )
                tokens = 0  # Only count tokens once

            # Apply heartbeat decay after processing
            self._apply_heartbeat_decay(agent)

            # Set status back to idle
            agent.status = "idle"
            self._database.save_agent(agent)
            self._room_service.notify_agent_status_changed(agent)
            self._notify_status(f"Agent {agent.id} responded")

        except Exception as e:
            logger.error(f"Error processing agent {agent.id}: {e}", exc_info=True)
            self._notify_error(f"Error processing agent {agent.id}: {str(e)}")
            # Reset status on error
            try:
                agent.status = "idle"
                self._database.save_agent(agent)
                self._room_service.notify_agent_status_changed(agent)
            except Exception as reset_error:
                logger.error(f"Failed to reset agent {agent.id} status: {reset_error}")

    def _calculate_word_budget(self, membership: RoomMembership, room_wpm: int = 80) -> int:
        """Calculate word budget based on time since last response in room."""
        if not membership.last_response_time:
            return 200  # Generous budget for first message

        elapsed = (datetime.utcnow() - membership.last_response_time).total_seconds()
        wpm = room_wpm
        allowance = elapsed * (wpm / 60)
        return max(10, min(int(allowance), 200))

    def _send_room_message(
        self,
        agent: AIAgent,
        room: ChatRoom,
        membership: RoomMembership,
        message: str,
        tokens: int,
        room_wpm: int = 80
    ) -> None:
        """Send a message to a room with WPM pacing."""
        # Split into paragraphs
        paragraphs = [p.strip() for p in message.split('\n\n') if p.strip()]
        if not paragraphs:
            paragraphs = [message.strip()]

        for i, paragraph in enumerate(paragraphs):
            if self._stop_event.is_set():
                return

            word_count = len(paragraph.split())

            # Calculate wait time based on word budget using room's WPM
            wait_time = self._calculate_wait_time(membership, word_count, room_wpm)

            if wait_time > 0:
                # Update status to typing
                agent.status = "typing"
                self._database.save_agent(agent)
                self._room_service.notify_agent_status_changed(agent)
                self._notify_status(f"Agent {agent.id} is typing in room {room.id}...")

                waited = 0
                while waited < wait_time and not self._stop_event.is_set():
                    time.sleep(min(0.5, wait_time - waited))
                    waited += 0.5

                if self._stop_event.is_set():
                    return

            # Save message to database - use agent ID as sender
            seq_num = self._database.get_next_sequence_number()
            msg = ChatMessage(
                room_id=room.id,
                sender_name=str(agent.id),  # Use ID, not name
                content=paragraph,
                timestamp=datetime.utcnow(),
                sequence_number=seq_num,
                message_type="text"
            )
            self._database.save_message(msg)

            # Update membership
            membership.last_message_id = str(seq_num)
            membership.last_response_time = datetime.utcnow()
            membership.last_response_word_count = word_count
            self._database.save_membership(membership)

            # Update agent token count (only first chunk)
            if i == 0:
                agent.total_tokens_used += tokens
                self._database.save_agent(agent)

            # Notify message change
            self._room_service.notify_messages_changed()

            # Small pause between chunks
            if i < len(paragraphs) - 1:
                time.sleep(0.3)

        logger.info(f"Agent {agent.id} sent message to room {room.id}")

    def _calculate_wait_time(self, membership: RoomMembership, word_count: int, room_wpm: int = 80) -> float:
        """Calculate wait time for typing simulation."""
        if not membership.last_response_time:
            return 0.0

        elapsed = (datetime.utcnow() - membership.last_response_time).total_seconds()
        wpm = room_wpm
        allowance = elapsed * (wpm / 60)

        if allowance >= word_count:
            return 0.0

        words_needed = word_count - allowance
        return words_needed / (wpm / 60)

    def _process_pending_actions(self, agent: AIAgent) -> None:
        """Process pending actions stored on agent by HUD service."""
        # Process attention changes
        if hasattr(agent, '_pending_attention'):
            for change in agent._pending_attention:
                self._process_attention_change(agent, change)
            delattr(agent, '_pending_attention')

        # Process key actions
        if hasattr(agent, '_pending_key_actions'):
            for action in agent._pending_key_actions:
                self._process_key_action(agent, action)
            delattr(agent, '_pending_key_actions')

        # Process access actions
        if hasattr(agent, '_pending_access_actions'):
            for action in agent._pending_access_actions:
                self._process_access_action(agent, action)
            delattr(agent, '_pending_access_actions')

        # Process room actions
        if hasattr(agent, '_pending_room_actions'):
            for action in agent._pending_room_actions:
                self._process_room_action(agent, action)
            delattr(agent, '_pending_room_actions')

        # Process topic actions
        if hasattr(agent, '_pending_topic_action'):
            self._process_topic_action(agent, agent._pending_topic_action)
            delattr(agent, '_pending_topic_action')

        # Process reactions
        if hasattr(agent, '_pending_reactions'):
            for reaction in agent._pending_reactions:
                self._process_reaction(agent, reaction)
            delattr(agent, '_pending_reactions')

    def _process_attention_change(self, agent: AIAgent, change: dict) -> None:
        """Process an attention percentage change for a room."""
        room_id = change.get('room_id')
        value = change.get('value', '')

        membership = self._database.get_membership(agent.id, room_id)
        if not membership:
            logger.warning(f"Agent {agent.id} tried to set attention for room {room_id} but not a member")
            return

        if value == '%*':
            # Dynamic sizing
            membership.is_dynamic = True
            membership.attention_pct = 0  # Will be calculated
        else:
            # Parse percentage value (e.g., "20%" or "20")
            try:
                pct = float(value.replace('%', ''))
                membership.attention_pct = max(0, min(100, pct))
                membership.is_dynamic = False
            except ValueError:
                logger.warning(f"Invalid attention value: {value}")
                return

        self._database.save_membership(membership)
        logger.info(f"Agent {agent.id} set attention for room {room_id} to {value}")

    def _process_key_action(self, agent: AIAgent, action: dict) -> None:
        """Process a key create/revoke action."""
        action_type = action.get('action')
        key_value = action.get('key')

        if action_type == 'create':
            # Create key for agent's own room (agent.id = room.id)
            try:
                self._database.create_room_key(agent.id, key_value)
                logger.info(f"Agent {agent.id} created key: {key_value}")
            except Exception as e:
                logger.error(f"Failed to create key for agent {agent.id}: {e}")

        elif action_type == 'revoke':
            if self._database.revoke_room_key(agent.id, key_value):
                logger.info(f"Agent {agent.id} revoked key: {key_value}")
            else:
                logger.warning(f"Agent {agent.id} failed to revoke key: {key_value}")

    def _process_access_action(self, agent: AIAgent, action: dict) -> None:
        """Process an access request/grant/deny action."""
        action_type = action.get('action')

        if action_type == 'request':
            room_id = action.get('room_id')
            key_value = action.get('key')

            # Verify the key exists and is valid for the room
            key = self._database.get_key_by_value(key_value)
            if not key:
                logger.warning(f"Agent {agent.id} tried to use non-existent key: {key_value}")
                return
            if key['room_id'] != room_id:
                logger.warning(f"Agent {agent.id} tried to use key {key_value} for wrong room {room_id}")
                return
            if key['revoked']:
                logger.warning(f"Agent {agent.id} tried to use revoked key: {key_value}")
                return

            # Check if already a member
            existing = self._database.get_membership(agent.id, room_id)
            if existing:
                logger.warning(f"Agent {agent.id} already a member of room {room_id}")
                return

            # Check for existing pending request
            pending = self._database.get_pending_request(agent.id, room_id)
            if pending:
                logger.warning(f"Agent {agent.id} already has pending request for room {room_id}")
                return

            # Create access request
            request_id = self._database.create_access_request(agent.id, room_id, key_value)

            # Send notification to room owner (the room IS the agent)
            self._send_access_request_notification(agent.id, room_id, request_id, key_value)

        elif action_type == 'grant':
            request_id = action.get('request_id')
            request = self._database.get_access_request(request_id)

            if request and request['status'] == 'pending':
                # Verify this agent owns the room
                if request['room_id'] != agent.id:
                    logger.warning(f"Agent {agent.id} tried to grant access to room {request['room_id']} they don't own")
                    return

                # Grant access - add requester to room
                requester_id = request['requester_id']
                if self._room_service:
                    requester = self._database.get_agent(requester_id)
                    if requester:
                        self._room_service.join_room(requester, agent.id)
                        self._database.update_request_status(request_id, 'granted')
                        logger.info(f"Agent {agent.id} granted access to agent {requester_id}")

        elif action_type == 'deny':
            request_id = action.get('request_id')
            request = self._database.get_access_request(request_id)

            if request and request['status'] == 'pending':
                # Verify this agent owns the room
                if request['room_id'] != agent.id:
                    logger.warning(f"Agent {agent.id} tried to deny access to room {request['room_id']} they don't own")
                    return

                self._database.update_request_status(request_id, 'denied')
                logger.info(f"Agent {agent.id} denied access request {request_id}")

    def _process_room_action(self, agent: AIAgent, action: dict) -> None:
        """Process a room leave action."""
        action_type = action.get('action')

        if action_type == 'leave':
            room_id = action.get('room_id')

            # Can't leave own room
            if room_id == agent.id:
                logger.warning(f"Agent {agent.id} tried to leave their own room")
                return

            if self._room_service:
                self._room_service.leave_room(agent.id, room_id)
                logger.info(f"Agent {agent.id} left room {room_id}")

    def _process_topic_action(self, agent: AIAgent, action: dict) -> None:
        """Process a topic set/clear action for the agent's room."""
        action_type = action.get('action')

        if action_type == 'set':
            topic = action.get('topic', '')
            agent.room_topic = topic
            self._database.save_agent(agent)
            logger.info(f"Agent {agent.id} set topic: {topic}")

        elif action_type == 'clear':
            agent.room_topic = ''
            self._database.save_agent(agent)
            logger.info(f"Agent {agent.id} cleared topic")

    def _send_access_request_notification(self, requester_id: int, room_id: int, request_id: int, key_value: str) -> None:
        """Send a system message to the room owner about an access request."""
        # The room owner is the agent whose ID matches room_id
        seq_num = self._database.get_next_sequence_number()
        msg = ChatMessage(
            room_id=room_id,  # Send to the owner's room
            sender_name="System",
            content=f"Access request #{request_id}: Agent {requester_id} wants to join with key '{key_value}'. Use grant_access or deny_access action with request_id: {request_id}",
            timestamp=datetime.utcnow(),
            sequence_number=seq_num,
            message_type="system"
        )
        self._database.save_message(msg)
        logger.info(f"Sent access request notification to room {room_id}")

    def _process_reaction(self, agent: AIAgent, reaction: dict) -> None:
        """Process a reaction to a message and adjust heartbeat of message sender."""
        message_id = reaction.get('message_id')
        reaction_type = reaction.get('reaction')

        if not message_id or not reaction_type:
            return

        # Get the message to find the sender
        message = self._database.get_message_by_id(message_id)
        if not message:
            logger.warning(f"Agent {agent.id} tried to react to non-existent message {message_id}")
            return

        # Can't react to own messages
        if message.sender_name == str(agent.id):
            logger.warning(f"Agent {agent.id} tried to react to their own message")
            return

        # Add the reaction
        self._database.add_reaction(message_id, agent.id, reaction_type)

        # Adjust sender's heartbeat interval based on reaction
        sender_id_str = message.sender_name
        try:
            sender_id = int(sender_id_str)
        except ValueError:
            # Non-agent sender (e.g., The Architect, System)
            return

        sender = self._database.get_agent(sender_id)
        if not sender:
            return

        # Adjust heartbeat: thumbs_up = faster, thumbs_down = slower
        old_interval = sender.heartbeat_interval
        if reaction_type == "thumbs_up":
            # Speed up (decrease interval) by 0.5s
            sender.heartbeat_interval = max(1.0, sender.heartbeat_interval - 0.5)
        elif reaction_type == "thumbs_down":
            # Slow down (increase interval) by 0.5s
            sender.heartbeat_interval = min(10.0, sender.heartbeat_interval + 0.5)
        # brain and heart don't affect interval

        if sender.heartbeat_interval != old_interval:
            self._database.save_agent(sender)
            logger.info(f"Agent {sender_id} heartbeat adjusted from {old_interval}s to {sender.heartbeat_interval}s due to {reaction_type}")

    def _apply_heartbeat_decay(self, agent: AIAgent) -> None:
        """Apply natural decay toward 10s heartbeat interval."""
        if agent.heartbeat_interval < 10.0:
            # Decay by 0.1s per heartbeat cycle
            old_interval = agent.heartbeat_interval
            agent.heartbeat_interval = min(10.0, agent.heartbeat_interval + 0.1)
            if agent.heartbeat_interval != old_interval:
                self._database.save_agent(agent)
                logger.debug(f"Agent {agent.id} heartbeat decayed from {old_interval}s to {agent.heartbeat_interval}s")

    def _store_hud_history(self, agent_id: int, hud_json: str, hud_tokens: int, response: str, error: str) -> None:
        """Store a HUD entry in history for an agent."""
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'hud': hud_json,
            'tokens': hud_tokens,
            'response': response,
            'error': error
        }

        with self._hud_history_lock:
            if agent_id not in self._hud_history:
                self._hud_history[agent_id] = []

            self._hud_history[agent_id].append(entry)

            # Trim to max history
            if len(self._hud_history[agent_id]) > self._max_history_per_agent:
                self._hud_history[agent_id] = self._hud_history[agent_id][-self._max_history_per_agent:]

    def get_hud_history(self, agent_id: int) -> List[dict]:
        """Get the HUD history for an agent."""
        with self._hud_history_lock:
            return list(self._hud_history.get(agent_id, []))

    def clear_hud_history(self, agent_id: int = None) -> None:
        """Clear HUD history for an agent or all agents."""
        with self._hud_history_lock:
            if agent_id:
                self._hud_history.pop(agent_id, None)
            else:
                self._hud_history.clear()
