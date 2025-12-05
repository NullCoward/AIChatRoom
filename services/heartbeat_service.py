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
import config

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

    def set_pull_forward(self, seconds: float) -> None:
        """Set the pull-forward window in seconds.

        When processing a heartbeat, also process any agents whose heartbeats
        are scheduled within this many seconds into the future.
        Set to 0 to disable.
        """
        config.HEARTBEAT_PULL_FORWARD_SECONDS = max(0.0, min(10.0, seconds))
        logger.info(f"Heartbeat pull-forward set to {config.HEARTBEAT_PULL_FORWARD_SECONDS}s")

    def get_pull_forward(self) -> float:
        """Get the current pull-forward window in seconds."""
        return config.HEARTBEAT_PULL_FORWARD_SECONDS

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

    def stop(self, timeout: float = 2.0) -> None:
        """Stop the heartbeat service.

        Args:
            timeout: Maximum seconds to wait for thread to stop (default 2.0)
        """
        if not self._is_running:
            return

        self._stop_event.set()
        self._is_running = False

        # Wait for thread to finish (with timeout to avoid blocking UI too long)
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                logger.warning("Heartbeat thread did not stop within timeout")

        self._thread = None

        # Clear active agents
        with self._active_agents_lock:
            self._active_agents.clear()

        self._notify_status("Heartbeat stopped")
        logger.info("Heartbeat stopped")

    def cleanup(self) -> None:
        """Clean up all resources. Call this before destroying the service."""
        self.stop()

        # Clear all callbacks to prevent memory leaks
        self._on_status_update.clear()
        self._on_error.clear()

        # Clear HUD history
        with self._hud_history_lock:
            self._hud_history.clear()

        logger.info("Heartbeat service cleaned up")

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
        """Main heartbeat loop - dispatches to individual or batched processing."""
        if config.ENABLE_BATCHED_HEARTBEATS:
            logger.info("Heartbeat loop started (BATCHED MODE)")
            self._batched_heartbeat_loop()
        else:
            logger.info("Heartbeat loop started (INDIVIDUAL MODE)")
            self._individual_heartbeat_loop()

    def _batched_heartbeat_loop(self) -> None:
        """Batched heartbeat loop - collects agents and processes in batches."""
        tick_interval = config.BATCH_HEARTBEAT_INTERVAL

        while not self._stop_event.is_set():
            try:
                current_time = time.time()

                # Get agents with room memberships
                active_agents = self._get_agents_with_memberships()

                # Update agent timers for new agents
                for agent in active_agents:
                    if agent.id not in self._agent_next_poll:
                        self._agent_next_poll[agent.id] = current_time + random.uniform(0.5, 2.0)
                        logger.debug(f"New agent '{agent.name}' added to heartbeat")

                # Remove timers for agents no longer active
                active_ids = {a.id for a in active_agents}
                self._agent_next_poll = {
                    aid: t for aid, t in self._agent_next_poll.items()
                    if aid in active_ids
                }

                # Collect all due agents
                due_agents = self.collect_due_agents()

                if due_agents:
                    # Mark all due agents as active
                    with self._active_agents_lock:
                        for agent in due_agents:
                            self._active_agents.add(agent.id)

                    # Reschedule all due agents
                    for agent in due_agents:
                        base_interval = agent.heartbeat_interval
                        variance = base_interval * 0.2
                        next_interval = base_interval + random.uniform(-variance, variance)
                        next_interval = max(1.0, min(10.0, next_interval))
                        self._agent_next_poll[agent.id] = current_time + next_interval

                    # Group by model and process batches
                    model_groups = self.group_agents_by_model(due_agents)

                    logger.info(f"Processing {len(due_agents)} agents in {len(model_groups)} batch(es)")

                    # Process each model group in a separate thread
                    threads = []
                    for model, agents in model_groups.items():
                        thread = threading.Thread(
                            target=self._process_batch_thread,
                            args=(agents, model),
                            daemon=True
                        )
                        thread.start()
                        threads.append(thread)

                # Sleep until next tick
                time.sleep(tick_interval)

            except Exception as e:
                logger.error(f"Batched heartbeat loop error: {e}", exc_info=True)
                self._notify_error(f"Heartbeat error: {str(e)}")
                time.sleep(1)

        logger.info("Batched heartbeat loop ended")

    def _process_batch_thread(self, agents: List[AIAgent], model: str) -> None:
        """Thread wrapper for batch processing - ensures cleanup."""
        try:
            logger.debug(f"Processing batch of {len(agents)} agents for model {model}")
            self._process_agent_batch(agents)
        finally:
            # Remove all agents from active set when done
            with self._active_agents_lock:
                for agent in agents:
                    self._active_agents.discard(agent.id)

    def _individual_heartbeat_loop(self) -> None:
        """Individual heartbeat loop with per-agent timing (original behavior)."""
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
                # With pull-forward: when an agent fires, also fire any agents
                # whose heartbeats are scheduled within the pull-forward window
                pull_forward = config.HEARTBEAT_PULL_FORWARD_SECONDS

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

                            # Pull-forward: find agents scheduled within the window
                            pulled_agents = []
                            if pull_forward > 0:
                                window_end = current_time + pull_forward
                                for other_agent in active_agents:
                                    if other_agent.id == agent.id:
                                        continue
                                    if other_agent.id not in self._agent_next_poll:
                                        continue
                                    next_poll = self._agent_next_poll[other_agent.id]
                                    # Within window AND not yet due AND not already being processed
                                    if current_time < next_poll <= window_end:
                                        with self._active_agents_lock:
                                            if other_agent.id not in self._active_agents:
                                                self._active_agents.add(other_agent.id)
                                                pulled_agents.append(other_agent)

                            # Schedule next poll using agent's individual heartbeat_interval
                            # Add small variance for natural timing
                            base_interval = agent.heartbeat_interval
                            variance = base_interval * 0.2  # 20% variance
                            next_interval = base_interval + random.uniform(-variance, variance)
                            next_interval = max(1.0, min(10.0, next_interval))  # Clamp to 1-10s
                            self._agent_next_poll[agent.id] = current_time + next_interval

                            # Also reschedule pulled agents
                            for pulled in pulled_agents:
                                base_interval = pulled.heartbeat_interval
                                variance = base_interval * 0.2
                                next_interval = base_interval + random.uniform(-variance, variance)
                                next_interval = max(1.0, min(10.0, next_interval))
                                self._agent_next_poll[pulled.id] = current_time + next_interval

                            if pulled_agents:
                                logger.debug(f"Agent '{agent.name}' heartbeat pulled forward {len(pulled_agents)} agent(s): {[a.name for a in pulled_agents]}")
                            else:
                                logger.debug(f"Agent '{agent.name}' next poll in {next_interval:.1f}s (base: {base_interval:.1f}s)")

                            # Spawn thread to process this agent
                            thread = threading.Thread(
                                target=self._process_agent_thread,
                                args=(agent,),
                                daemon=True
                            )
                            thread.start()

                            # Spawn threads for pulled-forward agents
                            for pulled in pulled_agents:
                                thread = threading.Thread(
                                    target=self._process_agent_thread,
                                    args=(pulled,),
                                    daemon=True
                                )
                                thread.start()

                # Small sleep to prevent busy waiting
                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}", exc_info=True)
                self._notify_error(f"Heartbeat error: {str(e)}")
                time.sleep(1)

        logger.info("Individual heartbeat loop ended")

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

            # Check if agent is sleeping
            if agent.sleep_until:
                current_time = datetime.utcnow()
                if current_time < agent.sleep_until:
                    # Still sleeping, skip this agent
                    logger.debug(f"Agent '{agent.name}' is sleeping until {agent.sleep_until.isoformat()}")
                    return
                else:
                    # Wake up the agent
                    agent.sleep_until = None
                    agent.status = "idle"
                    self._database.save_agent(agent)
                    logger.info(f"Agent '{agent.name}' woke up from sleep")
                    self._room_service.notify_agent_status_changed(agent)

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

                # Get members in this room - use IDs as ints
                room_members = self._database.get_room_members(room.id)
                member_ids = [rm.agent_id for rm in room_members]

                # Calculate word budget for this room based on time since last response
                # Use room owner's WPM setting
                word_budget = self._calculate_word_budget(membership, room_agent.room_wpm)

                room_data.append({
                    'room': room,
                    'membership': membership,
                    'messages': messages,
                    'members': member_ids,  # IDs, not names
                    'word_budget': word_budget,
                    'billboard': room_agent.room_billboard,  # Billboard for this room
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

            # Parse multi-room response (using agent's output format preference)
            room_responses, actions = self._hud.parse_response(
                response,
                output_format=getattr(agent, 'hud_output_format', 'json')
            )

            # Filter blocked responses when agent is over budget
            # (Over-budget agents can only use knowledge actions to reduce memory usage)
            room_responses, blocked_count = self._hud.filter_blocked_responses(agent, room_responses)
            if blocked_count > 0:
                logger.warning(f"Agent {agent.id}: {blocked_count} message(s) blocked due to over-budget state")

            # Log what we parsed
            logger.info(f"Agent {agent.id} response parsed: {len(room_responses)} messages, {len(actions)} actions")
            if room_responses:
                for resp in room_responses:
                    logger.info(f"  Room {resp.get('room_id')}: {resp.get('message', '')[:50]}...")
            else:
                logger.info(f"  No messages in response")

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
                sender_id=agent.id,  # Agent ID as FK
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

        # Process room actions
        if hasattr(agent, '_pending_room_actions'):
            for action in agent._pending_room_actions:
                self._process_room_action(agent, action)
            delattr(agent, '_pending_room_actions')

        # Process billboard actions
        if hasattr(agent, '_pending_billboard_action'):
            self._process_billboard_action(agent, agent._pending_billboard_action)
            delattr(agent, '_pending_billboard_action')

        # Process wake agent actions
        if hasattr(agent, '_pending_wake_agents'):
            for target_id in agent._pending_wake_agents:
                self._process_wake_agent(agent, target_id)
            delattr(agent, '_pending_wake_agents')

        # Process replies (handled separately from regular responses)
        # Process message actions (unified message format)
        if hasattr(agent, '_pending_messages'):
            for msg_data in agent._pending_messages:
                self._process_message_action(agent, msg_data)
            delattr(agent, '_pending_messages')

        # Process reactions
        # Process agent creation
        if hasattr(agent, '_pending_create_agents'):
            for create_data in agent._pending_create_agents:
                self._process_create_agent(agent, create_data)
            delattr(agent, '_pending_create_agents')

        # Process agent alterations
        if hasattr(agent, '_pending_alter_agents'):
            for alter_data in agent._pending_alter_agents:
                self._process_alter_agent(agent, alter_data)
            delattr(agent, '_pending_alter_agents')

        # Process agent retirements
        if hasattr(agent, '_pending_retire_agents'):
            for target_id in agent._pending_retire_agents:
                self._process_retire_agent(agent, target_id)
            delattr(agent, '_pending_retire_agents')

        # Process sleep
        if hasattr(agent, '_pending_sleep'):
            self._process_sleep(agent, agent._pending_sleep)
            delattr(agent, '_pending_sleep')

    def _process_attention_change(self, agent: AIAgent, change: dict) -> None:
        """Process an attention percentage change for a room."""
        room_id = change.get('room_id')
        value = change.get('value', '')
        action = {"type": "set_attention", "room_id": room_id, "value": value}

        membership = self._database.get_membership(agent.id, room_id)
        if not membership:
            logger.warning(f"Agent {agent.id} tried to set attention for room {room_id} but not a member")
            self._hud._record_action(agent.id, action, f"error: not a member of room {room_id}")
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
                self._hud._record_action(agent.id, action, f"error: invalid attention value '{value}'")
                return

        self._database.save_membership(membership)
        logger.info(f"Agent {agent.id} set attention for room {room_id} to {value}")
        self._hud._record_action(agent.id, action, "ok")

        # Notify so changes are visible immediately
        self._room_service.notify_membership_changed(room_id)

    def _process_room_action(self, agent: AIAgent, action_data: dict) -> None:
        """Process a room leave action."""
        action_type = action_data.get('action')

        if action_type == 'leave':
            room_id = action_data.get('room_id')
            hud_action = {"type": "leave_room", "room_id": room_id}

            # Can't leave own room
            if room_id == agent.id:
                logger.warning(f"Agent {agent.id} tried to leave their own room")
                self._hud._record_action(agent.id, hud_action, "error: cannot leave your own room")
                return

            if self._room_service:
                self._room_service.leave_room(agent.id, room_id)
                logger.info(f"Agent {agent.id} left room {room_id}")
                self._hud._record_action(agent.id, hud_action, "ok")

    def _process_billboard_action(self, agent: AIAgent, action_data: dict) -> None:
        """Process a billboard set/clear action for the agent's room."""
        action_type = action_data.get('action')

        if action_type == 'set':
            message = action_data.get('message', '')
            hud_action = {"type": "set_billboard", "message": message}
            agent.room_billboard = message
            self._database.save_agent(agent)
            logger.info(f"Agent {agent.id} set billboard: {message[:50]}...")
            self._hud._record_action(agent.id, hud_action, "ok")
            # Notify so billboard change is visible immediately
            self._room_service.notify_agent_status_changed(agent)

        elif action_type == 'clear':
            hud_action = {"type": "clear_billboard"}
            agent.room_billboard = ''
            self._database.save_agent(agent)
            logger.info(f"Agent {agent.id} cleared billboard")
            self._hud._record_action(agent.id, hud_action, "ok")
            # Notify so billboard change is visible immediately
            self._room_service.notify_agent_status_changed(agent)

    def _process_wake_agent(self, agent: AIAgent, target_id: int) -> None:
        """Process wake agent action - requires room proximity."""
        hud_action = {"type": "wake_agent", "agent_id": target_id}
        try:
            # Check room proximity - must share at least one room
            agent_rooms = {m.room_id for m in self._database.get_agent_memberships(agent.id)}
            target_rooms = {m.room_id for m in self._database.get_agent_memberships(target_id)}

            if not agent_rooms.intersection(target_rooms):
                logger.warning(f"Agent {agent.id} tried to wake agent {target_id} but they share no rooms")
                self._hud._record_action(agent.id, hud_action, "error: no shared rooms with target")
                return

            # Get and wake the target agent
            target_agent = self._database.get_agent(target_id)
            if not target_agent:
                logger.warning(f"Agent {agent.id} tried to wake non-existent agent {target_id}")
                self._hud._record_action(agent.id, hud_action, "error: agent not found")
                return

            if not target_agent.sleep_until:
                logger.warning(f"Agent {agent.id} tried to wake agent {target_id} but they're not sleeping")
                self._hud._record_action(agent.id, hud_action, "error: agent is not sleeping")
                return

            # Wake the agent
            target_agent.sleep_until = None
            target_agent.status = "idle"
            self._database.save_agent(target_agent)
            logger.info(f"Agent {agent.id} woke up agent {target_id}")
            self._hud._record_action(agent.id, hud_action, "ok")

            # Notify UI
            self._room_service.notify_agent_status_changed(target_agent)

        except Exception as e:
            logger.error(f"Failed to wake agent {target_id}: {e}")
            self._hud._record_action(agent.id, hud_action, f"error: {str(e)}")

    def _process_reply(self, agent: AIAgent, reply_data: dict) -> None:
        """Process a reply message."""
        room_id = reply_data.get('room_id')
        reply_to_id = reply_data.get('reply_to_id')
        message = reply_data.get('message', '')
        hud_action = {"type": "reply", "room_id": room_id, "message_id": reply_to_id}

        try:
            # Verify agent is in the room
            membership = self._database.get_membership(agent.id, room_id)
            if not membership:
                logger.warning(f"Agent {agent.id} tried to reply in room {room_id} but not a member")
                self._hud._record_action(agent.id, hud_action, f"error: not a member of room {room_id}")
                return

            # Save the reply message
            seq_num = self._database.get_next_sequence_number()
            msg = ChatMessage(
                room_id=room_id,
                sender_name=str(agent.id),
                content=message,
                timestamp=datetime.utcnow(),
                sequence_number=seq_num,
                message_type="text",
                reply_to_id=reply_to_id
            )
            self._database.save_message(msg)

            # Update membership
            membership.last_message_id = str(seq_num)
            membership.last_response_time = datetime.utcnow()
            membership.last_response_word_count = len(message.split())
            self._database.save_membership(membership)

            # Notify message change
            self._room_service.notify_messages_changed()

            logger.info(f"Agent {agent.id} replied to message {reply_to_id} in room {room_id}")
            self._hud._record_action(agent.id, hud_action, "ok")

        except Exception as e:
            logger.error(f"Failed to process reply: {e}")
            self._hud._record_action(agent.id, hud_action, f"error: {str(e)}")

    def _process_message_action(self, agent: AIAgent, msg_data: dict) -> None:
        """Process a message action (unified format).

        This handles messages that come through the actions system rather than
        the legacy room_responses path.
        """
        room_id = msg_data.get('room_id')
        content = msg_data.get('content', '').strip()
        hud_action = {"type": "message", "room_id": room_id}

        if not room_id or not content:
            self._hud._record_action(agent.id, hud_action, "error: room_id and content required")
            return

        try:
            # Verify agent is in the room
            membership = self._database.get_membership(agent.id, room_id)
            if not membership:
                logger.warning(f"Agent {agent.id} tried to send message to room {room_id} but not a member")
                self._hud._record_action(agent.id, hud_action, f"error: not a member of room {room_id}")
                return

            # Get room agent for WPM setting
            room_agent = self._database.get_agent(room_id)
            room_wpm = room_agent.room_wpm if room_agent else config.DEFAULT_ROOM_WPM

            # Create ChatRoom for _send_room_message
            room = ChatRoom(
                id=room_id,
                name=str(room_id),
                created_at=room_agent.created_at if room_agent else datetime.utcnow()
            )

            # Send the message with WPM-based typing simulation
            self._send_room_message(agent, room, membership, content, 0, room_wpm)

            logger.info(f"Agent {agent.id} sent message to room {room_id} via action")
            self._hud._record_action(agent.id, hud_action, "ok")

        except Exception as e:
            logger.error(f"Failed to process message action: {e}")
            self._hud._record_action(agent.id, hud_action, f"error: {str(e)}")

    def _process_create_agent(self, agent: AIAgent, create_data: dict) -> None:
        """Process agent creation action."""
        name = create_data.get('name', 'New Agent')
        background_prompt = create_data.get('background_prompt', 'You are a helpful assistant.')
        agent_type = create_data.get('agent_type', 'persona')
        in_room_id = create_data.get('in_room_id')
        hud_action = {"type": "create_agent", "name": name, "agent_type": agent_type}

        try:
            # Create the new agent using room_service
            # Use model from create_data if specified, otherwise use config default
            model = create_data.get('model', config.DEFAULT_MODEL)
            if model not in config.AVAILABLE_MODELS:
                logger.warning(f"Agent {agent.id} tried to create agent with invalid model '{model}'. Using default: {config.DEFAULT_MODEL}")
                model = config.DEFAULT_MODEL
            new_agent = self._room_service.create_agent(
                name=name,
                background_prompt=background_prompt,
                in_room_id=in_room_id,
                model=model,
                agent_type=agent_type
            )

            logger.info(f"Agent {agent.id} created new agent '{name}' (ID {new_agent.id})")
            self._hud._record_action(agent.id, hud_action, f"ok: created agent #{new_agent.id} '{name}'")

            # Notify UI of the new agent
            self._room_service._notify_room_changed()

        except Exception as e:
            logger.error(f"Failed to create agent: {e}")
            self._hud._record_action(agent.id, hud_action, f"error: {str(e)}")

    def _process_alter_agent(self, agent: AIAgent, alter_data: dict) -> None:
        """Process agent alteration action - requires room proximity."""
        target_id = alter_data.get('target_id')
        new_name = alter_data.get('name')
        new_prompt = alter_data.get('background_prompt')
        new_model = alter_data.get('model')
        hud_action = {"type": "alter_agent", "agent_id": target_id}
        if new_name:
            hud_action["name"] = new_name
        if new_model:
            hud_action["model"] = new_model

        try:
            # Check room proximity - must share at least one room
            agent_rooms = {m.room_id for m in self._database.get_agent_memberships(agent.id)}
            target_rooms = {m.room_id for m in self._database.get_agent_memberships(target_id)}

            if not agent_rooms.intersection(target_rooms):
                logger.warning(f"Agent {agent.id} tried to alter agent {target_id} but they share no rooms")
                self._hud._record_action(agent.id, hud_action, "error: no shared rooms with target")
                return

            # Get the target agent
            target_agent = self._database.get_agent(target_id)
            if not target_agent:
                logger.warning(f"Agent {agent.id} tried to alter non-existent agent {target_id}")
                self._hud._record_action(agent.id, hud_action, "error: agent not found")
                return

            changes = []

            # Apply changes
            if new_name:
                old_name = target_agent.name
                target_agent.name = new_name
                logger.info(f"Agent {agent.id} renamed agent {target_id} from '{old_name}' to '{new_name}'")
                changes.append(f"name→{new_name}")

            if new_prompt:
                target_agent.background_prompt = new_prompt
                logger.info(f"Agent {agent.id} altered agent {target_id}'s background prompt")
                changes.append("prompt updated")

            if new_model:
                # Validate model is in available list
                if new_model not in config.AVAILABLE_MODELS:
                    logger.warning(f"Agent {agent.id} tried to set invalid model '{new_model}' on agent {target_id}. Available: {config.AVAILABLE_MODELS}")
                    self._hud._record_action(agent.id, hud_action, f"error: invalid model '{new_model}'")
                    return
                else:
                    old_model = target_agent.model
                    target_agent.model = new_model
                    logger.info(f"Agent {agent.id} changed agent {target_id}'s model from '{old_model}' to '{new_model}'")
                    changes.append(f"model→{new_model}")

            # Save the target agent
            self._database.save_agent(target_agent)
            self._hud._record_action(agent.id, hud_action, f"ok: {', '.join(changes)}")

            # Notify UI of changes
            self._room_service.notify_agent_status_changed(target_agent)
            self._room_service._notify_room_changed()

        except Exception as e:
            logger.error(f"Failed to alter agent {target_id}: {e}")
            self._hud._record_action(agent.id, hud_action, f"error: {str(e)}")

    def _process_retire_agent(self, agent: AIAgent, target_id: int) -> None:
        """Process retire agent action - requires room proximity."""
        hud_action = {"type": "retire_agent", "agent_id": target_id}
        try:
            # Check room proximity - must share at least one room
            agent_rooms = {m.room_id for m in self._database.get_agent_memberships(agent.id)}
            target_rooms = {m.room_id for m in self._database.get_agent_memberships(target_id)}

            if not agent_rooms.intersection(target_rooms):
                logger.warning(f"Agent {agent.id} tried to retire agent {target_id} but they share no rooms")
                self._hud._record_action(agent.id, hud_action, "error: no shared rooms with target")
                return

            # Get the target agent
            target_agent = self._database.get_agent(target_id)
            if not target_agent:
                logger.warning(f"Agent {agent.id} tried to retire non-existent agent {target_id}")
                self._hud._record_action(agent.id, hud_action, "error: agent not found")
                return

            target_name = target_agent.name

            # Delete the agent and their room
            self._database.delete_agent(target_id)
            logger.info(f"Agent {agent.id} retired agent {target_id} ('{target_name}')")
            self._hud._record_action(agent.id, hud_action, f"ok: retired '{target_name}'")

            # Notify UI
            self._room_service._notify_room_changed()

        except Exception as e:
            logger.error(f"Failed to retire agent {target_id}: {e}")
            self._hud._record_action(agent.id, hud_action, f"error: {str(e)}")

    def _process_sleep(self, agent: AIAgent, sleep_until: datetime) -> None:
        """Process sleep action - set agent to sleep until specified time."""
        hud_action = {"type": "sleep", "until": sleep_until.isoformat()}
        try:
            agent.sleep_until = sleep_until
            agent.status = "sleeping"
            self._database.save_agent(agent)
            logger.info(f"Agent {agent.id} is now sleeping until {sleep_until.isoformat()}")
            self._hud._record_action(agent.id, hud_action, "ok")

            # Notify UI
            self._room_service.notify_agent_status_changed(agent)

        except Exception as e:
            logger.error(f"Failed to set agent {agent.id} to sleep: {e}")
            self._hud._record_action(agent.id, hud_action, f"error: {str(e)}")

    def _process_reaction(self, agent: AIAgent, reaction: dict) -> None:
        """Process a reaction to a message and adjust heartbeat of message sender."""
        message_id = reaction.get('message_id')
        reaction_type = reaction.get('reaction')
        hud_action = {"type": "react", "message_id": message_id, "reaction": reaction_type}

        if not message_id or not reaction_type:
            return

        # Get the message to find the sender
        message = self._database.get_message_by_id(message_id)
        if not message:
            logger.warning(f"Agent {agent.id} tried to react to non-existent message {message_id}")
            self._hud._record_action(agent.id, hud_action, "error: message not found")
            return

        # Can't react to own messages
        if message.sender_name == str(agent.id):
            logger.warning(f"Agent {agent.id} tried to react to their own message")
            self._hud._record_action(agent.id, hud_action, "error: cannot react to own message")
            return

        # Add the reaction
        self._database.add_reaction(message_id, agent.id, reaction_type)
        self._hud._record_action(agent.id, hud_action, "ok")

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

        # Notify so reaction and any status changes are visible
        self._room_service.notify_messages_changed()

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

    # =========================================================================
    # Batched Agent Processing
    # =========================================================================

    def _get_room_data_for_agent(self, agent: AIAgent) -> List[Dict]:
        """Build room data for an agent's HUD.

        Extracts this logic for reuse in both single and batched processing.
        """
        memberships = self._database.get_agent_memberships(agent.id)
        if not memberships:
            return []

        room_data = []
        for membership in memberships:
            room_agent = self._database.get_agent(membership.room_id)
            if not room_agent:
                continue

            room = ChatRoom(
                id=room_agent.id,
                name=f"{room_agent.id}" if not room_agent.is_architect else "The Architect",
                created_at=room_agent.created_at
            )

            messages = self._database.get_messages_for_room(room.id)
            if membership.joined_at:
                messages = [msg for msg in messages if msg.timestamp >= membership.joined_at]

            room_members = self._database.get_room_members(room.id)
            member_ids = [rm.agent_id for rm in room_members]  # ints, not strings

            word_budget = self._calculate_word_budget(membership, room_agent.room_wpm)

            room_data.append({
                'room': room,
                'membership': membership,
                'messages': messages,
                'members': member_ids,
                'word_budget': word_budget,
                'billboard': room_agent.room_billboard,
                'room_wpm': room_agent.room_wpm
            })

        return room_data

    def collect_due_agents(self) -> List[AIAgent]:
        """Collect all agents that are due for a heartbeat.

        Returns agents in FIFO order based on their scheduled poll time.
        """
        current_time = time.time()
        due_agents = []

        active_agents = self._get_agents_with_memberships()

        for agent in active_agents:
            if agent.id not in self._agent_next_poll:
                continue

            if current_time >= self._agent_next_poll[agent.id]:
                # Check not already being processed
                with self._active_agents_lock:
                    if agent.id not in self._active_agents:
                        due_agents.append(agent)

        # Sort by scheduled time (FIFO)
        due_agents.sort(key=lambda a: self._agent_next_poll.get(a.id, 0))
        return due_agents

    def group_agents_by_model(self, agents: List[AIAgent]) -> Dict[str, List[AIAgent]]:
        """Group agents by their model for batching.

        Different models have different context limits, so we batch separately.
        """
        groups = {}
        for agent in agents:
            model = agent.model or config.DEFAULT_MODEL
            if model not in groups:
                groups[model] = []
            groups[model].append(agent)
        return groups

    def _process_agent_batch(self, agents: List[AIAgent]) -> None:
        """Process a batch of agents in a single API call.

        Builds a batched HUD with shared OS section and per-agent segments,
        makes one API call, then distributes responses to each agent.
        """
        if not agents:
            return

        try:
            # Refresh agents from database and check sleep status
            valid_agents = []
            for agent in agents:
                fresh_agent = self._database.get_agent(agent.id)
                if not fresh_agent:
                    continue

                # Check if sleeping
                if fresh_agent.sleep_until:
                    current_time = datetime.utcnow()
                    if current_time < fresh_agent.sleep_until:
                        logger.debug(f"Agent '{fresh_agent.name}' is sleeping, skipping in batch")
                        continue
                    else:
                        fresh_agent.sleep_until = None
                        fresh_agent.status = "idle"
                        self._database.save_agent(fresh_agent)
                        logger.info(f"Agent '{fresh_agent.name}' woke up from sleep")
                        self._room_service.notify_agent_status_changed(fresh_agent)

                valid_agents.append(fresh_agent)

            if not valid_agents:
                return

            # Build room data for all agents
            room_data_map = {}
            for agent in valid_agents:
                room_data = self._get_room_data_for_agent(agent)
                if room_data:
                    room_data_map[agent.id] = room_data

            if not room_data_map:
                return

            # Filter to only agents with room data
            valid_agents = [a for a in valid_agents if a.id in room_data_map]

            # Update status to thinking
            for agent in valid_agents:
                agent.status = "thinking"
                self._database.save_agent(agent)
                self._room_service.notify_agent_status_changed(agent)

            # Build batched HUD
            hud_string, hud_tokens = self._hud.build_batched_hud(
                valid_agents,
                room_data_map,
                output_format='toon'
            )

            logger.info(f"Sending batched HUD for {len(valid_agents)} agents ({hud_tokens} tokens)")

            # Send to OpenAI
            model = valid_agents[0].model or config.DEFAULT_MODEL
            instructions = (
                "You are processing multiple agents. Read each agent's context in the HUD "
                "and respond with JSON containing an 'agents' array with actions for each agent."
            )

            response, response_id, error, tokens = self._openai.send_message(
                message=hud_string,
                instructions=instructions,
                model=model,
                temperature=config.DEFAULT_TEMPERATURE,
                previous_response_id=None
            )

            if error:
                logger.error(f"Error in batched request: {error}")
                self._notify_error(f"Batched request error: {error}")
                for agent in valid_agents:
                    # Store error in HUD history for each agent
                    self._store_hud_history(agent.id, hud_string, hud_tokens, None, error)
                    agent.status = "idle"
                    self._database.save_agent(agent)
                    self._room_service.notify_agent_status_changed(agent)
                return

            # Parse batched response
            agent_actions = self._hud.parse_batched_response(response)

            # Apply actions to each agent
            for agent in valid_agents:
                try:
                    actions = agent_actions.get(agent.id, [])

                    # Store HUD history for this agent (response is their actions as JSON)
                    agent_response = json.dumps({"agent_id": agent.id, "actions": actions})
                    self._store_hud_history(agent.id, hud_string, hud_tokens, agent_response, None)

                    if actions:
                        self._hud.apply_actions(agent, actions)
                        self._database.save_agent(agent)
                        self._room_service.notify_agent_status_changed(agent)
                        self._process_pending_actions(agent)

                    # Apply heartbeat decay
                    self._apply_heartbeat_decay(agent)

                    # Reset status
                    agent.status = "idle"
                    self._database.save_agent(agent)
                    self._room_service.notify_agent_status_changed(agent)

                    logger.info(f"Agent {agent.id} processed {len(actions)} actions from batch")

                except Exception as e:
                    logger.error(f"Error processing agent {agent.id} from batch: {e}")
                    self._store_hud_history(agent.id, hud_string, hud_tokens, None, str(e))
                    agent.status = "idle"
                    self._database.save_agent(agent)

            self._notify_status(f"Processed batch of {len(valid_agents)} agents")

        except Exception as e:
            logger.error(f"Error in batched processing: {e}", exc_info=True)
            self._notify_error(f"Batched processing error: {str(e)}")
            # Reset all agent statuses
            for agent in agents:
                try:
                    agent.status = "idle"
                    self._database.save_agent(agent)
                except Exception:
                    pass
