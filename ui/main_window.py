"""Main window UI using Tkinter.

The main application window that coordinates all UI components for the
AI Chat Room application.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from typing import Optional, List
try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

from services import DatabaseService, OpenAIService, HeartbeatService, RoomService, setup_logging, get_logger
from models import AIAgent, ChatRoom
from .dialogs import KnowledgeExplorerDialog, SettingsDialog, PromptEditorDialog, HUDHistoryDialog
from . import theme
import config

logger = get_logger("ui")


class MainWindow:
    """Main application window."""

    def __init__(self):
        """Initialize the main window."""
        # Set up logging first
        setup_logging()
        logger.info("Application starting")

        # Initialize services
        self._database = DatabaseService()
        self._openai = OpenAIService()
        self._room_service = RoomService(self._database)
        self._heartbeat = HeartbeatService(self._openai, self._database, self._room_service)

        # Set up callbacks
        self._room_service.add_messages_changed_callback(self._on_messages_changed)
        self._room_service.add_agent_status_callback(self._on_agent_status_changed)
        self._room_service.add_room_changed_callback(self._on_rooms_changed)
        self._room_service.add_membership_changed_callback(self._on_membership_changed)
        self._heartbeat.add_status_callback(self._on_status_update)
        self._heartbeat.add_error_callback(self._on_status_update)

        # Create main window
        self._root = tk.Tk()
        self._root.title("AI Chat Room")
        self._root.geometry(f"{config.WINDOW_DEFAULT_WIDTH}x{config.WINDOW_DEFAULT_HEIGHT}")
        self._root.minsize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)

        # Apply theme colors
        self._bg_dark = theme.BG_DARK
        self._bg_medium = theme.BG_MEDIUM
        self._bg_light = theme.BG_LIGHT
        self._fg_light = theme.FG_LIGHT
        self._fg_dim = theme.FG_DIM

        # Configure dark mode styling
        self._root.configure(bg=self._bg_dark)
        style = ttk.Style()
        theme.configure_ttk_styles(style, self._bg_dark, self._bg_medium, self._bg_light, self._fg_light)

        # Track selected items
        self._selected_agent: Optional[AIAgent] = None
        self._selected_room: Optional[ChatRoom] = None
        self._rooms_list: List[ChatRoom] = []  # Cache for rooms
        self._room_agents_list: List[AIAgent] = []  # Cache for agents in selected room

        # Build UI
        self._create_ui()
        self._load_data()

        # Handle window close
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

        logger.info("Application initialized")

    def _create_ui(self) -> None:
        """Create all UI elements."""
        # Create menu bar
        self._create_menu_bar()

        # Main container
        main_frame = ttk.Frame(self._root, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # Main content area
        content_frame = ttk.Frame(main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True)

        # Left panel: Browsing/management (agent list)
        self._create_browse_panel(content_frame)

        # Right panel: Details (agent settings, room members, chat)
        self._create_detail_panel(content_frame)

        # Bottom: Status bar
        self._create_status_bar(main_frame)

    def _create_menu_bar(self) -> None:
        """Create the application menu bar."""
        menubar = tk.Menu(self._root, bg=self._bg_medium, fg=self._fg_light,
                         activebackground=self._bg_light, activeforeground=self._fg_light)
        self._root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0, bg=self._bg_medium, fg=self._fg_light,
                           activebackground=self._bg_light, activeforeground=self._fg_light)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Settings", command=self._open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        # Agents menu
        agents_menu = tk.Menu(menubar, tearoff=0, bg=self._bg_medium, fg=self._fg_light,
                             activebackground=self._bg_light, activeforeground=self._fg_light)
        menubar.add_cascade(label="Agents", menu=agents_menu)
        agents_menu.add_command(label="New Agent", command=self._create_agent)
        agents_menu.add_command(label="Delete Agent", command=self._delete_agent)

        # System menu
        system_menu = tk.Menu(menubar, tearoff=0, bg=self._bg_medium, fg=self._fg_light,
                             activebackground=self._bg_light, activeforeground=self._fg_light)
        menubar.add_cascade(label="System", menu=system_menu)
        system_menu.add_command(label="Edit Prompts", command=self._open_prompt_editor)

        # Help menu
        help_menu = tk.Menu(menubar, tearoff=0, bg=self._bg_medium, fg=self._fg_light,
                           activebackground=self._bg_light, activeforeground=self._fg_light)
        menubar.add_cascade(label="Help", menu=help_menu)
        help_menu.add_command(label="About", command=self._show_about)

    def _open_prompt_editor(self) -> None:
        """Open the prompt editor dialog."""
        dialog = PromptEditorDialog(self._root)

    def _show_about(self) -> None:
        """Show about dialog."""
        messagebox.showinfo(
            "About AI Chat Room",
            "AI Chat Room\n\n"
            "A multi-agent chat application where AI agents communicate via OpenAI's Responses API.\n\n"
            "Each agent IS a room - agent.id = room.id\n\n"
            "Version 1.0"
        )

    def _create_browse_panel(self, parent: ttk.Frame) -> None:
        """Create left panel for browsing and management (agent list)."""
        panel = ttk.Frame(parent, width=280)
        panel.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 15))
        panel.pack_propagate(False)

        # Agent list with status indicators
        agents_frame = ttk.LabelFrame(panel, text="Agents", padding="10")
        agents_frame.pack(fill=tk.BOTH, expand=True)

        # Agent listbox with scrollbar
        list_container = ttk.Frame(agents_frame)
        list_container.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self._agent_listbox = tk.Listbox(
            list_container, bg=self._bg_medium, fg=self._fg_light,
            selectbackground="#3d5a80", selectforeground="white",
            font=("Consolas", 11), activestyle='none'
        )
        agent_scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self._agent_listbox.yview)
        self._agent_listbox.configure(yscrollcommand=agent_scrollbar.set)

        self._agent_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        agent_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self._agent_listbox.bind('<<ListboxSelect>>', self._on_agent_listbox_select)

        # Right-click context menu for agent list
        self._agent_context_menu = tk.Menu(self._root, tearoff=0, bg=self._bg_medium, fg=self._fg_light,
                                           activebackground=self._bg_light, activeforeground=self._fg_light)
        self._agent_context_menu.add_command(label="Add to current room", command=self._add_agent_to_current_room)
        self._agent_context_menu.add_command(label="Remove from current room", command=self._remove_agent_from_current_room)
        self._agent_listbox.bind('<Button-3>', self._show_agent_context_menu)

        # New/Delete buttons
        btn_frame = ttk.Frame(agents_frame)
        btn_frame.pack(fill=tk.X)
        ttk.Button(btn_frame, text="+ New", command=self._create_agent).pack(side=tk.LEFT, expand=True, fill=tk.X)
        ttk.Button(btn_frame, text="Delete", command=self._delete_agent).pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(8, 0))

    def _create_chat_panel(self, parent: ttk.Frame) -> None:
        """Create right panel for agent's room chat."""
        panel = ttk.LabelFrame(parent, text="Chat Room", padding="15")
        panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Header with controls
        header = ttk.Frame(panel)
        header.pack(fill=tk.X, pady=(0, 10))

        # Heartbeat controls
        self._heartbeat_btn_text = tk.StringVar(value="▶ Start")
        ttk.Button(header, textvariable=self._heartbeat_btn_text, command=self._toggle_heartbeat).pack(side=tk.LEFT)
        ttk.Button(header, text="Clear", command=self._clear_chat).pack(side=tk.LEFT, padx=(8, 0))

        # Messages area
        self._messages_text = scrolledtext.ScrolledText(
            panel, wrap=tk.WORD, state=tk.DISABLED, font=("Consolas", 11),
            bg=self._bg_medium, fg=self._fg_light, insertbackground=self._fg_light,
            padx=10, pady=10
        )
        self._messages_text.pack(fill=tk.BOTH, expand=True)

        # Configure tags for different message types - bright colors for dark mode
        self._messages_text.tag_configure("system", foreground="#888888", font=("Consolas", 10, "italic"))
        self._messages_text.tag_configure("user", foreground="#58a6ff", font=("Consolas", 12, "bold"))  # Bright blue
        self._messages_text.tag_configure("agent", foreground="#7ee787", font=("Consolas", 12, "bold"))  # Bright green
        self._messages_text.tag_configure("timestamp", foreground="#6e7681", font=("Consolas", 9))
        self._messages_text.tag_configure("image_link", foreground="#d2a8ff", underline=True)  # Purple
        self._messages_text.tag_configure("typing", foreground="#ffa657", font=("Consolas", 11, "italic"))  # Orange
        self._messages_text.tag_configure("content", foreground=self._fg_light, font=("Consolas", 11))

        # Typing indicator
        self._typing_var = tk.StringVar(value="")
        self._typing_label = ttk.Label(panel, textvariable=self._typing_var, foreground="orange")
        self._typing_label.pack(fill=tk.X, pady=(5, 0))

        # Message input
        input_frame = ttk.Frame(panel)
        input_frame.pack(fill=tk.X, pady=(10, 0))

        self._message_var = tk.StringVar()
        msg_entry = ttk.Entry(input_frame, textvariable=self._message_var, font=("Consolas", 11))
        msg_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        msg_entry.bind('<Return>', lambda e: self._send_message())

        ttk.Button(input_frame, text="Send", command=self._send_message).pack(side=tk.LEFT, padx=(8, 0))

    def _create_status_bar(self, parent: ttk.Frame) -> None:
        """Create status bar."""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.X, pady=(10, 0))

        self._status_var = tk.StringVar(value="Ready")
        ttk.Label(frame, textvariable=self._status_var, relief=tk.SUNKEN).pack(fill=tk.X)

    def _load_data(self) -> None:
        """Load initial data from database."""
        self._load_api_key()
        self._refresh_agent_list()
        self._refresh_messages()

    def _refresh_agent_list(self) -> None:
        """Refresh the agent listbox with status indicators."""
        # Get all agents
        agents = self._database.get_all_agents()
        self._agents_list = [a for a in agents if not a.is_architect]  # Exclude architect

        # Clear and repopulate listbox
        self._agent_listbox.delete(0, tk.END)
        for agent in self._agents_list:
            # Status indicator
            status = agent.status if agent.status else "idle"
            indicator = {
                "idle": "●",
                "thinking": "◐",
                "typing": "⌨",
                "sending": "↑"
            }.get(status, "●")
            name = agent.name or "Unnamed"
            self._agent_listbox.insert(tk.END, f"{indicator} {name} (#{agent.id})")

        # Select first agent if none selected
        if self._agents_list and not self._selected_agent:
            self._agent_listbox.selection_set(0)
            self._on_agent_listbox_select(None)
        elif self._selected_agent:
            # Re-select current agent
            for i, a in enumerate(self._agents_list):
                if a.id == self._selected_agent.id:
                    self._agent_listbox.selection_set(i)
                    break

        # Update model combo with available models
        if hasattr(self, '_agent_model_combo'):
            self._agent_model_combo['values'] = self._openai.get_available_models()

    def _on_agent_listbox_select(self, event) -> None:
        """Handle agent selection from listbox."""
        selection = self._agent_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx < 0 or idx >= len(self._agents_list):
            return

        self._selected_agent = self._agents_list[idx]
        # Room is the agent's own room (agent = room)
        self._selected_room = ChatRoom(
            id=self._selected_agent.id,
            name=f"{self._selected_agent.id}",
            created_at=self._selected_agent.created_at
        )

        # Update details fields
        self._agent_name_var.set(self._selected_agent.name)
        self._agent_model_var.set(self._selected_agent.model)
        self._agent_prompt_text.delete("1.0", tk.END)
        self._agent_prompt_text.insert("1.0", self._selected_agent.background_prompt)
        self._topic_var.set(self._selected_agent.room_topic or "")

        # Load WPM from agent (room-level setting)
        self._detail_wpm_var.set(str(self._selected_agent.room_wpm))

        # Update heartbeat status
        status = self._selected_agent.status if self._selected_agent.status else "idle"
        status_text = {
            "idle": "● Idle",
            "thinking": "◐ Waiting for API...",
            "typing": "⌨ Typing...",
            "sending": "↑ Sending..."
        }.get(status, f"● {status}")
        self._heartbeat_status_var.set(status_text)
        self._heartbeat_status_label.configure(fg=theme.STATUS_COLORS.get(status, self._fg_light))

        # Update available agents dropdown
        self._refresh_add_agent_combo()

        # Refresh chat and status
        self._refresh_messages()
        self._update_room_status()

    def _create_agent(self) -> None:
        """Create a new agent."""
        # Create agent with default values
        agent = AIAgent(
            name="New Agent",
            model="gpt-4o-mini",
            background_prompt="You are a helpful AI assistant."
        )
        agent_id = self._database.save_agent(agent)
        agent.id = agent_id  # Update the agent object with the returned ID

        # Auto-join to own room
        self._room_service.join_room(agent, agent.id)

        # Set as selected and refresh
        self._selected_agent = agent
        self._refresh_agent_list()
        # Select the new agent in the listbox
        for i, a in enumerate(self._agents_list):
            if a.id == agent.id:
                self._agent_listbox.selection_clear(0, tk.END)
                self._agent_listbox.selection_set(i)
                self._agent_listbox.see(i)
                break
        self._on_agent_listbox_select(None)

    def _delete_agent(self) -> None:
        """Delete the selected agent."""
        if not self._selected_agent:
            return

        if messagebox.askyesno("Delete Agent", f"Delete agent {self._selected_agent.id}?"):
            self._database.delete_agent(self._selected_agent.id)
            self._selected_agent = None
            self._refresh_agent_list()
            self._refresh_messages()

    def _save_agent_details(self) -> None:
        """Save the current agent details."""
        if not self._selected_agent:
            return

        self._selected_agent.name = self._agent_name_var.get()
        self._selected_agent.model = self._agent_model_var.get()
        self._selected_agent.background_prompt = self._agent_prompt_text.get("1.0", tk.END).strip()
        self._selected_agent.room_topic = self._topic_var.get()

        # Save WPM to agent (room-level setting)
        try:
            self._selected_agent.room_wpm = int(self._detail_wpm_var.get())
        except ValueError:
            pass

        self._database.save_agent(self._selected_agent)

        self._refresh_agent_list()

    def _refresh_add_agent_combo(self) -> None:
        """Refresh the dropdown of agents that can be added to the room."""
        if not self._selected_room:
            self._add_agent_combo['values'] = []
            return

        # Get agents in room
        room_agents = self._room_service.get_agents_in_room(self._selected_room.id)
        room_agent_ids = {a.id for a in room_agents}

        # Get all agents not in room
        all_agents = self._database.get_all_agents()
        available = [a for a in all_agents if a.id not in room_agent_ids and not a.is_architect]

        options = [f"{a.id}: {a.name or 'Unnamed'}" for a in available]
        self._add_agent_combo['values'] = options
        self._available_agents_to_add = available

    def _add_agent_to_room(self) -> None:
        """Add the selected agent to the current room."""
        if not self._selected_room:
            return

        idx = self._add_agent_combo.current()
        if idx < 0 or not hasattr(self, '_available_agents_to_add') or idx >= len(self._available_agents_to_add):
            return

        agent = self._available_agents_to_add[idx]
        self._room_service.join_room(agent, self._selected_room.id)
        self._update_room_status()
        self._refresh_add_agent_combo()
        self._add_agent_var.set("")

    def _show_agent_context_menu(self, event) -> None:
        """Show context menu for agent list on right-click."""
        # Select the item under the cursor
        idx = self._agent_listbox.nearest(event.y)
        if idx >= 0:
            self._agent_listbox.selection_clear(0, tk.END)
            self._agent_listbox.selection_set(idx)
            self._agent_listbox.activate(idx)
            # Store the right-clicked agent
            if idx < len(self._agents_list):
                self._right_clicked_agent = self._agents_list[idx]
                # Show the context menu
                self._agent_context_menu.tk_popup(event.x_root, event.y_root)

    def _add_agent_to_current_room(self) -> None:
        """Add the right-clicked agent to the currently selected room."""
        if not self._selected_room:
            messagebox.showwarning("No Room", "Please select an agent/room first.")
            return

        if not hasattr(self, '_right_clicked_agent') or not self._right_clicked_agent:
            return

        agent = self._right_clicked_agent

        # Check if agent is already in the room
        room_agents = self._room_service.get_agents_in_room(self._selected_room.id)
        if any(a.id == agent.id for a in room_agents):
            messagebox.showinfo("Already Member", f"Agent {agent.id} is already in this room.")
            return

        self._room_service.join_room(agent, self._selected_room.id)
        self._update_room_status()
        self._refresh_add_agent_combo()
        self._status_var.set(f"Added Agent {agent.id} to room {self._selected_room.id}")

    def _remove_agent_from_current_room(self) -> None:
        """Remove the right-clicked agent from the currently selected room."""
        if not self._selected_room:
            messagebox.showwarning("No Room", "Please select an agent/room first.")
            return

        if not hasattr(self, '_right_clicked_agent') or not self._right_clicked_agent:
            return

        agent = self._right_clicked_agent

        # Can't remove the room owner from their own room
        if agent.id == self._selected_room.id:
            messagebox.showwarning("Cannot Remove", "Cannot remove the room owner from their own room.")
            return

        # Check if agent is in the room
        room_agents = self._room_service.get_agents_in_room(self._selected_room.id)
        if not any(a.id == agent.id for a in room_agents):
            messagebox.showinfo("Not Member", f"Agent {agent.id} is not in this room.")
            return

        self._room_service.leave_room(agent.id, self._selected_room.id)
        self._update_room_status()
        self._refresh_add_agent_combo()
        self._status_var.set(f"Removed Agent {agent.id} from room {self._selected_room.id}")

    def _open_settings(self) -> None:
        """Open the settings dialog."""
        dialog = SettingsDialog(
            self._root,
            self._openai,
            on_connected=self._refresh_agent_list
        )

    def _open_knowledge_explorer(self) -> None:
        """Open the knowledge explorer for the selected agent."""
        if not self._selected_agent:
            messagebox.showwarning("No Agent", "Please select an agent first.")
            return

        dialog = KnowledgeExplorerDialog(
            self._root,
            self._selected_agent,
            self._database
        )

    def _open_hud_history(self) -> None:
        """Open the HUD history viewer for the selected agent."""
        if not self._selected_agent:
            messagebox.showwarning("No Agent", "Please select an agent first.")
            return

        dialog = HUDHistoryDialog(
            self._root,
            self._selected_agent,
            self._heartbeat
        )

    def _on_rooms_changed(self) -> None:
        """Handle rooms list change."""
        self._root.after(0, self._refresh_agent_list)

    def _on_membership_changed(self, room_id: int) -> None:
        """Handle room membership change."""
        if self._selected_room and self._selected_room.id == room_id:
            self._root.after(0, self._update_room_status)

    def _update_room_status(self) -> None:
        """Update the room members display with editable controls."""
        # Clear existing widgets
        for widget in self._members_frame.winfo_children():
            widget.destroy()
        self._member_widgets = {}

        if not self._selected_room:
            ttk.Label(self._members_frame, text="No room selected").pack(anchor=tk.W)
            return

        # Get agents in this room
        self._room_agents_list = self._room_service.get_agents_in_room(self._selected_room.id)

        if not self._room_agents_list:
            ttk.Label(self._members_frame, text="No agents in room").pack(anchor=tk.W)
            return

        # Sort agents so owner (admin) is first
        owner_id = self._selected_room.id
        sorted_agents = sorted(self._room_agents_list, key=lambda a: (0 if a.id == owner_id else 1, a.id))

        for agent in sorted_agents:
            # Create frame for each agent
            agent_frame = ttk.Frame(self._members_frame)
            agent_frame.pack(fill=tk.X, pady=(0, 5))

            # Check if this is the room owner (admin)
            is_owner = agent.id == owner_id

            # Agent name and status - always show ID for identification
            if agent.is_architect:
                display = "The Architect"
            elif is_owner:
                name = agent.name or "Unnamed"
                display = f"★ {name} (#{agent.id}) Admin"
            else:
                name = agent.name or "Unnamed"
                display = f"  {name} (#{agent.id})"

            # Owner gets gold color, others get blue
            name_color = theme.OWNER_COLOR if is_owner else theme.MEMBER_COLOR
            name_label = tk.Label(
                agent_frame, text=display,
                fg=name_color, bg=self._bg_dark,
                font=("Consolas", 10, "bold")
            )
            name_label.pack(side=tk.LEFT)

            # Status indicator
            status = agent.status if agent.status else "idle"
            status_label = tk.Label(
                agent_frame, text=f" ● {status}",
                fg=theme.STATUS_COLORS.get(status, self._fg_light), bg=self._bg_dark,
                font=("Consolas", 9)
            )
            status_label.pack(side=tk.LEFT)

            # Store widgets for status updates
            self._member_widgets[agent.id] = {
                'status_label': status_label
            }

    def _refresh_messages(self) -> None:
        """Refresh the messages display for selected room."""
        self._messages_text.config(state=tk.NORMAL)
        self._messages_text.delete(1.0, tk.END)

        if not self._selected_room:
            self._messages_text.insert(tk.END, "No room selected", "system")
            self._messages_text.config(state=tk.DISABLED)
            return

        messages = self._room_service.get_room_messages(self._selected_room.id)

        for msg in messages:
            timestamp = msg.timestamp.strftime("%H:%M:%S")

            # Determine sender display name
            # sender_name is now stored as ID for agents
            if msg.sender_name == "System":
                sender_display = None  # System messages don't show sender
            elif msg.sender_name == "The Architect":
                sender_display = "The Architect"
            elif msg.sender_name == "User":
                sender_display = "User"
            elif msg.sender_name.isdigit():
                # It's an agent ID - look up the agent's name
                agent_id = int(msg.sender_name)
                agent = self._database.get_agent(agent_id)
                if agent and agent.name:
                    sender_display = f"{agent.name} (#{agent_id})"
                else:
                    sender_display = f"Agent #{agent_id}"
            else:
                sender_display = msg.sender_name

            # Determine tag based on message type
            if msg.message_type == "system" or msg.message_type == "starter":
                self._messages_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
                self._messages_text.insert(tk.END, f"{msg.content}\n\n", "system")
            elif msg.sender_name == "The Architect" or msg.sender_name == "User":
                self._messages_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
                self._messages_text.insert(tk.END, f"{sender_display}: ", "user")
                self._messages_text.insert(tk.END, f"{msg.content}\n")
                if msg.image_url:
                    self._messages_text.insert(tk.END, f"[View Image]\n", "image_link")
                self._messages_text.insert(tk.END, "\n")
            else:
                self._messages_text.insert(tk.END, f"[{timestamp}] ", "timestamp")
                self._messages_text.insert(tk.END, f"{sender_display}: ", "agent")
                self._messages_text.insert(tk.END, f"{msg.content}\n")
                if msg.image_url:
                    # Make image URL clickable
                    self._messages_text.insert(tk.END, "[View Image]", "image_link")
                    # Store URL for click handling
                    self._messages_text.insert(tk.END, f" ({msg.image_url})\n")
                self._messages_text.insert(tk.END, "\n")

        self._messages_text.config(state=tk.DISABLED)
        self._messages_text.see(tk.END)

    def _on_messages_changed(self) -> None:
        """Handle messages changed event."""
        self._root.after(0, self._refresh_messages)

    def _on_agent_status_changed(self, agent: AIAgent) -> None:
        """Handle agent status change (including name changes)."""
        self._root.after(0, self._refresh_agent_list)
        self._root.after(0, self._update_room_status)
        # Update heartbeat status if this is the selected agent
        if self._selected_agent and agent.id == self._selected_agent.id:
            self._root.after(0, lambda: self._update_heartbeat_status(agent))
            # Also update the name field if it changed
            self._root.after(0, lambda: self._agent_name_var.set(agent.name))

    def _update_heartbeat_status(self, agent: AIAgent) -> None:
        """Update the heartbeat status indicator for an agent."""
        if not hasattr(self, '_heartbeat_status_var'):
            return

        status = agent.status if agent.status else "idle"
        status_text = {
            "idle": "● Idle",
            "thinking": "◐ Waiting for API...",
            "typing": "⌨ Typing...",
            "sending": "↑ Sending..."
        }.get(status, f"● {status}")
        self._heartbeat_status_var.set(status_text)

        if hasattr(self, '_heartbeat_status_label'):
            self._heartbeat_status_label.configure(fg=theme.STATUS_COLORS.get(status, self._fg_light))

    def _on_status_update(self, message: str) -> None:
        """Handle status update."""
        self._root.after(0, lambda: self._status_var.set(message))
        # Update typing indicator
        if "is typing" in message:
            self._root.after(0, lambda: self._typing_var.set(message))
        elif "responded" in message or "thinking" in message:
            self._root.after(0, lambda: self._typing_var.set(""))


    def _load_api_key(self) -> None:
        """Load API key from keyring and auto-connect if found."""
        if not HAS_KEYRING:
            logger.info("Keyring not available")
            return

        try:
            api_key = keyring.get_password(config.KEYRING_SERVICE, config.KEYRING_USERNAME)
            if api_key:
                self._openai.set_api_key(api_key)
                logger.info("API key loaded from keyring")
                # Test connection
                success, message = self._openai.test_connection()
                logger.info(f"Connection test: {message}")
                if success:
                    models = self._openai.get_available_models()
                    logger.info(f"API connected: {len(models)} models available")
        except Exception as e:
            logger.error(f"Failed to load API key from keyring: {e}")

    def _send_message(self) -> None:
        """Send a message from The Architect to selected room."""
        if not self._selected_room:
            messagebox.showwarning("Warning", "Please select a room first")
            return

        message = self._message_var.get().strip()
        if not message:
            return

        # The user is The Architect
        self._room_service.send_message(self._selected_room.id, "The Architect", message)
        self._message_var.set("")
        self._refresh_messages()

    def _toggle_heartbeat(self) -> None:
        """Toggle heartbeat service."""
        if self._heartbeat.is_running:
            self._heartbeat.stop()
            self._heartbeat_btn_text.set("Start Heartbeat")
        else:
            if not self._openai.has_api_key:
                messagebox.showerror("Error", "Please connect to OpenAI first")
                return

            # Interval is per-agent, WPM is per-room
            self._heartbeat.start()
            self._heartbeat_btn_text.set("Stop Heartbeat")

    def _clear_chat(self) -> None:
        """Clear chat messages in selected room."""
        if not self._selected_room:
            messagebox.showwarning("Warning", "Please select a room first")
            return

        display_name = "The Architect" if self._selected_room.name == "The Architect" else f"Room {self._selected_room.id}"
        if messagebox.askyesno("Confirm", f"Clear all messages in '{display_name}'?"):
            self._room_service.clear_room_messages(self._selected_room.id)
            self._refresh_messages()
            self._status_var.set(f"Chat cleared in {display_name}")

    def _on_close(self) -> None:
        """Handle window close."""
        logger.info("Application closing")
        self._heartbeat.stop()
        self._root.destroy()

    def run(self) -> None:
        """Run the application."""
        self._root.mainloop()
