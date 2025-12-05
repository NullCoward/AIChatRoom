/**
 * API client for the AI Chat Room backend.
 */

const API_BASE = '/api';

// ============ Types ============

export interface Agent {
  id: number;
  name: string;
  background_prompt: string;
  model: string;
  temperature: number;
  status: string;
  is_architect: boolean;
  agent_type: string;
  room_wpm: number;
  heartbeat_interval: number;
  can_create_agents: boolean;
  total_tokens_used: number;
  token_budget: number;
  sleep_until: string | null;
  hud_input_format: string;
  hud_output_format: string;
}

export interface AgentCreate {
  name: string;
  background_prompt?: string;
  model?: string;
  temperature?: number;
  room_wpm?: number;
  heartbeat_interval?: number;
  can_create_agents?: boolean;
  in_room_id?: number;
}

export interface Message {
  id: number;
  room_id: number;
  sender_id: number;
  sender_name: string;
  content: string;
  timestamp: string;
  message_type: string;
}

export interface RoomMember {
  agent_id: number;
  room_id: number;
  joined_at: string;
  allocation_percent: number;
  is_owner: boolean;
  agent_name: string;
  status: string;
}

export interface ApiStatus {
  connected: boolean;
  has_key: boolean;
  message?: string;
  models?: string[];
}

export interface HUDHistoryEntry {
  timestamp: string;
  hud: string;
  response: string;
  tokens: number;
  hud_tokens?: number;
  error?: string;
}

// ============ Helper Functions ============

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(error.detail || `HTTP ${response.status}`);
  }

  return response.json();
}

// ============ Agent API ============

export async function getAgents(): Promise<Agent[]> {
  return fetchJson<Agent[]>(`${API_BASE}/agents`);
}

export async function getAgent(id: number): Promise<Agent> {
  return fetchJson<Agent>(`${API_BASE}/agents/${id}`);
}

export async function createAgent(data: AgentCreate): Promise<Agent> {
  return fetchJson<Agent>(`${API_BASE}/agents`, {
    method: 'POST',
    body: JSON.stringify(data),
  });
}

export async function updateAgent(id: number, data: Partial<AgentCreate>): Promise<Agent> {
  return fetchJson<Agent>(`${API_BASE}/agents/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function deleteAgent(id: number): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/agents/${id}`, {
    method: 'DELETE',
  });
}

// ============ Knowledge API ============

export async function getAgentKnowledge(agentId: number): Promise<Record<string, unknown>> {
  return fetchJson<Record<string, unknown>>(`${API_BASE}/agents/${agentId}/knowledge`);
}

export async function updateAgentKnowledge(agentId: number, data: Record<string, unknown>): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/agents/${agentId}/knowledge`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

export async function clearAgentKnowledge(agentId: number): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/agents/${agentId}/knowledge`, {
    method: 'DELETE',
  });
}

// ============ Messages API ============

export async function getRoomMessages(roomId: number): Promise<Message[]> {
  return fetchJson<Message[]>(`${API_BASE}/agents/${roomId}/room/messages`);
}

export async function sendMessage(roomId: number, content: string, senderName?: string): Promise<Message> {
  return fetchJson<Message>(`${API_BASE}/agents/${roomId}/room/messages`, {
    method: 'POST',
    body: JSON.stringify({ content, sender_name: senderName || 'Architect' }),
  });
}

export async function clearRoomMessages(roomId: number): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/agents/${roomId}/room/messages`, {
    method: 'DELETE',
  });
}

// ============ Room Members API ============

export async function getRoomMembers(roomId: number): Promise<RoomMember[]> {
  return fetchJson<RoomMember[]>(`${API_BASE}/agents/${roomId}/room/members`);
}

export async function addRoomMember(roomId: number, agentId: number): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/agents/${roomId}/room/members`, {
    method: 'POST',
    body: JSON.stringify({ member_id: agentId }),
  });
}

export async function removeRoomMember(roomId: number, agentId: number): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/agents/${roomId}/room/members/${agentId}`, {
    method: 'DELETE',
  });
}

// ============ Heartbeat API ============

export async function startHeartbeat(): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/heartbeat/start`, {
    method: 'POST',
  });
}

export async function stopHeartbeat(): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/heartbeat/stop`, {
    method: 'POST',
  });
}

export interface HeartbeatStatus {
  running: boolean;
  interval: number;
  pull_forward: number;
}

export async function getHeartbeatStatus(): Promise<HeartbeatStatus> {
  return fetchJson<HeartbeatStatus>(`${API_BASE}/heartbeat/status`);
}

export async function setPullForward(seconds: number): Promise<void> {
  await fetchJson<{ status: string; pull_forward: number }>(`${API_BASE}/heartbeat/pull-forward`, {
    method: 'POST',
    body: JSON.stringify({ seconds }),
  });
}

// ============ HUD History API ============

export async function getHUDHistory(agentId: number, limit?: number): Promise<HUDHistoryEntry[]> {
  const url = limit
    ? `${API_BASE}/agents/${agentId}/hud-history?limit=${limit}`
    : `${API_BASE}/agents/${agentId}/hud-history`;
  return fetchJson<HUDHistoryEntry[]>(url);
}

export async function clearHUDHistory(agentId: number): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/agents/${agentId}/hud-history`, {
    method: 'DELETE',
  });
}

// ============ Settings API ============

export async function getApiStatus(): Promise<ApiStatus> {
  return fetchJson<ApiStatus>(`${API_BASE}/settings/status`);
}

export async function setApiKey(apiKey: string): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/settings/apikey`, {
    method: 'POST',
    body: JSON.stringify({ api_key: apiKey }),
  });
}

export async function getModels(): Promise<string[]> {
  return fetchJson<string[]>(`${API_BASE}/settings/models`);
}

// ============ Prompts API ============

export async function getPrompts(): Promise<Record<string, unknown>> {
  return fetchJson<Record<string, unknown>>(`${API_BASE}/prompts`);
}

export async function savePrompts(data: Record<string, unknown>): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/prompts`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// ============ Prompt Blocks API ============

export interface PromptBlocks {
  system_directives: string;
  persona_instructions: string;
  bot_instructions: string;
  batch_instructions: string;
}

export async function getPromptBlocks(): Promise<PromptBlocks> {
  return fetchJson<PromptBlocks>(`${API_BASE}/prompt-blocks`);
}

export async function savePromptBlocks(data: Partial<PromptBlocks>): Promise<void> {
  await fetchJson<{ status: string }>(`${API_BASE}/prompt-blocks`, {
    method: 'PUT',
    body: JSON.stringify(data),
  });
}

// ============ HUD Preview API ============

export interface HUDPreviewStats {
  json_chars: number;
  toon_chars: number;
  json_tokens: number;
  toon_tokens: number;
  savings_chars: number;
  savings_tokens: number;
  savings_pct: number;
}

export interface HUDPreview {
  agent_id: number;
  agent_name: string;
  structure: Record<string, unknown>;
  json: string;
  toon: string;
  stats: HUDPreviewStats;
}

export interface HUDSchema {
  description: string;
  sections: Record<string, unknown>;
  formats: Record<string, string>;
}

export async function getHUDPreview(agentId: number): Promise<HUDPreview> {
  return fetchJson<HUDPreview>(`${API_BASE}/hud/preview/${agentId}`);
}

export async function getHUDSchema(): Promise<HUDSchema> {
  return fetchJson<HUDSchema>(`${API_BASE}/hud/schema`);
}
