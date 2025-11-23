"""Pop-out dialogs for agent and room management."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import List, Optional, Callable
import os
from models import AIAgent, ChatRoom, RoomMembership, SelfConcept
from services import DatabaseService, RoomService
import config


class AgentManagerDialog(tk.Toplevel):
    """Pop-out window for agent creation and management."""

    def __init__(
        self,
        parent,
        database: DatabaseService,
        room_service: RoomService,
        available_models: List[str],
        on_agent_changed: Callable = None
    ):
        super().__init__(parent)
        self.title("Agent Manager")
        self.geometry("600x500")
        self.transient(parent)

        self._database = database
        self._room_service = room_service
        self._available_models = available_models
        self._on_agent_changed = on_agent_changed
        self._selected_agent: Optional[AIAgent] = None

        # Dark mode colors
        self._bg_dark = "#252525"
        self._bg_medium = "#333333"
        self._fg_light = "#cccccc"

        self.configure(bg=self._bg_dark)
        self._setup_ui()
        self._refresh_agents()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # Left panel - agent list
        left_frame = tk.Frame(self, bg=self._bg_dark)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)

        tk.Label(left_frame, text="Agents", bg=self._bg_dark, fg=self._fg_light,
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        self._agent_listbox = tk.Listbox(
            left_frame, width=20, height=15,
            bg=self._bg_medium, fg=self._fg_light,
            selectbackground="#555555"
        )
        self._agent_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self._agent_listbox.bind('<<ListboxSelect>>', self._on_agent_select)

        # Buttons
        btn_frame = tk.Frame(left_frame, bg=self._bg_dark)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="New", command=self._create_agent).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete_agent).pack(side=tk.LEFT, padx=2)

        # Right panel - agent details
        right_frame = tk.Frame(self, bg=self._bg_dark)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Agent Type
        tk.Label(right_frame, text="Type:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W)
        self._type_var = tk.StringVar(value="persona")
        type_frame = tk.Frame(right_frame, bg=self._bg_dark)
        type_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Radiobutton(type_frame, text="Persona", variable=self._type_var, value="persona",
                       bg=self._bg_dark, fg=self._fg_light, selectcolor=self._bg_medium,
                       activebackground=self._bg_dark, activeforeground=self._fg_light,
                       command=self._on_type_changed).pack(side=tk.LEFT)
        tk.Radiobutton(type_frame, text="Bot", variable=self._type_var, value="bot",
                       bg=self._bg_dark, fg=self._fg_light, selectcolor=self._bg_medium,
                       activebackground=self._bg_dark, activeforeground=self._fg_light,
                       command=self._on_type_changed).pack(side=tk.LEFT)

        # Name
        tk.Label(right_frame, text="Name:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W)
        self._name_var = tk.StringVar()
        self._name_entry = tk.Entry(right_frame, textvariable=self._name_var,
                                    bg=self._bg_medium, fg=self._fg_light,
                                    insertbackground=self._fg_light)
        self._name_entry.pack(fill=tk.X, pady=(0, 10))

        # Model
        tk.Label(right_frame, text="Model:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W)
        self._model_var = tk.StringVar()
        self._model_combo = ttk.Combobox(right_frame, textvariable=self._model_var,
                                         values=self._available_models)
        self._model_combo.pack(fill=tk.X, pady=(0, 10))

        # Background prompt / Role (label changes based on type)
        self._prompt_label = tk.Label(right_frame, text="Background Prompt:", bg=self._bg_dark, fg=self._fg_light)
        self._prompt_label.pack(anchor=tk.W)
        self._prompt_text = tk.Text(right_frame, height=8,
                                    bg=self._bg_medium, fg=self._fg_light,
                                    insertbackground=self._fg_light, wrap=tk.WORD)
        self._prompt_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Status info
        tk.Label(right_frame, text="Status:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W)
        self._status_text = tk.Text(right_frame, height=4, state=tk.DISABLED,
                                    bg=self._bg_medium, fg=self._fg_light, wrap=tk.WORD)
        self._status_text.pack(fill=tk.X, pady=(0, 10))

        # Self-concept browser
        tk.Label(right_frame, text="Self-Concept:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W)
        self._concept_text = tk.Text(right_frame, height=8, state=tk.DISABLED,
                                     bg=self._bg_medium, fg=self._fg_light, wrap=tk.WORD,
                                     font=("Consolas", 9))
        self._concept_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Configure tags for self-concept display
        self._concept_text.tag_configure("header", foreground="#58a6ff", font=("Consolas", 9, "bold"))
        self._concept_text.tag_configure("id", foreground="#7ee787")
        self._concept_text.tag_configure("content", foreground="#cccccc")
        self._concept_text.tag_configure("dim", foreground="#666666")

        # Save button
        ttk.Button(right_frame, text="Save Changes", command=self._save_agent).pack(anchor=tk.E)

    def _refresh_agents(self):
        """Refresh the agent list."""
        self._agent_listbox.delete(0, tk.END)
        agents = self._database.get_all_agents()
        for agent in agents:
            # Show room count
            memberships = self._database.get_agent_memberships(agent.id)
            room_count = len(memberships)
            # Display as ID for AI agents, special name for Architect
            if agent.is_architect:
                display = f"The Architect ({room_count} rooms)"
            else:
                display = f"Agent {agent.id} ({room_count} rooms)"
            self._agent_listbox.insert(tk.END, display)

    def _on_agent_select(self, event):
        """Handle agent selection."""
        selection = self._agent_listbox.curselection()
        if not selection:
            return

        agents = self._database.get_all_agents()
        if selection[0] < len(agents):
            self._selected_agent = agents[selection[0]]
            self._load_agent_details()

    def _on_type_changed(self):
        """Handle agent type change - update label."""
        if self._type_var.get() == "bot":
            self._prompt_label.config(text="Role:")
        else:
            self._prompt_label.config(text="Background Prompt:")

    def _load_agent_details(self):
        """Load selected agent's details into the form."""
        if not self._selected_agent:
            return

        agent = self._selected_agent
        self._type_var.set(agent.agent_type)
        self._on_type_changed()  # Update label
        self._name_var.set(agent.name)
        self._model_var.set(agent.model)

        self._prompt_text.delete("1.0", tk.END)
        self._prompt_text.insert("1.0", agent.background_prompt)

        # Build status info
        memberships = self._database.get_agent_memberships(agent.id)
        self_concept = SelfConcept.from_json(agent.self_concept_json)

        status_lines = [
            f"Tokens used: {agent.total_tokens_used}",
            f"Rooms: {len(memberships)}",
            f"Topic: {agent.room_topic or '(none)'}"
        ]

        self._status_text.config(state=tk.NORMAL)
        self._status_text.delete("1.0", tk.END)
        self._status_text.insert("1.0", "\n".join(status_lines))
        self._status_text.config(state=tk.DISABLED)

        # Build self-concept display (flexible JSON store)
        self._concept_text.config(state=tk.NORMAL)
        self._concept_text.delete("1.0", tk.END)

        knowledge = self_concept.to_dict()
        if knowledge:
            self._display_knowledge_tree(knowledge, "")
        else:
            self._concept_text.insert(tk.END, "(empty knowledge store)\n", "dim")

        self._concept_text.config(state=tk.DISABLED)

    def _display_knowledge_tree(self, data, indent: str):
        """Display knowledge tree recursively."""
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, dict):
                    # Check if it's a weighted value
                    if set(value.keys()) == {'v', 'w'}:
                        self._concept_text.insert(tk.END, f"{indent}{key}: ", "id")
                        self._concept_text.insert(tk.END, f"{value['v']} (w={value['w']})\n", "content")
                    else:
                        self._concept_text.insert(tk.END, f"{indent}{key}:\n", "header")
                        self._display_knowledge_tree(value, indent + "  ")
                elif isinstance(value, list):
                    self._concept_text.insert(tk.END, f"{indent}{key}: [{len(value)} items]\n", "header")
                    for i, item in enumerate(value):
                        if isinstance(item, (dict, list)):
                            self._concept_text.insert(tk.END, f"{indent}  [{i}]:\n", "id")
                            self._display_knowledge_tree(item, indent + "    ")
                        else:
                            self._concept_text.insert(tk.END, f"{indent}  [{i}]: ", "id")
                            self._concept_text.insert(tk.END, f"{item}\n", "content")
                else:
                    self._concept_text.insert(tk.END, f"{indent}{key}: ", "id")
                    self._concept_text.insert(tk.END, f"{value}\n", "content")

    def _create_agent(self):
        """Create a new agent, optionally in a room."""
        # Get available rooms
        rooms = self._room_service.get_all_rooms()

        # Build room selection list with "None" option first
        room_options = ["None (self-room only)"]
        for room in rooms:
            if room.name == "The Architect":
                room_options.append(f"The Architect (ID: {room.id})")
            else:
                room_options.append(f"Room {room.id}")

        # Create selection dialog
        selection_dialog = tk.Toplevel(self)
        selection_dialog.title("Create Agent")
        selection_dialog.geometry("300x200")
        selection_dialog.transient(self)
        selection_dialog.configure(bg=self._bg_dark)

        tk.Label(selection_dialog, text="Create agent in room:",
                 bg=self._bg_dark, fg=self._fg_light).pack(pady=5)

        room_var = tk.StringVar()
        room_combo = ttk.Combobox(selection_dialog, textvariable=room_var,
                                   values=room_options, state="readonly")
        room_combo.pack(padx=10, fill=tk.X)
        if room_options:
            room_combo.current(0)

        tk.Label(selection_dialog, text="Agent name:",
                 bg=self._bg_dark, fg=self._fg_light).pack(pady=(10, 5))

        name_var = tk.StringVar()
        name_entry = tk.Entry(selection_dialog, textvariable=name_var,
                              bg=self._bg_medium, fg=self._fg_light)
        name_entry.pack(padx=10, fill=tk.X)

        def on_create():
            name = name_var.get().strip()
            if not name:
                messagebox.showwarning("Warning", "Please enter a name", parent=selection_dialog)
                return

            # Parse room ID from selection
            selected = room_var.get()
            room_id = None

            # Check if "None" was selected (self-room only)
            if selected != "None (self-room only)":
                for room in rooms:
                    display = "The Architect" if room.name == "The Architect" else f"Room {room.id}"
                    if selected.startswith(display):
                        room_id = room.id
                        break

            try:
                agent = self._room_service.create_agent(
                    name=name,
                    background_prompt="",
                    in_room_id=room_id,  # None for self-room only
                    model=self._available_models[0] if self._available_models else "gpt-4o-mini"
                )
                selection_dialog.destroy()
                self._refresh_agents()
                if self._on_agent_changed:
                    self._on_agent_changed()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=selection_dialog)

        ttk.Button(selection_dialog, text="Create", command=on_create).pack(pady=10)

    def _delete_agent(self):
        """Delete the selected agent."""
        if not self._selected_agent:
            return

        if messagebox.askyesno("Delete Agent",
                               f"Delete agent '{self._selected_agent.name}'?",
                               parent=self):
            # Remove from all rooms first
            memberships = self._database.get_agent_memberships(self._selected_agent.id)
            for m in memberships:
                self._database.delete_membership(self._selected_agent.id, m.room_id)

            self._database.delete_agent(self._selected_agent.id)
            self._selected_agent = None
            self._refresh_agents()

            if self._on_agent_changed:
                self._on_agent_changed()

    def _save_agent(self):
        """Save changes to the selected agent."""
        if not self._selected_agent:
            return

        self._selected_agent.agent_type = self._type_var.get()
        self._selected_agent.name = self._name_var.get()
        self._selected_agent.model = self._model_var.get()
        self._selected_agent.background_prompt = self._prompt_text.get("1.0", tk.END).strip()

        self._database.save_agent(self._selected_agent)
        self._refresh_agents()

        if self._on_agent_changed:
            self._on_agent_changed()

        agent_type = "Bot" if self._selected_agent.agent_type == "bot" else "Persona"
        messagebox.showinfo("Saved", f"{agent_type} saved.", parent=self)


class RoomManagerDialog(tk.Toplevel):
    """Pop-out window for room creation and management."""

    def __init__(
        self,
        parent,
        database: DatabaseService,
        room_service: RoomService,
        on_room_changed: Callable = None
    ):
        super().__init__(parent)
        self.title("Room Manager")
        self.geometry("500x400")
        self.transient(parent)

        self._database = database
        self._room_service = room_service
        self._on_room_changed = on_room_changed
        self._selected_room: Optional[ChatRoom] = None

        # Dark mode colors
        self._bg_dark = "#252525"
        self._bg_medium = "#333333"
        self._fg_light = "#cccccc"

        self.configure(bg=self._bg_dark)
        self._setup_ui()
        self._refresh_rooms()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # Left panel - room list
        left_frame = tk.Frame(self, bg=self._bg_dark)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, padx=5, pady=5)

        tk.Label(left_frame, text="Rooms", bg=self._bg_dark, fg=self._fg_light,
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        self._room_listbox = tk.Listbox(
            left_frame, width=20, height=12,
            bg=self._bg_medium, fg=self._fg_light,
            selectbackground="#555555"
        )
        self._room_listbox.pack(fill=tk.BOTH, expand=True, pady=5)
        self._room_listbox.bind('<<ListboxSelect>>', self._on_room_select)

        # Buttons
        btn_frame = tk.Frame(left_frame, bg=self._bg_dark)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="New", command=self._create_room).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="Delete", command=self._delete_room).pack(side=tk.LEFT, padx=2)

        # Right panel - room members
        right_frame = tk.Frame(self, bg=self._bg_dark)
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

        tk.Label(right_frame, text="Room Members:", bg=self._bg_dark, fg=self._fg_light,
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        # Members list
        self._members_listbox = tk.Listbox(
            right_frame, height=8,
            bg=self._bg_medium, fg=self._fg_light,
            selectbackground="#555555"
        )
        self._members_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

        # Add/remove buttons
        member_btn_frame = tk.Frame(right_frame, bg=self._bg_dark)
        member_btn_frame.pack(fill=tk.X)

        ttk.Button(member_btn_frame, text="Add Agent", command=self._add_agent).pack(side=tk.LEFT, padx=2)
        ttk.Button(member_btn_frame, text="Remove", command=self._remove_agent).pack(side=tk.LEFT, padx=2)

        # Available agents
        tk.Label(right_frame, text="Available Agents:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W, pady=(10, 0))

        self._available_listbox = tk.Listbox(
            right_frame, height=6,
            bg=self._bg_medium, fg=self._fg_light,
            selectbackground="#555555"
        )
        self._available_listbox.pack(fill=tk.BOTH, expand=True, pady=5)

    def _refresh_rooms(self):
        """Refresh the room list."""
        self._room_listbox.delete(0, tk.END)
        rooms = self._room_service.get_all_rooms()
        for room in rooms:
            members = self._database.get_room_members(room.id)
            # Show ID-based display
            if room.name == "The Architect":
                display = f"The Architect ({len(members)})"
            else:
                display = f"Room {room.id} ({len(members)})"
            self._room_listbox.insert(tk.END, display)

    def _on_room_select(self, event):
        """Handle room selection."""
        selection = self._room_listbox.curselection()
        if not selection:
            return

        rooms = self._room_service.get_all_rooms()
        if selection[0] < len(rooms):
            self._selected_room = rooms[selection[0]]
            self._refresh_members()

    def _refresh_members(self):
        """Refresh the members list for selected room."""
        self._members_listbox.delete(0, tk.END)
        self._available_listbox.delete(0, tk.END)

        if not self._selected_room:
            return

        # Get current members
        memberships = self._database.get_room_members(self._selected_room.id)
        member_ids = set()

        for m in memberships:
            agent = self._database.get_agent(m.agent_id)
            if agent:
                # Show ID-based display
                if agent.is_architect:
                    display = "The Architect"
                else:
                    display = f"Agent {agent.id}"
                self._members_listbox.insert(tk.END, display)
                member_ids.add(agent.id)

        # Get available agents (not in room)
        all_agents = self._database.get_all_agents()
        for agent in all_agents:
            if agent.id not in member_ids:
                # Show ID-based display
                if agent.is_architect:
                    display = "The Architect"
                else:
                    display = f"Agent {agent.id}"
                self._available_listbox.insert(tk.END, display)

    def _create_room(self):
        """Create a new room - in this architecture, rooms are agents."""
        # Rooms ARE agents, so we need to create an agent
        messagebox.showinfo(
            "Create Room",
            "In this architecture, each agent IS a room.\n\n"
            "Use the Agent Manager to create new agents.\n"
            "Each agent you create becomes its own room.",
            parent=self
        )

    def _delete_room(self):
        """Delete the selected room (which is an agent)."""
        if not self._selected_room:
            return

        # Show ID-based display name
        if self._selected_room.name == "The Architect":
            display = "The Architect"
        else:
            display = f"Room {self._selected_room.id}"

        if messagebox.askyesno("Delete Room",
                               f"Delete {display}?\n\n"
                               f"This will delete the agent and all its memberships.",
                               parent=self):
            self._room_service.delete_room(self._selected_room.id)
            self._selected_room = None
            self._refresh_rooms()

            if self._on_room_changed:
                self._on_room_changed()

    def _add_agent(self):
        """Add selected agent to room."""
        if not self._selected_room:
            return

        selection = self._available_listbox.curselection()
        if not selection:
            return

        # Find the agent
        all_agents = self._database.get_all_agents()
        memberships = self._database.get_room_members(self._selected_room.id)
        member_ids = {m.agent_id for m in memberships}

        available = [a for a in all_agents if a.id not in member_ids]
        if selection[0] < len(available):
            agent = available[selection[0]]
            self._room_service.join_room(agent, self._selected_room.id)
            self._refresh_members()

            if self._on_room_changed:
                self._on_room_changed()

    def _remove_agent(self):
        """Remove selected agent from room."""
        if not self._selected_room:
            return

        selection = self._members_listbox.curselection()
        if not selection:
            return

        memberships = self._database.get_room_members(self._selected_room.id)
        if selection[0] < len(memberships):
            membership = memberships[selection[0]]
            self._room_service.leave_room(membership.agent_id, self._selected_room.id)
            self._refresh_members()

            if self._on_room_changed:
                self._on_room_changed()


class KnowledgeExplorerDialog(tk.Toplevel):
    """Pop-out window for exploring agent's knowledge tree."""

    def __init__(self, parent, agent: AIAgent, database: DatabaseService):
        super().__init__(parent)
        self.title(f"Knowledge Explorer - Agent {agent.id}")
        self.geometry("500x600")
        self.transient(parent)

        self._agent = agent
        self._database = database

        # Dark mode colors
        self._bg_dark = "#252525"
        self._bg_medium = "#333333"
        self._fg_light = "#cccccc"

        self.configure(bg=self._bg_dark)
        self._setup_ui()
        self._load_knowledge()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # Header
        header = tk.Frame(self, bg=self._bg_dark)
        header.pack(fill=tk.X, padx=10, pady=10)

        tk.Label(
            header, text=f"Agent {self._agent.id}: {self._agent.name}",
            bg=self._bg_dark, fg=self._fg_light,
            font=("Segoe UI", 12, "bold")
        ).pack(anchor=tk.W)

        # Tree view
        tree_frame = tk.Frame(self, bg=self._bg_dark)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # Treeview with scrollbar
        self._tree = ttk.Treeview(tree_frame, show="tree")
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Refresh button
        btn_frame = tk.Frame(self, bg=self._bg_dark)
        btn_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        ttk.Button(btn_frame, text="Refresh", command=self._load_knowledge).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT)

    def _load_knowledge(self):
        """Load and display the agent's knowledge tree."""
        # Clear existing items
        for item in self._tree.get_children():
            self._tree.delete(item)

        # Reload agent from database
        self._agent = self._database.get_agent(self._agent.id)
        if not self._agent:
            return

        # Parse knowledge
        self_concept = SelfConcept.from_json(self._agent.self_concept_json)
        knowledge = self_concept.to_dict()

        # Build tree
        self._add_dict_to_tree("", knowledge, "")

    def _add_dict_to_tree(self, parent: str, data, path: str):
        """Recursively add dictionary items to tree."""
        if isinstance(data, dict):
            for key, value in data.items():
                new_path = f"{path}.{key}" if path else key
                if isinstance(value, dict):
                    # Check if it's a weighted value
                    if set(value.keys()) == {'v', 'w'}:
                        # Display weighted value
                        display = f"{key}: {value['v']} (w={value['w']})"
                        self._tree.insert(parent, tk.END, text=display)
                    else:
                        # Regular dict - create node and recurse
                        node_id = self._tree.insert(parent, tk.END, text=key, open=True)
                        self._add_dict_to_tree(node_id, value, new_path)
                elif isinstance(value, list):
                    # Array
                    node_id = self._tree.insert(parent, tk.END, text=f"{key} [{len(value)}]", open=True)
                    for i, item in enumerate(value):
                        if isinstance(item, (dict, list)):
                            item_id = self._tree.insert(node_id, tk.END, text=f"[{i}]", open=True)
                            self._add_dict_to_tree(item_id, item, f"{new_path}.{i}")
                        else:
                            self._tree.insert(node_id, tk.END, text=f"[{i}]: {item}")
                else:
                    # Simple value
                    self._tree.insert(parent, tk.END, text=f"{key}: {value}")
        elif isinstance(data, list):
            for i, item in enumerate(data):
                if isinstance(item, (dict, list)):
                    item_id = self._tree.insert(parent, tk.END, text=f"[{i}]", open=True)
                    self._add_dict_to_tree(item_id, item, f"{path}.{i}")
                else:
                    self._tree.insert(parent, tk.END, text=f"[{i}]: {item}")


class SettingsDialog(tk.Toplevel):
    """Pop-out window for API settings and connection."""

    def __init__(self, parent, openai_service, on_connected=None):
        super().__init__(parent)
        self.title("Settings")
        self.geometry("500x250")
        self.transient(parent)

        self._openai = openai_service
        self._on_connected = on_connected

        # Dark mode colors
        self._bg_dark = "#252525"
        self._bg_medium = "#333333"
        self._fg_light = "#cccccc"

        self.configure(bg=self._bg_dark)
        self._setup_ui()
        self._load_api_key()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # API Key section
        frame = tk.Frame(self, bg=self._bg_dark, padx=20, pady=20)
        frame.pack(fill=tk.BOTH, expand=True)

        tk.Label(
            frame, text="OpenAI API Settings",
            bg=self._bg_dark, fg=self._fg_light,
            font=("Segoe UI", 12, "bold")
        ).pack(anchor=tk.W, pady=(0, 15))

        # API Key
        tk.Label(frame, text="API Key:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W)
        self._api_key_var = tk.StringVar()
        api_entry = tk.Entry(
            frame, textvariable=self._api_key_var, show="*", width=50,
            bg=self._bg_medium, fg=self._fg_light, insertbackground=self._fg_light
        )
        api_entry.pack(fill=tk.X, pady=(0, 10))

        # Status
        self._status_var = tk.StringVar(value="Not connected")
        tk.Label(frame, textvariable=self._status_var, bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W, pady=(0, 15))

        # Buttons
        btn_frame = tk.Frame(frame, bg=self._bg_dark)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="Test Connection", command=self._test_connection).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT)

    def _load_api_key(self):
        """Load API key from keyring."""
        try:
            import keyring
            api_key = keyring.get_password(config.KEYRING_SERVICE, config.KEYRING_USERNAME)
            if api_key:
                self._api_key_var.set(api_key)
                if self._openai.has_api_key:
                    self._status_var.set("Connected")
        except Exception:
            pass  # Keyring not available or empty

    def _test_connection(self):
        """Test API connection."""
        api_key = self._api_key_var.get().strip()
        if not api_key:
            self._status_var.set("Please enter an API key")
            return

        self._openai.set_api_key(api_key)
        self._status_var.set("Testing...")
        self.update()

        success, message = self._openai.test_connection()
        self._status_var.set(message)

        if success:
            # Save API key
            try:
                import keyring
                keyring.set_password(config.KEYRING_SERVICE, config.KEYRING_USERNAME, api_key)
            except Exception:
                pass  # Keyring not available

            if self._on_connected:
                self._on_connected()


class PromptEditorDialog(tk.Toplevel):
    """Pop-out window for editing agent prompts as a dynamic JSON tree."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Prompt Editor - JSON Tree")
        self.geometry("1000x700")
        self.transient(parent)

        # Dark mode colors
        self._bg_dark = "#252525"
        self._bg_medium = "#333333"
        self._fg_light = "#cccccc"

        self.configure(bg=self._bg_dark)

        # Store the JSON data
        self._data = {}
        self._selected_path = []  # Path to currently selected node

        self._setup_ui()
        self._load_prompts()

    def _setup_ui(self):
        """Set up the dialog UI with tree view and editor."""
        # Header
        header = tk.Frame(self, bg=self._bg_dark, padx=10, pady=10)
        header.pack(fill=tk.X)

        tk.Label(
            header, text="Prompt Configuration",
            bg=self._bg_dark, fg=self._fg_light,
            font=("Segoe UI", 12, "bold")
        ).pack(anchor=tk.W)

        tk.Label(
            header, text="Edit the JSON tree structure. Select a node to edit its values.",
            bg=self._bg_dark, fg="#888888",
            font=("Segoe UI", 9)
        ).pack(anchor=tk.W)

        # Main content - split into tree and editor
        content = tk.Frame(self, bg=self._bg_dark)
        content.pack(fill=tk.BOTH, expand=True, padx=10)

        # Left: Tree view
        tree_frame = tk.Frame(content, bg=self._bg_dark)
        tree_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        tk.Label(tree_frame, text="Structure:", bg=self._bg_dark, fg=self._fg_light,
                font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        # Treeview with scrollbar
        tree_container = tk.Frame(tree_frame, bg=self._bg_dark)
        tree_container.pack(fill=tk.BOTH, expand=True)

        self._tree = ttk.Treeview(tree_container, show="tree")
        tree_scroll = ttk.Scrollbar(tree_container, orient=tk.VERTICAL, command=self._tree.yview)
        self._tree.configure(yscrollcommand=tree_scroll.set)

        self._tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self._tree.bind('<<TreeviewSelect>>', self._on_tree_select)

        # Tree buttons
        tree_btn_frame = tk.Frame(tree_frame, bg=self._bg_dark)
        tree_btn_frame.pack(fill=tk.X, pady=(5, 0))

        ttk.Button(tree_btn_frame, text="Add Node", command=self._add_node).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(tree_btn_frame, text="Delete Node", command=self._delete_node).pack(side=tk.LEFT)

        # Right: Editor panel
        editor_frame = tk.Frame(content, bg=self._bg_dark, width=400)
        editor_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))
        editor_frame.pack_propagate(False)

        tk.Label(editor_frame, text="Edit Node:", bg=self._bg_dark, fg=self._fg_light,
                font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        # Path display
        self._path_var = tk.StringVar(value="(select a node)")
        tk.Label(editor_frame, textvariable=self._path_var, bg=self._bg_dark, fg="#58a6ff",
                font=("Consolas", 9)).pack(anchor=tk.W, pady=(0, 10))

        # Description field
        tk.Label(editor_frame, text="Description:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W)
        self._desc_text = tk.Text(editor_frame, height=2, wrap=tk.WORD,
                                  bg=self._bg_medium, fg=self._fg_light,
                                  insertbackground=self._fg_light, font=("Consolas", 10))
        self._desc_text.pack(fill=tk.X, pady=(0, 10))

        # Content field
        tk.Label(editor_frame, text="Content:", bg=self._bg_dark, fg=self._fg_light).pack(anchor=tk.W)
        self._content_text = tk.Text(editor_frame, wrap=tk.WORD,
                                     bg=self._bg_medium, fg=self._fg_light,
                                     insertbackground=self._fg_light, font=("Consolas", 10))
        self._content_text.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Update button
        ttk.Button(editor_frame, text="Update Node", command=self._update_node).pack(anchor=tk.W)

        # Bottom buttons
        btn_frame = tk.Frame(self, bg=self._bg_dark)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(btn_frame, text="Save All", command=self._save_prompts).pack(side=tk.LEFT)
        ttk.Button(btn_frame, text="Reload", command=self._load_prompts).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(btn_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT)

    def _load_prompts(self):
        """Load prompts from JSON file."""
        try:
            import prompts
            self._data = prompts.load_prompts()
            self._refresh_tree()
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load prompts: {e}", parent=self)

    def _refresh_tree(self):
        """Refresh the tree view from data."""
        # Clear existing items
        for item in self._tree.get_children():
            self._tree.delete(item)

        # Build tree recursively
        self._add_dict_to_tree("", self._data, [])

    def _add_dict_to_tree(self, parent: str, data: dict, path: list):
        """Recursively add dictionary items to tree."""
        for key, value in data.items():
            current_path = path + [key]
            path_str = ".".join(current_path)

            if isinstance(value, dict):
                # Check if it's a leaf node (has description/content)
                if "content" in value or "description" in value:
                    # Leaf node - show as editable
                    node_id = self._tree.insert(parent, tk.END, text=f"📝 {key}",
                                               values=(path_str,), open=False)
                else:
                    # Branch node - recurse
                    node_id = self._tree.insert(parent, tk.END, text=f"📁 {key}",
                                               values=(path_str,), open=True)
                    self._add_dict_to_tree(node_id, value, current_path)
            else:
                # Simple value
                node_id = self._tree.insert(parent, tk.END, text=f"{key}: {str(value)[:30]}...",
                                           values=(path_str,))

    def _on_tree_select(self, event):
        """Handle tree selection."""
        selection = self._tree.selection()
        if not selection:
            return

        # Auto-save current node before switching
        if self._selected_path:
            self._auto_save_current_node()

        # Get the path from the tree item
        item = selection[0]
        item_text = self._tree.item(item, 'text')

        # Navigate to the selected node
        self._selected_path = self._get_path_from_item(item)
        path_str = ".".join(self._selected_path)
        self._path_var.set(path_str if path_str else "(root)")

        # Get the node data
        node = self._get_node(self._selected_path)

        # Clear editors
        self._desc_text.delete("1.0", tk.END)
        self._content_text.delete("1.0", tk.END)

        if isinstance(node, dict):
            # Load description and content if available
            if "description" in node:
                self._desc_text.insert("1.0", node.get("description", ""))
            if "content" in node:
                self._content_text.insert("1.0", node.get("content", ""))

    def _auto_save_current_node(self):
        """Auto-save the current node's edits to memory."""
        if not self._selected_path:
            return

        node = self._get_node(self._selected_path)
        if not isinstance(node, dict):
            return

        # Get current editor values
        desc = self._desc_text.get("1.0", tk.END).strip()
        content = self._content_text.get("1.0", tk.END).strip()

        # Only update if this is a content node
        if "content" in node or "description" in node:
            node["description"] = desc
            node["content"] = content

    def _get_path_from_item(self, item) -> list:
        """Get the path list from a tree item."""
        path = []
        while item:
            text = self._tree.item(item, 'text')
            # Remove emoji prefix
            if text.startswith("📝 ") or text.startswith("📁 "):
                text = text[2:].strip()
            elif ": " in text:
                text = text.split(": ")[0]
            path.insert(0, text)
            item = self._tree.parent(item)
        return path

    def _get_node(self, path: list):
        """Get node at path."""
        current = self._data
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None
        return current

    def _set_node(self, path: list, value):
        """Set node value at path."""
        if not path:
            return

        current = self._data
        for key in path[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]

        current[path[-1]] = value

    def _update_node(self):
        """Update the selected node with editor values."""
        if not self._selected_path:
            return

        node = self._get_node(self._selected_path)
        if not isinstance(node, dict):
            return

        # Update description and content
        desc = self._desc_text.get("1.0", tk.END).strip()
        content = self._content_text.get("1.0", tk.END).strip()

        node["description"] = desc
        node["content"] = content

        self._refresh_tree()
        messagebox.showinfo("Updated", f"Node '{'.'.join(self._selected_path)}' updated.", parent=self)

    def _add_node(self):
        """Add a new node."""
        # Get parent path
        if self._selected_path:
            parent_node = self._get_node(self._selected_path)
            if isinstance(parent_node, dict) and "content" in parent_node:
                # Selected node is a leaf, use its parent
                parent_path = self._selected_path[:-1]
            else:
                parent_path = self._selected_path
        else:
            parent_path = []

        # Ask for node name
        name = simpledialog.askstring("Add Node", "Enter node name:", parent=self)
        if not name:
            return

        # Ask if leaf or branch
        is_leaf = messagebox.askyesno(
            "Node Type",
            "Create a content node?\n\nYes = Node with description/content (leaf)\nNo = Container node (branch)",
            parent=self
        )

        if is_leaf:
            # Create new leaf node with description and content
            new_node = {
                "description": "Description of this node",
                "content": "Content goes here"
            }
        else:
            # Create empty branch node
            new_node = {}

        # Add to data
        if parent_path:
            parent = self._get_node(parent_path)
            if isinstance(parent, dict):
                parent[name] = new_node
        else:
            self._data[name] = new_node

        self._refresh_tree()
        messagebox.showinfo("Added", f"Node '{name}' added.", parent=self)

    def _delete_node(self):
        """Delete the selected node."""
        if not self._selected_path:
            messagebox.showwarning("No Selection", "Please select a node to delete.", parent=self)
            return

        path_str = ".".join(self._selected_path)
        if not messagebox.askyesno("Delete Node", f"Delete '{path_str}'?", parent=self):
            return

        # Delete from data
        if len(self._selected_path) == 1:
            del self._data[self._selected_path[0]]
        else:
            parent = self._get_node(self._selected_path[:-1])
            if isinstance(parent, dict):
                del parent[self._selected_path[-1]]

        self._selected_path = []
        self._refresh_tree()
        self._path_var.set("(select a node)")
        self._desc_text.delete("1.0", tk.END)
        self._content_text.delete("1.0", tk.END)

    def _save_prompts(self):
        """Save prompts to JSON file."""
        try:
            # Auto-save current node first
            self._auto_save_current_node()

            import prompts
            if prompts.save_prompts(self._data):
                messagebox.showinfo("Saved", "Prompts saved successfully.\n\nChanges will apply to new agent responses.", parent=self)
            else:
                messagebox.showerror("Error", "Failed to save prompts.", parent=self)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save prompts: {e}", parent=self)


class HUDHistoryDialog(tk.Toplevel):
    """Dialog to view HUD history for an agent."""

    def __init__(self, parent, agent: AIAgent, heartbeat_service):
        super().__init__(parent)
        self.title(f"HUD History - {agent.name} (#{agent.id})")
        self.geometry("1000x700")
        self.transient(parent)

        self._agent = agent
        self._heartbeat = heartbeat_service
        self._history = []
        self._current_index = -1

        # Dark mode colors
        self._bg_dark = "#252525"
        self._bg_medium = "#333333"
        self._bg_light = "#444444"
        self._fg_light = "#cccccc"

        self.configure(bg=self._bg_dark)
        self._setup_ui()
        self._load_history()

    def _setup_ui(self):
        """Set up the dialog UI."""
        # Top bar - navigation
        nav_frame = tk.Frame(self, bg=self._bg_dark)
        nav_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(nav_frame, text="◀ Prev", command=self._prev_entry).pack(side=tk.LEFT)
        ttk.Button(nav_frame, text="Next ▶", command=self._next_entry).pack(side=tk.LEFT, padx=(5, 0))

        self._nav_label = tk.Label(
            nav_frame, text="No history", bg=self._bg_dark, fg=self._fg_light,
            font=("Consolas", 10)
        )
        self._nav_label.pack(side=tk.LEFT, padx=(15, 0))

        ttk.Button(nav_frame, text="Refresh", command=self._load_history).pack(side=tk.RIGHT)
        ttk.Button(nav_frame, text="Clear", command=self._clear_history).pack(side=tk.RIGHT, padx=(0, 5))

        # Entry list on left
        list_frame = tk.Frame(self, bg=self._bg_dark, width=200)
        list_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(10, 0), pady=(0, 10))
        list_frame.pack_propagate(False)

        tk.Label(list_frame, text="Entries", bg=self._bg_dark, fg=self._fg_light,
                 font=("Segoe UI", 10, "bold")).pack(anchor=tk.W)

        self._entry_listbox = tk.Listbox(
            list_frame, bg=self._bg_medium, fg=self._fg_light,
            selectbackground="#3d5a80", selectforeground="white",
            font=("Consolas", 9), activestyle='none'
        )
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self._entry_listbox.yview)
        self._entry_listbox.configure(yscrollcommand=scrollbar.set)
        self._entry_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, pady=(5, 0))
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=(5, 0))
        self._entry_listbox.bind('<<ListboxSelect>>', self._on_entry_select)

        # Main content area - split for HUD and Response
        content_frame = tk.Frame(self, bg=self._bg_dark)
        content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        # HUD section
        hud_frame = tk.LabelFrame(content_frame, text="HUD Sent", bg=self._bg_dark, fg=self._fg_light)
        hud_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 5))

        self._hud_text = tk.Text(
            hud_frame, wrap=tk.NONE, bg=self._bg_medium, fg=self._fg_light,
            insertbackground=self._fg_light, font=("Consolas", 9)
        )
        hud_scroll_y = ttk.Scrollbar(hud_frame, orient=tk.VERTICAL, command=self._hud_text.yview)
        hud_scroll_x = ttk.Scrollbar(hud_frame, orient=tk.HORIZONTAL, command=self._hud_text.xview)
        self._hud_text.configure(yscrollcommand=hud_scroll_y.set, xscrollcommand=hud_scroll_x.set)

        hud_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        hud_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self._hud_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Response section
        resp_frame = tk.LabelFrame(content_frame, text="Response", bg=self._bg_dark, fg=self._fg_light)
        resp_frame.pack(fill=tk.BOTH, expand=True, pady=(5, 0))

        self._resp_text = tk.Text(
            resp_frame, wrap=tk.NONE, bg=self._bg_medium, fg=self._fg_light,
            insertbackground=self._fg_light, font=("Consolas", 9)
        )
        resp_scroll_y = ttk.Scrollbar(resp_frame, orient=tk.VERTICAL, command=self._resp_text.yview)
        resp_scroll_x = ttk.Scrollbar(resp_frame, orient=tk.HORIZONTAL, command=self._resp_text.xview)
        self._resp_text.configure(yscrollcommand=resp_scroll_y.set, xscrollcommand=resp_scroll_x.set)

        resp_scroll_y.pack(side=tk.RIGHT, fill=tk.Y)
        resp_scroll_x.pack(side=tk.BOTTOM, fill=tk.X)
        self._resp_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def _load_history(self):
        """Load HUD history from heartbeat service."""
        self._history = self._heartbeat.get_hud_history(self._agent.id)
        self._entry_listbox.delete(0, tk.END)

        for i, entry in enumerate(self._history):
            timestamp = entry.get('timestamp', 'Unknown')
            # Parse and format timestamp
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(timestamp)
                display = dt.strftime("%H:%M:%S")
            except (ValueError, TypeError):
                display = timestamp[:8] if timestamp else ""

            tokens = entry.get('tokens', 0)
            error = entry.get('error')
            status = "✗" if error else "✓"
            self._entry_listbox.insert(tk.END, f"{status} {display} ({tokens}t)")

        if self._history:
            # Select last entry
            self._current_index = len(self._history) - 1
            self._entry_listbox.selection_set(self._current_index)
            self._entry_listbox.see(self._current_index)
            self._show_entry(self._current_index)
        else:
            self._current_index = -1
            self._nav_label.config(text="No history")
            self._hud_text.delete("1.0", tk.END)
            self._resp_text.delete("1.0", tk.END)

    def _on_entry_select(self, event):
        """Handle entry selection from listbox."""
        selection = self._entry_listbox.curselection()
        if selection:
            self._current_index = selection[0]
            self._show_entry(self._current_index)

    def _show_entry(self, index: int):
        """Display a specific history entry."""
        if index < 0 or index >= len(self._history):
            return

        entry = self._history[index]
        timestamp = entry.get('timestamp', 'Unknown')
        tokens = entry.get('tokens', 0)

        # Update navigation label
        self._nav_label.config(text=f"Entry {index + 1} of {len(self._history)} | {timestamp} | {tokens} tokens")

        # Show HUD
        self._hud_text.delete("1.0", tk.END)
        hud = entry.get('hud', '')
        # Try to pretty-print JSON
        try:
            import json
            hud_obj = json.loads(hud)
            hud = json.dumps(hud_obj, indent=2)
        except (json.JSONDecodeError, TypeError):
            pass  # Use original text if not valid JSON
        self._hud_text.insert("1.0", hud)

        # Show response or error
        self._resp_text.delete("1.0", tk.END)
        error = entry.get('error')
        if error:
            self._resp_text.insert("1.0", f"ERROR: {error}")
        else:
            response = entry.get('response', '')
            # Try to pretty-print JSON
            try:
                import json
                resp_obj = json.loads(response)
                response = json.dumps(resp_obj, indent=2)
            except (json.JSONDecodeError, TypeError):
                pass  # Use original text if not valid JSON
            self._resp_text.insert("1.0", response)

    def _prev_entry(self):
        """Show previous history entry."""
        if self._current_index > 0:
            self._current_index -= 1
            self._entry_listbox.selection_clear(0, tk.END)
            self._entry_listbox.selection_set(self._current_index)
            self._entry_listbox.see(self._current_index)
            self._show_entry(self._current_index)

    def _next_entry(self):
        """Show next history entry."""
        if self._current_index < len(self._history) - 1:
            self._current_index += 1
            self._entry_listbox.selection_clear(0, tk.END)
            self._entry_listbox.selection_set(self._current_index)
            self._entry_listbox.see(self._current_index)
            self._show_entry(self._current_index)

    def _clear_history(self):
        """Clear history for this agent."""
        if messagebox.askyesno("Clear History", f"Clear all HUD history for {self._agent.name}?", parent=self):
            self._heartbeat.clear_hud_history(self._agent.id)
            self._load_history()
