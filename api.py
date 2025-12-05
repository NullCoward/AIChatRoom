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
WEB_UI_PATH = pathlib.Path(__file__).parent / "web" / "out"

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
                <p class="warning">⚠ Web UI not built. Run: <code>cd web && npm run build</code></p>
                <h2>API Endpoints</h2>
                <ul>
                    <li><code>GET /api/agents</code> - List all agents</li>
                    <li><code>POST /api/agents</code> - Create agent</li>
                    <li><code>GET /api/agents/{id}/room/messages</code> - Get agent room messages</li>
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
    sender_id: Optional[int] = None
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
    pull_forward: float = 0.0


class PullForwardRequest(BaseModel):
    seconds: float


class ApiKeyRequest(BaseModel):
    api_key: str


class AddMemberRequest(BaseModel):
    member_id: int

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

@app.get("/api/agents/{agent_id}/room/messages", response_model=List[MessageResponse])
async def get_agent_room_messages(agent_id: int, since: Optional[int] = None):
    """Get messages for an agent's room, optionally since a sequence number."""
    if since is not None:
        messages = db.get_messages_for_room_since(agent_id, since)
    else:
        messages = db.get_messages_for_room(agent_id)

    return [
        MessageResponse(
            id=m.id,
            room_id=m.room_id,
            sender_id=m.sender_id,
            sender_name=m.sender_name,
            content=m.content,
            timestamp=m.timestamp.isoformat() if m.timestamp else "",
            sequence_number=m.sequence_number,
            message_type=m.message_type,
            reply_to_id=m.reply_to_id
        )
        for m in messages
    ]


@app.post("/api/agents/{agent_id}/room/messages", response_model=MessageResponse)
async def send_agent_room_message(agent_id: int, message_data: MessageCreate):
    """Send a message to an agent's room."""
    # Determine sender_id from sender_name
    sender_id = None
    if message_data.sender_name in ["Architect", "The Architect"]:
        architect = db.get_architect()
        sender_id = architect.id if architect else None
    else:
        # Try to parse as agent ID
        try:
            sender_id = int(message_data.sender_name)
        except ValueError:
            # Not a numeric ID, leave as None
            pass
    
    room_service.send_message(
        agent_id,
        message_data.sender_name,
        message_data.content,
        reply_to_id=message_data.reply_to_id,
        sender_id=sender_id
    )

    # Get the latest message
    messages = db.get_messages_for_room(agent_id)
    if messages:
        m = messages[-1]
        return MessageResponse(
            id=m.id,
            room_id=m.room_id,
            sender_id=m.sender_id,
            sender_name=m.sender_name,
            content=m.content,
            timestamp=m.timestamp.isoformat() if m.timestamp else "",
            sequence_number=m.sequence_number,
            message_type=m.message_type,
            reply_to_id=m.reply_to_id
        )
    raise HTTPException(status_code=500, detail="Failed to send message")


@app.delete("/api/agents/{agent_id}/room/messages")
async def clear_agent_room_messages(agent_id: int):
    """Clear all messages in an agent's room."""
    room_service.clear_room_messages(agent_id)
    return {"status": "cleared", "agent_id": agent_id}


# ============ Room Member Endpoints ============

@app.get("/api/agents/{agent_id}/room/members", response_model=List[RoomMemberResponse])
async def get_agent_room_members(agent_id: int):
    """Get all members of an agent's room."""
    agents = room_service.get_agents_in_room(agent_id)
    return [
        RoomMemberResponse(
            agent_id=a.id,
            agent_name=a.name,
            status=a.status,
            is_owner=(a.id == agent_id)
        )
        for a in agents
    ]


@app.post("/api/agents/{agent_id}/room/members")
async def add_agent_room_member(agent_id: int, request: AddMemberRequest):
    """Add a member to an agent's room."""
    member = db.get_agent(request.member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    room_service.join_room(member, agent_id)
    return {"status": "joined", "member_id": request.member_id, "room_id": agent_id}


@app.delete("/api/agents/{agent_id}/room/members/{member_id}")
async def remove_agent_room_member(agent_id: int, member_id: int):
    """Remove an agent from a room."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    room_service.leave_room(member_id, agent_id)
    return {"status": "left", "agent_id": member_id, "room_id": agent_id}


# ============ Heartbeat Endpoints ============

@app.get("/api/heartbeat/status", response_model=HeartbeatStatus)
async def get_heartbeat_status():
    """Get heartbeat service status."""
    return HeartbeatStatus(
        running=heartbeat_service.is_running if heartbeat_service else False,
        interval=heartbeat_service.get_interval() if heartbeat_service else 5.0,
        pull_forward=heartbeat_service.get_pull_forward() if heartbeat_service else 0.0
    )


@app.post("/api/heartbeat/pull-forward")
async def set_pull_forward(request: PullForwardRequest):
    """Set the heartbeat pull-forward window in seconds.

    When processing a heartbeat, also process any agents whose heartbeats
    are scheduled within this many seconds into the future.
    Set to 0 to disable pull-forward bundling.
    """
    heartbeat_service.set_pull_forward(request.seconds)
    return {
        "status": "updated",
        "pull_forward": heartbeat_service.get_pull_forward()
    }


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
    from models import SelfConcept
    return SelfConcept.from_json(agent.self_concept_json).to_dict()


@app.put("/api/agents/{agent_id}/knowledge")
async def update_agent_knowledge(agent_id: int, data: dict):
    """Update an agent's self-concept."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    import json
    agent.self_concept_json = json.dumps(data)
    db.save_agent(agent)
    return {"status": "updated", "agent_id": agent_id}


@app.delete("/api/agents/{agent_id}/knowledge")
async def clear_agent_knowledge(agent_id: int):
    """Clear an agent's entire knowledge bank."""
    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    agent.self_concept_json = "{}"
    db.save_agent(agent)
    logger.info(f"Cleared knowledge bank for agent {agent_id} ({agent.name})")
    return {"status": "cleared", "agent_id": agent_id}


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


@app.get("/api/prompt-blocks")
async def get_prompt_blocks():
    """Get the main prompt text blocks from config."""
    import config
    return {
        "system_directives": config.SYSTEM_DIRECTIVES,
        "persona_instructions": config.PERSONA_INSTRUCTIONS,
        "bot_instructions": config.BOT_INSTRUCTIONS,
        "batch_instructions": config.BATCH_INSTRUCTIONS
    }


@app.put("/api/prompt-blocks")
async def save_prompt_blocks(data: dict):
    """Save prompt blocks to an override file."""
    import json
    import os
    
    override_file = os.path.join(os.path.dirname(__file__), "prompt_overrides.json")
    
    # Load existing overrides
    overrides = {}
    if os.path.exists(override_file):
        with open(override_file, 'r', encoding='utf-8') as f:
            overrides = json.load(f)
    
    # Update with new values
    for key in ["system_directives", "persona_instructions", "bot_instructions", "batch_instructions"]:
        if key in data:
            overrides[key] = data[key]
    
    # Save
    with open(override_file, 'w', encoding='utf-8') as f:
        json.dump(overrides, f, indent=2)
    
    # Reload config module to pick up changes
    import importlib
    importlib.reload(config)
    
    return {"status": "saved"}


# ============ HUD OS Preview Endpoints ============

@app.get("/api/hud/preview/{agent_id}")
async def get_hud_preview(agent_id: int):
    """Get a preview HUD for an agent in both JSON and TOON formats."""
    from services.hud_service import HUDService
    from services.toon_service import serialize_hud, HUDFormat
    from models import SelfConcept
    import json

    agent = db.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    hud_service = HUDService()

    # Get agent's rooms and build room data
    memberships = db.get_agent_memberships(agent_id)
    room_data = []
    for mem in memberships:
        # Get the agent that IS this room
        room_agent = db.get_agent(mem.room_id)
        if room_agent:
            messages = db.get_messages_for_room(mem.room_id)[-10:]
            members = db.get_room_members(mem.room_id)
            member_names = [db.get_agent(m.agent_id).name for m in members if db.get_agent(m.agent_id)]
            # Create a minimal room dict for this agent
            room_dict = {
                "id": room_agent.id,
                "name": f"{room_agent.id}" if not room_agent.is_architect else "The Architect"
            }
            room_data.append({
                "room": room_dict,
                "membership": mem,
                "messages": messages,
                "members": member_names,
                "word_budget": 500
            })

    # Build HUD structure (without serialization)
    self_concept = SelfConcept.from_json(agent.self_concept_json)

    # Calculate free tokens (simplified)
    from datetime import datetime
    base_tokens = hud_service.estimate_base_hud_tokens(agent)
    free_tokens = max(0, agent.token_budget - base_tokens)
    current_time = datetime.utcnow().isoformat() + "Z"

    # Build the complete HUD structure
    hud_struct = {
        "system": {
            "directives": hud_service.build_system_directives(),
            "memory": {
                "total": agent.token_budget,
                "free": free_tokens
            }
        },
        "meta": {
            "current_time": current_time,
            "instructions": hud_service.build_meta_instructions(agent.agent_type),
            "available_actions": hud_service.build_available_actions(agent.agent_type, agent.can_create_agents),
            "response_format": "JSON object with 'actions' array"
        },
        "agents": [{
            "id": agent.id,
            "name": agent.name,
            "model": agent.model,
            "seed" if agent.agent_type == "persona" else "role": agent.background_prompt,
            "knowledge": self_concept.to_dict(),
            "recent_actions": hud_service.get_recent_actions(agent_id)
        }],
        "agent_rooms": []
    }

    # Add agent_rooms data
    for rd in room_data:
        room = rd["room"]
        hud_struct["agent_rooms"].append({
            "agent_id": room["id"],
            "members": rd["members"],
            "messages": [
                {
                    "sender": m.sender_name,
                    "content": m.content[:200] + "..." if len(m.content) > 200 else m.content,
                    "timestamp": m.timestamp.isoformat() if hasattr(m.timestamp, 'isoformat') else str(m.timestamp)
                }
                for m in rd["messages"][-5:]
            ]
        })

    # Generate JSON representation
    json_str = json.dumps(hud_struct, indent=2, default=str)

    # Generate TOON representation
    toon_str = serialize_hud(hud_struct, format=HUDFormat.TOON, record_telemetry=False)

    # Calculate token estimates
    json_tokens = len(json_str) // 4 + 1
    toon_tokens = len(toon_str) // 4 + 1

    return {
        "agent_id": agent_id,
        "agent_name": agent.name,
        "structure": hud_struct,
        "json": json_str,
        "toon": toon_str,
        "stats": {
            "json_chars": len(json_str),
            "toon_chars": len(toon_str),
            "json_tokens": json_tokens,
            "toon_tokens": toon_tokens,
            "savings_chars": len(json_str) - len(toon_str),
            "savings_tokens": json_tokens - toon_tokens,
            "savings_pct": round((1 - len(toon_str) / len(json_str)) * 100, 1) if len(json_str) > 0 else 0
        }
    }


@app.get("/api/hud/schema")
async def get_hud_schema():
    """Get the HUD schema documentation."""
    return {
        "description": "HUD (Heads-Up Display) is the context window sent to agents each heartbeat",
        "sections": {
            "warnings": {
                "description": "Optional array of warning messages (budget warnings, truncation notices)",
                "type": "array",
                "example": ["Knowledge store exceeds budget by 500 tokens"]
            },
            "system": {
                "description": "Core system directives and memory management",
                "children": {
                    "directives": "Core behavioral rules for the agent",
                    "memory": {
                        "description": "RAM-like memory budget system",
                        "children": {
                            "total": "Total token budget for agent",
                            "base_hud": "Fixed cost of system/meta sections",
                            "allocatable": "Tokens available for knowledge/rooms",
                            "allocations": "Percentage allocation per monitor"
                        }
                    }
                }
            },
            "self": {
                "description": "Agent's identity and persistent memory",
                "children": {
                    "identity": "Agent's name, ID, model, background",
                    "knowledge": "Agent's self-managed knowledge store (flexible JSON)",
                    "recent_actions": "History of agent's recent actions"
                }
            },
            "meta": {
                "description": "Instructions and available actions",
                "children": {
                    "instructions": "Behavioral guidelines from prompts.json",
                    "available_actions": "List of actions agent can take",
                    "response_format": "Expected response structure"
                }
            },
            "rooms": {
                "description": "Room messages and membership data",
                "children": {
                    "{room_id}": {
                        "name": "Room name",
                        "members": "List of agents in room",
                        "messages": "Recent messages",
                        "stats": "Message count, truncation info"
                    }
                }
            }
        },
        "formats": {
            "json": "Standard JSON with indentation (default)",
            "compact_json": "JSON with abbreviated keys",
            "toon": "Token-Oriented Object Notation - declares fields once, uses positional values"
        }
    }


# Setup static file serving AFTER all API routes are defined
# This ensures API routes take precedence over the catch-all
setup_static_files()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
