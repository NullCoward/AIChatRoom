#!/usr/bin/env python3
"""
AI Chat Room - Unified Startup Script

This script builds the web UI and starts the bundled server.
Both the web interface and API run on the same port (default: 8000).

Usage:
    python start.py              # Build UI and start server
    python start.py --skip-build # Start server without rebuilding UI
    python start.py --port 3000  # Use custom port
"""

import subprocess
import sys
import os
import argparse
from pathlib import Path

# Paths
SCRIPT_DIR = Path(__file__).parent
WEB_UI_DIR = SCRIPT_DIR / "web"
WEB_UI_OUT = WEB_UI_DIR / "out"


def build_web_ui():
    """Build the Next.js web UI."""
    print("=" * 60)
    print("Building Web UI...")
    print("=" * 60)

    if not WEB_UI_DIR.exists():
        print(f"Error: Web UI directory not found at {WEB_UI_DIR}")
        return False

    # Check for node_modules
    if not (WEB_UI_DIR / "node_modules").exists():
        print("Installing npm dependencies...")
        result = subprocess.run(
            ["npm", "install"],
            cwd=str(WEB_UI_DIR),
            shell=True
        )
        if result.returncode != 0:
            print("Error: npm install failed")
            return False

    # Build the Next.js app
    print("Running npm build...")
    result = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(WEB_UI_DIR),
        shell=True
    )

    if result.returncode != 0:
        print("Error: npm build failed")
        return False

    if WEB_UI_OUT.exists():
        print(f"Web UI built successfully at {WEB_UI_OUT}")
        return True
    else:
        print("Error: Build completed but output directory not found")
        return False


def start_server(port: int, reload: bool = False):
    """Start the FastAPI server."""
    print()
    print("=" * 60)
    print(f"Starting AI Chat Room Server on port {port}...")
    print("=" * 60)

    if WEB_UI_OUT.exists():
        print(f"Web UI: http://localhost:{port}/")
    else:
        print("Web UI: Not available (run without --skip-build to build)")

    print(f"API:    http://localhost:{port}/api/")
    print(f"Docs:   http://localhost:{port}/docs")
    print()
    print("Press Ctrl+C to stop the server")
    print("=" * 60)
    print()

    # Start uvicorn
    cmd = [
        sys.executable, "-m", "uvicorn",
        "api:app",
        "--host", "0.0.0.0",
        "--port", str(port),
    ]

    if reload:
        cmd.append("--reload")

    try:
        subprocess.run(cmd, cwd=str(SCRIPT_DIR))
    except KeyboardInterrupt:
        print("\nServer stopped.")


def main():
    parser = argparse.ArgumentParser(
        description="AI Chat Room - Unified Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python start.py              # Build UI and start server
    python start.py --skip-build # Start without rebuilding (faster)
    python start.py --port 3000  # Use custom port
    python start.py --dev        # Development mode with auto-reload
        """
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Skip building the web UI (use existing build)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to run the server on (default: 8000)"
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Enable auto-reload for development"
    )

    args = parser.parse_args()

    print()
    print("  AI Chat Room - Unified Server")
    print("  ==============================")
    print()

    # Build web UI unless skipped
    if not args.skip_build:
        if not build_web_ui():
            print()
            print("Warning: Web UI build failed. Starting API-only mode.")
            print("You can still access the API at /api/ endpoints.")
            print()
    else:
        if WEB_UI_OUT.exists():
            print("Skipping build - using existing web UI")
        else:
            print("Warning: No existing web UI build found")
            print("The server will start in API-only mode")
        print()

    # Start the server
    start_server(args.port, reload=args.dev)


if __name__ == "__main__":
    main()
