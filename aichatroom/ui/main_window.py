"""Main window UI using CustomTkinter for modern appearance.

The main application window that coordinates all UI components for the
AI Chat Room application.
"""

import customtkinter as ctk
from tkinter import messagebox
from typing import Optional, List
try:
    import keyring
    HAS_KEYRING = True
except ImportError:
    HAS_KEYRING = False

from services import DatabaseService, OpenAIService, HeartbeatService, RoomService, setup_logging, get_logger
from models import AIAgent, ChatRoom
from .dialogs import KnowledgeExplorerDialog, SettingsDialog, PromptEditorDialog, HUDHistoryDialog, TOONTelemetryDialog
import config

logger = get_logger("ui")

# Set appearance mode and color theme
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# Use system scaling
ctk.set_widget_scaling(1.0)
ctk.set_window_scaling(1.0)


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
        self._root = ctk.CTk()
        self._root.title("AI Chat Room")
        self._root.geometry(f"{config.WINDOW_DEFAULT_WIDTH}x{config.WINDOW_DEFAULT_HEIGHT}")
        self._root.minsize(config.WINDOW_MIN_WIDTH, config.WINDOW_MIN_HEIGHT)

        # Consistent typography - only 2 variations needed
        # Must be created after root window exists
        self._font_title = ctk.CTkFont(size=14, weight="bold")
        self._font_mono = ctk.CTkFont(family="Consolas", size=13)

        # Track selected items
        self._selected_agent: Optional[AIAgent] = None
        self._selected_room: Optional[ChatRoom] = None
        self._rooms_list: List[ChatRoom] = []
        self._room_agents_list: List[AIAgent] = []

        # Build UI
        self._create_menu_bar()
        self._create_ui()
        self._load_data()

        # Handle window close
        self._root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _create_menu_bar(self) -> None:
        """Create application menu bar."""
        import tkinter as tk

        menubar = tk.Menu(self._root)
        self._root.config(menu=menubar)

        # File menu
        file_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Settings...", command=self._open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self._on_close)

        # Edit menu
        edit_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="Edit", menu=edit_menu)
        edit_menu.add_command(label="Prompt Editor...", command=self._open_prompt_editor)

        # View menu
        view_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="View", menu=view_menu)
        view_menu.add_command(label="Knowledge Explorer", command=self._open_knowledge_explorer)
        view_menu.add_command(label="HUD History", command=self._open_hud_history)
        view_menu.add_separator()
        view_menu.add_command(label="TOON Telemetry...", command=self._open_toon_telemetry)

        logger.info("Application initialized")

    def _create_ui(self) -> None:
        """Create all UI elements."""
        # Configure grid weights for the root
        self._root.grid_columnconfigure(0, weight=1)  # Left panel - expandable (agents + settings)
        self._root.grid_columnconfigure(1, weight=2)  # Right panel - expandable (members + chat)
        self._root.grid_rowconfigure(0, weight=1)     # Main content
        self._root.grid_rowconfigure(1, weight=0)     # Status bar

        # Left panel: Agent list + Agent Settings (stacked)
        self._create_left_panel()

        # Right panel: Room Members + Chat
        self._create_right_panel()

        # Bottom: Status bar
        self._create_status_bar()

    def _create_left_panel(self) -> None:
        """Create left panel with agent list and agent settings stacked."""
        panel = ctk.CTkFrame(self._root)
        panel.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)

        # Configure panel grid - agents list on top, settings below
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=1)  # Agent list expands
        panel.grid_rowconfigure(1, weight=0)  # Settings fixed height

        # === TOP: Agent List ===
        agents_frame = ctk.CTkFrame(panel)
        agents_frame.grid(row=0, column=0, sticky="nsew", padx=0, pady=(0, 5))

        # Title
        title = ctk.CTkLabel(agents_frame, text="Agents", font=self._font_title)
        title.pack(pady=(8, 6))

        # Agent listbox frame
        list_frame = ctk.CTkFrame(agents_frame, fg_color="transparent")
        list_frame.pack(fill="both", expand=True, padx=6, pady=(0, 6))

        # Scrollable frame for agents
        self._agent_scroll = ctk.CTkScrollableFrame(list_frame, fg_color=("gray90", "gray17"))
        self._agent_scroll.pack(fill="both", expand=True)

        # Agent buttons will be added here dynamically
        self._agent_buttons = []

        # Action buttons
        btn_frame = ctk.CTkFrame(agents_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=6, pady=(0, 8))

        ctk.CTkButton(btn_frame, text="+ New", command=self._create_agent, height=28).pack(side="left", expand=True, fill="x", padx=(0, 3))
        ctk.CTkButton(btn_frame, text="Delete", command=self._delete_agent, height=28, fg_color="gray40", hover_color="gray30").pack(side="left", expand=True, fill="x", padx=(3, 0))

        # === BOTTOM: Agent Settings (collapsible) ===
        self._create_settings_panel(panel)

    def _create_right_panel(self) -> None:
        """Create right panel with room members and chat."""
        panel = ctk.CTkFrame(self._root)
        panel.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)

        # Configure grid for panel - members on top, chat below
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_rowconfigure(0, weight=0)  # Room members section
        panel.grid_rowconfigure(1, weight=1)  # Chat section (main focus - expands)

        # Top: Room Members
        self._create_members_section(panel)

        # Bottom: Chat Room (takes most space)
        self._create_chat_section(panel)

    def _create_settings_panel(self, parent) -> None:
        """Create collapsible agent settings panel in left column."""
        # Settings container frame
        settings_frame = ctk.CTkFrame(parent)
        settings_frame.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)

        # Header bar with toggle
        header = ctk.CTkFrame(settings_frame, fg_color="transparent")
        header.pack(fill="x", padx=6, pady=(6, 3))

        self._settings_expanded = True
        self._settings_toggle_text = ctk.StringVar(value="▼ Agent Settings")

        toggle_btn = ctk.CTkButton(
            header,
            textvariable=self._settings_toggle_text,
            command=self._toggle_settings,
            fg_color="transparent",
            hover_color=("gray70", "gray30"),
            anchor="w",
            font=self._font_title,
            height=26
        )
        toggle_btn.pack(side="left")

        # Collapsible content frame
        self._settings_content = ctk.CTkFrame(settings_frame, fg_color="transparent")
        self._settings_content.pack(fill="x", padx=6, pady=(0, 6))

        # Agent Settings content (now full width of left panel)
        self._create_settings_section(self._settings_content)

    def _toggle_settings(self) -> None:
        """Toggle the settings panel visibility."""
        if self._settings_expanded:
            self._settings_content.grid_remove()
            self._settings_toggle_text.set("▶ Agent Settings")
            self._settings_expanded = False
        else:
            self._settings_content.grid()
            self._settings_toggle_text.set("▼ Agent Settings")
            self._settings_expanded = True

    def _on_heartbeat_slider_change(self, *args) -> None:
        """Handle heartbeat slider value change."""
        value = self._heartbeat_interval_var.get()
        self._heartbeat_interval_label.configure(text=f"{value:.1f}s")

    def _create_settings_section(self, parent) -> None:
        """Create agent settings section (optimized for narrow left panel)."""
        # Settings content (no title - header has it)
        content = ctk.CTkFrame(parent, fg_color="transparent")
        content.pack(fill="x", padx=0, pady=0)

        # Row 1: Name
        row1 = ctk.CTkFrame(content, fg_color="transparent")
        row1.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(row1, text="Name:", width=45, anchor="w").pack(side="left")
        self._agent_name_var = ctk.StringVar()
        ctk.CTkEntry(row1, textvariable=self._agent_name_var, height=26).pack(side="left", fill="x", expand=True, padx=(3, 0))

        # Row 2: Model + Status
        row2 = ctk.CTkFrame(content, fg_color="transparent")
        row2.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(row2, text="Model:", width=45, anchor="w").pack(side="left")
        self._agent_model_var = ctk.StringVar()
        self._agent_model_combo = ctk.CTkComboBox(row2, variable=self._agent_model_var, height=26)
        self._agent_model_combo.pack(side="left", fill="x", expand=True, padx=(3, 6))

        self._heartbeat_status_var = ctk.StringVar(value="● Idle")
        self._heartbeat_status_label = ctk.CTkLabel(row2, textvariable=self._heartbeat_status_var, text_color="#7ee787")
        self._heartbeat_status_label.pack(side="right")

        # Row 3: WPM + Speed slider
        row3 = ctk.CTkFrame(content, fg_color="transparent")
        row3.pack(fill="x", pady=(0, 4))

        ctk.CTkLabel(row3, text="WPM:", width=45, anchor="w").pack(side="left")
        self._detail_wpm_var = ctk.StringVar(value="80")
        ctk.CTkEntry(row3, textvariable=self._detail_wpm_var, width=50, height=26).pack(side="left", padx=(3, 10))

        ctk.CTkLabel(row3, text="Speed:", anchor="w").pack(side="left")
        self._heartbeat_interval_var = ctk.DoubleVar(value=5.0)
        self._heartbeat_slider = ctk.CTkSlider(
            row3,
            from_=1.0,
            to=10.0,
            variable=self._heartbeat_interval_var,
            height=16,
            number_of_steps=18
        )
        self._heartbeat_slider.pack(side="left", fill="x", expand=True, padx=(3, 3))
        self._heartbeat_interval_label = ctk.CTkLabel(row3, text="5.0s", width=32)
        self._heartbeat_interval_label.pack(side="left")
        self._heartbeat_interval_var.trace_add("write", self._on_heartbeat_slider_change)

        # Row 4: Permissions checkbox
        row4 = ctk.CTkFrame(content, fg_color="transparent")
        row4.pack(fill="x", pady=(0, 4))

        self._can_create_agents_var = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(row4, text="Can create agents", variable=self._can_create_agents_var, height=22, checkbox_width=18, checkbox_height=18).pack(side="left")

        # Row 5: Background label
        ctk.CTkLabel(content, text="Background:", anchor="w").pack(fill="x", pady=(0, 2))

        # Background prompt
        self._agent_prompt_text = ctk.CTkTextbox(content, height=50)
        self._agent_prompt_text.pack(fill="x", pady=(0, 4))

        # Action buttons
        btn_frame = ctk.CTkFrame(content, fg_color="transparent")
        btn_frame.pack(fill="x")

        ctk.CTkButton(btn_frame, text="Save", command=self._save_agent_details, height=26).pack(side="left", fill="x", expand=True, padx=(0, 2))
        ctk.CTkButton(btn_frame, text="Knowledge", command=self._open_knowledge_explorer, height=26, fg_color="gray40", hover_color="gray30").pack(side="left", fill="x", expand=True, padx=(2, 2))
        ctk.CTkButton(btn_frame, text="HUD", command=self._open_hud_history, height=26, fg_color="gray40", hover_color="gray30").pack(side="left", fill="x", expand=True, padx=(2, 0))

    def _create_members_section(self, parent) -> None:
        """Create room members section."""
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=(6, 3))

        content = ctk.CTkFrame(frame, fg_color="transparent")
        content.pack(fill="both", expand=True, padx=6, pady=6)

        # Title row with add controls
        header = ctk.CTkFrame(content, fg_color="transparent")
        header.pack(fill="x", pady=(0, 5))

        ctk.CTkLabel(header, text="Room Members", font=self._font_title).pack(side="left")

        ctk.CTkButton(header, text="+", command=self._add_agent_to_room, width=26, height=26).pack(side="right")
        self._add_agent_var = ctk.StringVar()
        self._add_agent_combo = ctk.CTkComboBox(header, variable=self._add_agent_var, height=26, width=100)
        self._add_agent_combo.pack(side="right", padx=(0, 3))

        # Members list
        self._members_scroll = ctk.CTkScrollableFrame(content, fg_color=("gray90", "gray17"))
        self._members_scroll.pack(fill="both", expand=True)

        self._member_widgets = {}

    def _create_chat_section(self, parent) -> None:
        """Create chat room section."""
        frame = ctk.CTkFrame(parent)
        frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=(3, 6))

        # Configure grid
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)  # Messages area expands

        # Header with controls
        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 5))

        ctk.CTkLabel(header, text="Chat Room", font=self._font_title).pack(side="left")

        # Heartbeat controls on the right
        self._heartbeat_btn_text = ctk.StringVar(value="▶ Start")
        ctk.CTkButton(header, textvariable=self._heartbeat_btn_text, command=self._toggle_heartbeat, width=70, height=26).pack(side="right", padx=(6, 0))
        ctk.CTkButton(header, text="Clear", command=self._clear_chat, width=50, height=26, fg_color="gray40", hover_color="gray30").pack(side="right")

        # Messages area - monospace for readability
        self._messages_text = ctk.CTkTextbox(frame, state="disabled", font=self._font_mono)
        self._messages_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=(0, 5))

        # Typing indicator
        self._typing_var = ctk.StringVar(value="")
        self._typing_label = ctk.CTkLabel(frame, textvariable=self._typing_var, text_color="orange", height=18)
        self._typing_label.grid(row=2, column=0, sticky="ew", padx=8)

        # Message input
        input_frame = ctk.CTkFrame(frame, fg_color="transparent")
        input_frame.grid(row=3, column=0, sticky="ew", padx=8, pady=(3, 8))

        self._message_var = ctk.StringVar()
        self._message_entry = ctk.CTkEntry(input_frame, textvariable=self._message_var, height=32, placeholder_text="Type a message...")
        self._message_entry.pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._message_entry.bind('<Return>', lambda e: self._send_message())

        ctk.CTkButton(input_frame, text="Send", command=self._send_message, width=60, height=32).pack(side="left")

    def _create_status_bar(self) -> None:
        """Create status bar."""
        frame = ctk.CTkFrame(self._root, height=24, corner_radius=0)
        frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(0, 6))

        self._status_var = ctk.StringVar(value="Ready")
        ctk.CTkLabel(frame, textvariable=self._status_var, text_color="gray").pack(side="left", padx=8, pady=4)

    def _load_data(self) -> None:
        """Load initial data from database."""
        self._load_api_key()
        self._refresh_agent_list()
        self._refresh_messages()

    def _refresh_agent_list(self) -> None:
        """Refresh the agent list with status indicators."""
        # Get all agents
        agents = self._database.get_all_agents()
        self._agents_list = [a for a in agents if not a.is_architect]

        # Clear existing buttons
        for btn in self._agent_buttons:
            btn.destroy()
        self._agent_buttons = []

        # Create buttons for each agent
        for agent in self._agents_list:
            status = agent.status if agent.status else "idle"
            indicator = {"idle": "●", "thinking": "◐", "typing": "⌨", "sending": "↑", "sleeping": "💤"}.get(status, "●")
            color = {"idle": "#7ee787", "thinking": "#ffa657", "typing": "#79c0ff", "sending": "#d2a8ff", "sleeping": "#8b8b8b"}.get(status, "#7ee787")

            name = agent.name or "Unnamed"
            text = f"{indicator} {name} (#{agent.id})"

            btn = ctk.CTkButton(
                self._agent_scroll,
                text=text,
                anchor="w",
                height=28,
                fg_color="transparent" if not (self._selected_agent and agent.id == self._selected_agent.id) else ("gray75", "gray25"),
                hover_color=("gray70", "gray30"),
                text_color=color,
                command=lambda a=agent: self._select_agent(a)
            )
            btn.pack(fill="x", pady=1, padx=3)
            self._agent_buttons.append(btn)

        # Update model combo
        if hasattr(self, '_agent_model_combo'):
            models = self._openai.get_available_models()
            self._agent_model_combo.configure(values=models)

    def _select_agent(self, agent: AIAgent) -> None:
        """Select an agent and update the UI."""
        self._selected_agent = agent
        self._selected_room = ChatRoom(
            id=agent.id,
            name=f"{agent.id}",
            created_at=agent.created_at
        )

        # Update details fields
        self._agent_name_var.set(agent.name)
        self._agent_model_var.set(agent.model)
        self._agent_prompt_text.delete("1.0", "end")
        self._agent_prompt_text.insert("1.0", agent.background_prompt)
        self._detail_wpm_var.set(str(agent.room_wpm))
        self._can_create_agents_var.set(agent.can_create_agents)
        self._heartbeat_interval_var.set(agent.heartbeat_interval)
        self._heartbeat_interval_label.configure(text=f"{agent.heartbeat_interval:.1f}s")

        # Update heartbeat status
        status = agent.status if agent.status else "idle"
        status_text = {"idle": "● Idle", "thinking": "◐ Waiting...", "typing": "⌨ Typing...", "sending": "↑ Sending...", "sleeping": "💤 Sleeping"}.get(status, f"● {status}")
        color = {"idle": "#7ee787", "thinking": "#ffa657", "typing": "#79c0ff", "sending": "#d2a8ff", "sleeping": "#8b8b8b"}.get(status, "#7ee787")
        self._heartbeat_status_var.set(status_text)
        self._heartbeat_status_label.configure(text_color=color)

        # Refresh related UI
        self._refresh_agent_list()
        self._refresh_add_agent_combo()
        self._refresh_messages()
        self._update_room_status()

    def _create_agent(self) -> None:
        """Create a new agent."""
        agent = AIAgent(
            name="New Agent",
            model="gpt-4o-mini",
            background_prompt="You are a helpful AI assistant."
        )
        agent_id = self._database.save_agent(agent)
        agent.id = agent_id

        self._room_service.join_room(agent, agent.id)
        self._selected_agent = agent
        self._refresh_agent_list()
        self._select_agent(agent)

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
        self._selected_agent.background_prompt = self._agent_prompt_text.get("1.0", "end").strip()
        self._selected_agent.can_create_agents = self._can_create_agents_var.get()
        self._selected_agent.heartbeat_interval = self._heartbeat_interval_var.get()

        try:
            self._selected_agent.room_wpm = int(self._detail_wpm_var.get())
        except ValueError:
            pass

        self._database.save_agent(self._selected_agent)
        self._refresh_agent_list()
        self._status_var.set(f"Saved agent {self._selected_agent.id}")

    def _refresh_add_agent_combo(self) -> None:
        """Refresh the dropdown of agents that can be added to the room."""
        if not self._selected_room:
            self._add_agent_combo.configure(values=[])
            return

        room_agents = self._room_service.get_agents_in_room(self._selected_room.id)
        room_agent_ids = {a.id for a in room_agents}

        all_agents = self._database.get_all_agents()
        available = [a for a in all_agents if a.id not in room_agent_ids and not a.is_architect]

        options = [f"{a.id}: {a.name or 'Unnamed'}" for a in available]
        self._add_agent_combo.configure(values=options)
        self._available_agents_to_add = available

    def _add_agent_to_room(self) -> None:
        """Add the selected agent to the current room."""
        if not self._selected_room:
            return

        selection = self._add_agent_var.get()
        if not selection or not hasattr(self, '_available_agents_to_add'):
            return

        # Find the agent by the selection string
        for agent in self._available_agents_to_add:
            if selection.startswith(f"{agent.id}:"):
                self._room_service.join_room(agent, self._selected_room.id)
                self._update_room_status()
                self._refresh_add_agent_combo()
                self._add_agent_var.set("")
                break

    def _update_room_status(self) -> None:
        """Update the room members display."""
        # Clear existing widgets
        for widget in self._members_scroll.winfo_children():
            widget.destroy()
        self._member_widgets = {}

        if not self._selected_room:
            ctk.CTkLabel(self._members_scroll, text="No room selected", text_color="gray").pack(pady=6)
            return

        self._room_agents_list = self._room_service.get_agents_in_room(self._selected_room.id)

        if not self._room_agents_list:
            ctk.CTkLabel(self._members_scroll, text="No agents in room", text_color="gray").pack(pady=6)
            return

        owner_id = self._selected_room.id
        sorted_agents = sorted(self._room_agents_list, key=lambda a: (0 if a.id == owner_id else 1, a.id))

        for agent in sorted_agents:
            is_owner = agent.id == owner_id

            if agent.is_architect:
                display = "The Architect"
            elif is_owner:
                display = f"★ {agent.name or 'Unnamed'} (#{agent.id})"
            else:
                display = f"   {agent.name or 'Unnamed'} (#{agent.id})"

            color = "#ffd700" if is_owner else "#58a6ff"
            status = agent.status if agent.status else "idle"
            status_color = {"idle": "#7ee787", "thinking": "#ffa657", "typing": "#79c0ff", "sleeping": "#8b8b8b"}.get(status, "#7ee787")

            member_frame = ctk.CTkFrame(self._members_scroll, fg_color="transparent")
            member_frame.pack(fill="x", pady=1)

            ctk.CTkLabel(member_frame, text=display, text_color=color, anchor="w").pack(side="left")
            ctk.CTkLabel(member_frame, text=f" ● {status}", text_color=status_color).pack(side="left")

    def _refresh_messages(self) -> None:
        """Refresh the messages display for selected room."""
        self._messages_text.configure(state="normal")
        self._messages_text.delete("1.0", "end")

        if not self._selected_room:
            self._messages_text.insert("end", "No room selected")
            self._messages_text.configure(state="disabled")
            return

        messages = self._room_service.get_room_messages(self._selected_room.id)

        # Build lookup for reply references
        msg_lookup = {msg.id: msg for msg in messages if msg.id}

        # Reaction emoji mapping
        reaction_emoji = {
            "thumbs_up": "👍",
            "thumbs_down": "👎",
            "brain": "🧠",
            "heart": "❤️"
        }

        for msg in messages:
            timestamp = msg.timestamp.strftime("%H:%M:%S")

            # Get sender name
            if msg.sender_name == "System":
                sender_display = ""
                content_prefix = f"[{timestamp}] "
            elif msg.sender_name in ["The Architect", "User"]:
                sender_display = msg.sender_name
                content_prefix = f"[{timestamp}] {sender_display}: "
            elif msg.sender_name.isdigit():
                agent_id = int(msg.sender_name)
                agent = self._database.get_agent(agent_id)
                sender_display = f"{agent.name} (#{agent_id})" if agent and agent.name else f"Agent #{agent_id}"
                content_prefix = f"[{timestamp}] {sender_display}: "
            else:
                sender_display = msg.sender_name
                content_prefix = f"[{timestamp}] {sender_display}: "

            # Show reply reference if this is a reply
            if msg.reply_to_id and msg.reply_to_id in msg_lookup:
                replied_msg = msg_lookup[msg.reply_to_id]
                replied_sender = replied_msg.sender_name
                if replied_sender.isdigit():
                    replied_agent = self._database.get_agent(int(replied_sender))
                    replied_sender = replied_agent.name if replied_agent and replied_agent.name else f"#{replied_sender}"
                elif replied_sender in ["The Architect", "User"]:
                    pass  # Keep as is
                else:
                    replied_sender = replied_sender[:20]

                preview = replied_msg.content[:40] + "..." if len(replied_msg.content) > 40 else replied_msg.content
                self._messages_text.insert("end", f"  ↩ {replied_sender}: {preview}\n", "reply_ref")

            # Insert main message
            if msg.sender_name == "System":
                self._messages_text.insert("end", f"{content_prefix}{msg.content}")
            else:
                self._messages_text.insert("end", f"{content_prefix}{msg.content}")

            # Get and display reactions
            if msg.id:
                reactions = self._database.get_reactions_summary(msg.id)
                if reactions:
                    reaction_str = " "
                    for reaction_type, count in reactions.items():
                        emoji = reaction_emoji.get(reaction_type, "?")
                        reaction_str += f"{emoji}{count} "
                    self._messages_text.insert("end", reaction_str, "reactions")

            self._messages_text.insert("end", "\n\n")

        self._messages_text.configure(state="disabled")
        self._messages_text.see("end")

    def _on_messages_changed(self) -> None:
        """Handle messages changed event."""
        self._root.after(0, self._refresh_messages)

    def _on_agent_status_changed(self, agent: AIAgent) -> None:
        """Handle agent status change."""
        self._root.after(0, self._refresh_agent_list)
        self._root.after(0, self._update_room_status)
        if self._selected_agent and agent.id == self._selected_agent.id:
            self._root.after(0, lambda: self._update_selected_agent_status(agent))

    def _update_selected_agent_status(self, agent: AIAgent) -> None:
        """Update status display for selected agent."""
        status = agent.status if agent.status else "idle"
        status_text = {"idle": "● Idle", "thinking": "◐ Waiting...", "typing": "⌨ Typing...", "sending": "↑ Sending...", "sleeping": "💤 Sleeping"}.get(status, f"● {status}")
        color = {"idle": "#7ee787", "thinking": "#ffa657", "typing": "#79c0ff", "sending": "#d2a8ff", "sleeping": "#8b8b8b"}.get(status, "#7ee787")
        self._heartbeat_status_var.set(status_text)
        self._heartbeat_status_label.configure(text_color=color)
        self._agent_name_var.set(agent.name)

    def _on_status_update(self, message: str) -> None:
        """Handle status update."""
        self._root.after(0, lambda: self._status_var.set(message))
        if "is typing" in message:
            self._root.after(0, lambda: self._typing_var.set(message))
        elif "responded" in message or "thinking" in message:
            self._root.after(0, lambda: self._typing_var.set(""))

    def _on_rooms_changed(self) -> None:
        """Handle rooms list change."""
        self._root.after(0, self._refresh_agent_list)

    def _on_membership_changed(self, room_id: int) -> None:
        """Handle room membership change."""
        if self._selected_room and self._selected_room.id == room_id:
            self._root.after(0, self._update_room_status)

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

        self._room_service.send_message(self._selected_room.id, "The Architect", message)
        self._message_var.set("")
        self._refresh_messages()

    def _toggle_heartbeat(self) -> None:
        """Toggle heartbeat service."""
        if self._heartbeat.is_running:
            self._heartbeat.stop()
            self._heartbeat_btn_text.set("▶ Start")
        else:
            if not self._openai.has_api_key:
                messagebox.showerror("Error", "Please connect to OpenAI first (File > Settings)")
                return

            self._heartbeat.start()
            self._heartbeat_btn_text.set("⏹ Stop")

    def _clear_chat(self) -> None:
        """Clear chat messages in selected room."""
        if not self._selected_room:
            messagebox.showwarning("Warning", "Please select a room first")
            return

        if messagebox.askyesno("Confirm", f"Clear all messages in room {self._selected_room.id}?"):
            self._room_service.clear_room_messages(self._selected_room.id)
            self._refresh_messages()
            self._status_var.set(f"Chat cleared")

    def _open_settings(self) -> None:
        """Open the settings dialog."""
        dialog = SettingsDialog(self._root, self._openai, on_connected=self._refresh_agent_list)

    def _open_prompt_editor(self) -> None:
        """Open the prompt editor dialog."""
        dialog = PromptEditorDialog(self._root)

    def _open_knowledge_explorer(self) -> None:
        """Open the knowledge explorer for the selected agent."""
        if not self._selected_agent:
            messagebox.showwarning("No Agent", "Please select an agent first.")
            return
        dialog = KnowledgeExplorerDialog(self._root, self._selected_agent, self._database)

    def _open_hud_history(self) -> None:
        """Open the HUD history viewer for the selected agent."""
        if not self._selected_agent:
            messagebox.showwarning("No Agent", "Please select an agent first.")
            return
        dialog = HUDHistoryDialog(self._root, self._selected_agent, self._heartbeat)

    def _open_toon_telemetry(self) -> None:
        """Open the TOON telemetry viewer to compare format efficiency."""
        dialog = TOONTelemetryDialog(self._root)

    def _on_close(self) -> None:
        """Handle window close."""
        logger.info("Application closing")

        self._heartbeat.cleanup()
        self._room_service.cleanup()

        if hasattr(self._openai, '_client') and self._openai._client:
            try:
                self._openai._client.close()
            except Exception as e:
                logger.debug(f"Error closing OpenAI client: {e}")

        logger.info("All services cleaned up")
        self._root.destroy()

    def run(self) -> None:
        """Run the application."""
        self._root.mainloop()
