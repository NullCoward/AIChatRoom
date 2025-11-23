#!/usr/bin/env python3
"""AI Chat Room Application.

A multi-agent chat application where AI agents communicate via
OpenAI's Responses API using a heartbeat polling system.

Core Architecture:
- Each agent IS a room (agent.id = room.id)
- Agent 0 is "The Architect" (human user)
- Agents are polled on heartbeat intervals (1-10 seconds)
- HUD (Heads-Up Display) provides context window to each agent
"""

import sys
import os

# Add project root to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui import MainWindow


def main():
    """Main entry point for the application."""
    app = MainWindow()
    app.run()


if __name__ == "__main__":
    main()
