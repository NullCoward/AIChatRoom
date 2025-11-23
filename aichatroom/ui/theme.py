"""UI theme constants and styling configuration.

Dark mode color scheme and styling for the AI Chat Room application.
"""

# Dark mode colors - softer greyscale
BG_DARK = "#252525"
BG_MEDIUM = "#333333"
BG_LIGHT = "#444444"
FG_LIGHT = "#cccccc"
FG_DIM = "#777777"

# Status colors (stoplight)
STATUS_COLORS = {
    "idle": "#7ee787",       # Bright green - nothing happening
    "thinking": "#ffa657",   # Orange - waiting for AI response
    "typing": "#79c0ff",     # Blue - typing
    "sending": "#d2a8ff",    # Purple - sending
    "responded": "#7ee787"   # Bright green - goes back to idle
}

# Message colors
MESSAGE_COLORS = {
    "system": "#888888",
    "user": "#58a6ff",      # Bright blue
    "agent": "#7ee787",     # Bright green
    "timestamp": "#6e7681",
    "image_link": "#d2a8ff", # Purple
    "typing": "#ffa657",    # Orange
}

# Special colors
OWNER_COLOR = "#ffd700"  # Gold for room owner/admin
MEMBER_COLOR = "#58a6ff"  # Blue for regular members


def configure_ttk_styles(style, bg_dark: str, bg_medium: str, bg_light: str, fg_light: str) -> None:
    """Configure ttk widget styles for dark mode.

    Args:
        style: ttk.Style instance
        bg_dark: Dark background color
        bg_medium: Medium background color
        bg_light: Light background color
        fg_light: Light foreground color
    """
    style.theme_use('clam')

    # Configure base styles
    style.configure(".",
        background=bg_dark,
        foreground=fg_light,
        fieldbackground=bg_medium
    )
    style.configure("TFrame", background=bg_dark)
    style.configure("TLabel", background=bg_dark, foreground=fg_light)
    style.configure("TButton", background=bg_light, foreground=fg_light)
    style.configure("TEntry", fieldbackground=bg_medium, foreground=fg_light)
    style.configure("TLabelframe", background=bg_dark, foreground=fg_light)
    style.configure("TLabelframe.Label", background=bg_dark, foreground=fg_light)
    style.configure("Treeview",
        background=bg_medium,
        foreground=fg_light,
        fieldbackground=bg_medium
    )
    style.configure("TScale", background=bg_dark, troughcolor=bg_medium)
    style.map("TButton", background=[('active', bg_medium)])

    # Combobox styling
    style.configure("TCombobox",
        fieldbackground=bg_medium,
        background=bg_light,
        foreground=fg_light,
        arrowcolor=fg_light
    )
    style.map("TCombobox",
        fieldbackground=[('readonly', bg_medium)],
        selectbackground=[('readonly', bg_light)],
        selectforeground=[('readonly', fg_light)]
    )


def configure_combobox_dropdown(root, bg_medium: str, fg_light: str) -> None:
    """Configure combobox dropdown listbox colors for dark mode.

    This must be called on the root window to style the dropdown popup.

    Args:
        root: Tk root window
        bg_medium: Background color for dropdown
        fg_light: Text color for dropdown
    """
    # Style the combobox dropdown listbox
    root.option_add('*TCombobox*Listbox.background', bg_medium)
    root.option_add('*TCombobox*Listbox.foreground', fg_light)
    root.option_add('*TCombobox*Listbox.selectBackground', '#3d5a80')
    root.option_add('*TCombobox*Listbox.selectForeground', 'white')
