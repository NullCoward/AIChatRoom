"""FastAPI REST API for AI Chat Room.

Exposes the existing Python services as HTTP endpoints for the web UI.
Run with: uvicorn api:app --reload --port 8000
"""

import os
import sys
from datetime import datetime
from typing import List, Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import pathlib

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from services import DatabaseService, OpenAIService, HeartbeatService, RoomService, setup_logging, get_logger
from models import AIAgent, ChatMessage

setup_logging()
logger = get_logger("api")

# Global service instances
db: DatabaseService = None
openai_service: OpenAIService = None
room_service: RoomService = None
heartbeat_service: HeartbeatService = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services on startup, cleanup on shutdown."""
    global db, openai_service, room_service, heartbeat_service

    logger.info("Starting API server...")
    db = DatabaseService()
    openai_service = OpenAIService()
    room_service = RoomService(db)
    heartbeat_service = HeartbeatService(openai_service, db, room_service)

    # Try to load API key from environment or keyring
    api_key = os.environ.get("OPENAI_API_KEY")
    if api_key:
        openai_service.set_api_key(api_key)
        logger.info("API key loaded from environment")
    else:
        try:
            import keyring
            api_key = keyring.get_password("aichatroom", "openai_api_key")
            if api_key:
                openai_service.set_api_key(api_key)
                logger.info("API key loaded from keyring")
        except ImportError:
            pass

    yield

    # Cleanup
    logger.info("Shutting down API server...")
    if heartbeat_service:
        heartbeat_service.cleanup()
    if room_service:
        room_service.cleanup()


app = FastAPI(
    title="AI Chat Room API",
    description="REST API for the AI Chat Room multi-agent chat application",
    version="1.0.0",
    lifespan=lifespan
)

# CORS for local development and Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "https://*.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ Static File Serving ============

# Path to the web UI build output (Next.js static export)
WEB_UI_PATH = pathlib.Path(__file__).parent.parent / "aichatroom-web" / "out"

def setup_static_files():
    """Mount static files if the web UI build exists."""
    if WEB_UI_PATH.exists():
        # Mount static files (CSS, JS, images) under /_next
        next_static = WEB_UI_PATH / "_next"
        if next_static.exists():
            app.mount("/_next", StaticFiles(directory=str(next_static)), name="next_static")

        # Serve index.html for root and any non-API routes (SPA fallback)
        @app.get("/")
        async def serve_root():
            return FileResponse(str(WEB_UI_PATH / "index.html"))

        # Catch-all for client-side routing (must be registered last)
        @app.get("/{full_path:path}")
        async def serve_spa(full_path: str):
            # Don't intercept API routes or docs
            if full_path.startswith("api/") or full_path in ("docs", "redoc", "openapi.json"):
                raise HTTPException(status_code=404)

            # Try to serve the exact file first
            file_path = WEB_UI_PATH / full_path
            if file_path.is_file():
                return FileResponse(str(file_path))

            # Try with index.html for directory paths (Next.js trailingSlash)
            index_path = WEB_UI_PATH / full_path / "index.html"
            if index_path.is_file():
                return FileResponse(str(index_path))

            # Fallback to root index.html for SPA routing
            return FileResponse(str(WEB_UI_PATH / "index.html"))

        logger.info(f"Web UI mounted from {WEB_UI_PATH}")
    else:
        # Fallback: Show API info when no web UI is built
        from fastapi.responses import HTMLResponse

        @app.get("/", response_class=HTMLResponse)
        async def root():
            return """
            <!DOCTYPE html>
            <html>
            <head>
                <title>AI Chat Room API</title>
                <style>
                    body { font-family: system-ui, sans-serif; max-width: 800px; margin: 50px auto; padding: 20px; background: #1a1a2e; color: #eee; }
                    h1 { color: #3b82f6; }
                    a { color: #79c0ff; }
                    code { background: #2d2d44; padding: 2px 6px; border-radius: 4px; }
                    .status { color: #7ee787; }
                    .warning { color: #f0883e; }
                </style>
            </head>
            <body>
                <h1>AI Chat Room API</h1>
                <p class="status">✓ API is running</p>
                <p class="warning">⚠ Web UI not built. Run: <code>cd ../aichatroom-web && npm run build</code></p>
                <h2>API Endpoints</h2>
                <ul>
                    <li><code>GET /api/agents</code> - List all agents</li>
                    <li><code>POST /api/agents</code> - Create agent</li>
                    <li><code>GET /api/rooms/{id}/messages</code> - Get room messages</li>
                    <li><code>GET /api/health</code> - Health check</li>
                </ul>
                <p>📖 <a href="/docs">API Documentation (Swagger UI)</a></p>
            </body>
            </html>
            """
        logger.info(f"Web UI not found at {WEB_UI_PATH} - API-only mode")


# ============ Pydantic Models ============

class AgentCreate(BaseModel):
    name: str = "New Agent"
    model: str = "gpt-5-nano"
    background_prompt: str = "You are a helpful AI assistant."
    temperature: float = 0.7
    room_wpm: int = 80
    heartbeat_interval: float = 5.0
    can_create_agents: bool = False
    token_budget: int = 10000


class AgentUpdate(BaseModel):
    name: Optional[str] = None
    model: Optional[str] = None
    background_prompt: Optional[str] = None
    temperature: Optional[float] = None
    room_wpm: Optional[int] = None
    heartbeat_interval: Optional[float] = None
    can_create_agents: Optional[bool] = None
    token_budget: Optional[int] = None


class AgentResponse(BaseModel):
    id: int
    name: str
    model: str
    background_prompt: str
    temperature: float
    status: str
    room_wpm: int
    heartbeat_interval: float
    can_create_agents: bool
    is_architect: bool
    total_tokens_used: int
    token_budget: int
    created_at: str

    class Config:
        from_attributes = True


class MessageCreate(BaseModel):
    sender_name: str
    content: str
    reply_to_id: Optional[int] = None


class MessageResponse(BaseModel):
    id: int
    room_id: int
    sender_name: str
    content: str
    timestamp: str
    sequence_number: int
    message_type: str
    reply_to_id: Optional[int] = None

    class Config:
        from_attributes = True


class RoomMemberResponse(BaseModel):
    agent_id: int
    agent_name: str
    status: str
    is_owner: bool


class HeartbeatStatus(BaseModel):
    running: bool
    interval: float


class ApiKeyRequest(BaseModel):
    api_key: str


class StatusResponse(BaseModel):
    connected: bool
    models: List[str]
    message: str


# ============ Agent Endpoints ============

@app.get("/api/agents", response_model=List[AgentResponse])
async def get_agents():
    """Get all agents (excluding The Architect)."""
    agents = db.get_all_agents()
    return [
        AgentResponse(
            id=a.id,
            name=a.name,
            model=a.model,
            background_prompt=a.background_prompt,
            temperature=a.temperature,
            status=a.status,
            room_wpm=a.room_wpm,
            heartbeat_interval=a.heartbeat_interval,
            can_create_agents=a.can_create_agents,
            is_architect=a.is_architect,
            total_tokens_used=a.total_tokens_used,
            token_budget=a.token_budget,
            created_at=a.created_at.isoformat() if a.created_at else ""
        )
        for a in agents if not a.is_architect
    ]


@app.get("/api/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(agent_id: int):
    """Get a specific agent by ID."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return AgentResponse(
        id=agent.id,
        name=agent.name,
        model=agent.model,
        background_prompt=agent.background_prompt,
        temperature=agent.temperature,
        status=agent.status,
        room_wpm=agent.room_wpm,
        heartbeat_interval=agent.heartbeat_interval,
        can_create_agents=agent.can_create_agents,
        is_architect=agent.is_architect,
        total_tokens_used=agent.total_tokens_used,
        token_budget=agent.token_budget,
        created_at=agent.created_at.isoformat() if agent.created_at else ""
    )


@app.post("/api/agents", response_model=AgentResponse)
async def create_agent(agent_data: AgentCreate):
    """Create a new agent."""
    agent = AIAgent(
        name=agent_data.name,
        model=agent_data.model,
        background_prompt=agent_data.background_prompt,
        temperature=agent_data.temperature,
        room_wpm=agent_data.room_wpm,
        heartbeat_interval=agent_data.heartbeat_interval,
        can_create_agents=agent_data.can_create_agents,
        token_budget=agent_data.token_budget
    )
    agent_id = db.save_agent(agent)
    agent.id = agent_id

    # Auto-join the agent to their own room
    room_service.join_room(agent, agent_id)

    return AgentResponse(
        id=agent.id,
        name=agent.name,
        model=agent.model,
        background_prompt=agent.background_prompt,
        temperature=agent.temperature,
        status=agent.status,
        room_wpm=agent.room_wpm,
        heartbeat_interval=agent.heartbeat_interval,
        can_create_agents=agent.can_create_agents,
        is_architect=agent.is_architect,
        total_tokens_used=agent.total_tokens_used,
        token_budget=agent.token_budget,
        created_at=agent.created_at.isoformat() if agent.created_at else ""
    )


@app.put("/api/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(agent_id: int, agent_data: AgentUpdate):
    """Update an existing agent."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if agent_data.name is not None:
        agent.name = agent_data.name
    if agent_data.model is not None:
        agent.model = agent_data.model
    if agent_data.background_prompt is not None:
        agent.background_prompt = agent_data.background_prompt
    if agent_data.temperature is not None:
        agent.temperature = agent_data.temperature
    if agent_data.room_wpm is not None:
        agent.room_wpm = agent_data.room_wpm
    if agent_data.heartbeat_interval is not None:
        agent.heartbeat_interval = agent_data.heartbeat_interval
    if agent_data.can_create_agents is not None:
        agent.can_create_agents = agent_data.can_create_agents
    if agent_data.token_budget is not None:
        agent.token_budget = agent_data.token_budget

    db.save_agent(agent)

    return AgentResponse(
        id=agent.id,
        name=agent.name,
        model=agent.model,
        background_prompt=agent.background_prompt,
        temperature=agent.temperature,
        status=agent.status,
        room_wpm=agent.room_wpm,
        heartbeat_interval=agent.heartbeat_interval,
        can_create_agents=agent.can_create_agents,
        is_architect=agent.is_architect,
        total_tokens_used=agent.total_tokens_used,
        token_budget=agent.token_budget,
        created_at=agent.created_at.isoformat() if agent.created_at else ""
    )


@app.delete("/api/agents/{agent_id}")
async def delete_agent(agent_id: int):
    """Delete an agent."""
    if not db.delete_agent(agent_id):
        raise HTTPException(status_code=404, detail="Agent not found")
    return {"status": "deleted", "agent_id": agent_id}


# ============ Message Endpoints ============

@app.get("/api/rooms/{room_id}/messages", response_model=List[MessageResponse])
async def get_room_messages(room_id: int, since: Optional[int] = None):
    """Get messages for a room, optionally since a sequence number."""
    if since is not None:
        messages = db.get_messages_for_room_since(room_id, since)
    else:
        messages = db.get_messages_for_room(room_id)

    return [
        MessageResponse(
            id=m.id,
            room_id=m.room_id,
            sender_name=m.sender_name,
            content=m.content,
            timestamp=m.timestamp.isoformat() if m.timestamp else "",
            sequence_number=m.sequence_number,
            message_type=m.message_type,
            reply_to_id=m.reply_to_id
        )
        for m in messages
    ]


@app.post("/api/rooms/{room_id}/messages", response_model=MessageResponse)
async def send_message(room_id: int, message_data: MessageCreate):
    """Send a message to a room."""
    room_service.send_message(
        room_id,
        message_data.sender_name,
        message_data.content,
        reply_to_id=message_data.reply_to_id
    )

    # Get the latest message
    messages = db.get_messages_for_room(room_id)
    if messages:
        m = messages[-1]
        return MessageResponse(
            id=m.id,
            room_id=m.room_id,
            sender_name=m.sender_name,
            content=m.content,
            timestamp=m.timestamp.isoformat() if m.timestamp else "",
            sequence_number=m.sequence_number,
            message_type=m.message_type,
            reply_to_id=m.reply_to_id
        )
    raise HTTPException(status_code=500, detail="Failed to send message")


@app.delete("/api/rooms/{room_id}/messages")
async def clear_room_messages(room_id: int):
    """Clear all messages in a room."""
    room_service.clear_room_messages(room_id)
    return {"status": "cleared", "room_id": room_id}


# ============ Room Member Endpoints ============

@app.get("/api/rooms/{room_id}/members", response_model=List[RoomMemberResponse])
async def get_room_members(room_id: int):
    """Get all members of a room."""
    agents = room_service.get_agents_in_room(room_id)
    return [
        RoomMemberResponse(
            agent_id=a.id,
            agent_name=a.name,
            status=a.status,
            is_owner=(a.id == room_id)
        )
        for a in agents
    ]


@app.post("/api/rooms/{room_id}/members/{agent_id}")
async def add_room_member(room_id: int, agent_id: int):
    """Add an agent to a room."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    room_service.join_room(agent, room_id)
    return {"status": "joined", "agent_id": agent_id, "room_id": room_id}


@app.delete("/api/rooms/{room_id}/members/{agent_id}")
async def remove_room_member(room_id: int, agent_id: int):
    """Remove an agent from a room."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    room_service.leave_room(agent, room_id)
    return {"status": "left", "agent_id": agent_id, "room_id": room_id}


# ============ Heartbeat Endpoints ============

@app.get("/api/heartbeat/status", response_model=HeartbeatStatus)
async def get_heartbeat_status():
    """Get heartbeat service status."""
    return HeartbeatStatus(
        running=heartbeat_service.is_running if heartbeat_service else False,
        interval=5.0
    )


@app.post("/api/heartbeat/start")
async def start_heartbeat():
    """Start the heartbeat service."""
    if not openai_service.has_api_key:
        raise HTTPException(status_code=400, detail="OpenAI API key not configured")

    heartbeat_service.start()
    return {"status": "started"}


@app.post("/api/heartbeat/stop")
async def stop_heartbeat():
    """Stop the heartbeat service."""
    heartbeat_service.stop()
    return {"status": "stopped"}


# ============ Settings Endpoints ============

@app.get("/api/settings/status", response_model=StatusResponse)
async def get_api_status():
    """Get OpenAI API connection status."""
    if not openai_service.has_api_key:
        return StatusResponse(connected=False, models=[], message="API key not configured")

    success, message = openai_service.test_connection()
    models = openai_service.get_available_models() if success else []

    return StatusResponse(connected=success, models=models, message=message)


@app.post("/api/settings/apikey")
async def set_api_key(request: ApiKeyRequest):
    """Set the OpenAI API key."""
    openai_service.set_api_key(request.api_key)
    success, message = openai_service.test_connection()

    if success:
        # Save to keyring if available
        try:
            import keyring
            keyring.set_password("aichatroom", "openai_api_key", request.api_key)
        except ImportError:
            pass

        return {"status": "connected", "message": message}
    else:
        raise HTTPException(status_code=400, detail=message)


@app.get("/api/settings/models", response_model=List[str])
async def get_available_models():
    """Get list of available OpenAI models."""
    if not openai_service.has_api_key:
        raise HTTPException(status_code=400, detail="API key not configured")
    return openai_service.get_available_models()


# ============ Health Check ============

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "heartbeat_running": heartbeat_service.is_running if heartbeat_service else False,
        "api_connected": openai_service.has_api_key if openai_service else False
    }


# ============ HUD History Endpoints ============

@app.get("/api/agents/{agent_id}/hud-history")
async def get_hud_history(agent_id: int, limit: int = 50):
    """Get HUD interaction history for an agent."""
    if not heartbeat_service:
        return []
    history = heartbeat_service.get_hud_history(agent_id)
    # Return most recent entries, limited
    return history[-limit:] if history else []


@app.delete("/api/agents/{agent_id}/hud-history")
async def clear_hud_history(agent_id: int):
    """Clear HUD history for an agent."""
    if heartbeat_service:
        heartbeat_service.clear_hud_history(agent_id)
    return {"status": "cleared", "agent_id": agent_id}


# ============ Knowledge/Self-Concept Endpoints ============

@app.get("/api/agents/{agent_id}/knowledge")
async def get_agent_knowledge(agent_id: int):
    """Get an agent's self-concept/knowledge tree."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent.self_concept.data if agent.self_concept else {}


@app.put("/api/agents/{agent_id}/knowledge")
async def update_agent_knowledge(agent_id: int, data: dict):
    """Update an agent's self-concept."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    from models import SelfConcept
    agent.self_concept = SelfConcept(data)
    db.save_agent(agent)
    return {"status": "updated", "agent_id": agent_id}


@app.delete("/api/agents/{agent_id}/knowledge")
async def clear_agent_knowledge(agent_id: int):
    """Clear an agent's entire knowledge bank."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    from models import SelfConcept
    agent.self_concept = SelfConcept({})
    agent.self_concept_json = "{}"
    db.save_agent(agent)
    logger.info(f"Cleared knowledge bank for agent {agent_id} ({agent.name})")
    return {"status": "cleared", "agent_id": agent_id}


# ============ TOON Telemetry Endpoints ============

@app.get("/api/telemetry/toon")
async def get_toon_telemetry():
    """Get TOON format telemetry data."""
    from services.toon_service import get_telemetry
    collector = get_telemetry()
    summary = collector.get_summary()
    entries = collector.get_entries()

    return {
        "total_comparisons": summary.get("entries", 0),
        "json_chars": summary.get("total_json_chars", 0),
        "optimized_chars": summary.get("total_toon_chars", 0),
        "char_savings": summary.get("total_char_savings", 0),
        "savings_percentage": summary.get("avg_char_savings_pct", 0),
        "estimated_json_tokens": summary.get("total_json_tokens", 0),
        "estimated_optimized_tokens": summary.get("total_toon_tokens", 0),
        "entries": [
            {
                "timestamp": e.get("timestamp", ""),
                "json_tokens": e.get("json_tokens", 0),
                "optimized_tokens": e.get("toon_tokens", 0),
                "savings": e.get("token_savings", 0)
            }
            for e in entries[-100:]  # Last 100 entries
        ]
    }


# ============ Prompts Endpoints ============

@app.get("/api/prompts")
async def get_prompts():
    """Get the prompts configuration."""
    import prompts
    return prompts.load_prompts()


@app.put("/api/prompts")
async def save_prompts(data: dict):
    """Save the prompts configuration."""
    import prompts
    prompts.save_prompts(data)
    return {"status": "saved"}


# Setup static file serving AFTER all API routes are defined
# This ensures API routes take precedence over the catch-all
setup_static_files()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
