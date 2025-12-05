'use client';

import { useState, useEffect, useCallback } from 'react';
import * as api from '@/lib/api';
import AgentList from '@/components/AgentList';
import ChatRoom from '@/components/ChatRoom';
import AgentSettings from '@/components/AgentSettings';
import RoomMembers from '@/components/RoomMembers';
import SettingsModal from '@/components/SettingsModal';
import HUDHistoryModal from '@/components/HUDHistoryModal';
import KnowledgeModal from '@/components/KnowledgeModal';
import HUDOSNavigator from '@/components/HUDOSNavigator';
import PromptsModal from '@/components/PromptsModal';

export default function Home() {
  // Core state
  const [agents, setAgents] = useState<api.Agent[]>([]);
  const [selectedAgent, setSelectedAgent] = useState<api.Agent | null>(null);
  const [messages, setMessages] = useState<api.Message[]>([]);
  const [roomMembers, setRoomMembers] = useState<api.RoomMember[]>([]);
  const [models, setModels] = useState<string[]>([]);
  const [apiStatus, setApiStatus] = useState<api.ApiStatus | undefined>();
  const [heartbeatRunning, setHeartbeatRunning] = useState(false);

  // UI state
  const [settingsExpanded, setSettingsExpanded] = useState(true);
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [hudHistoryModalOpen, setHudHistoryModalOpen] = useState(false);
  const [knowledgeModalOpen, setKnowledgeModalOpen] = useState(false);
  const [hudOSNavigatorOpen, setHudOSNavigatorOpen] = useState(false);
  const [promptsModalOpen, setPromptsModalOpen] = useState(false);

  // Fetch initial data
  useEffect(() => {
    fetchAgents();
    fetchApiStatus();
    fetchHeartbeatStatus();
    fetchModels();
  }, []);

  // Poll for updates when heartbeat is running
  useEffect(() => {
    if (!heartbeatRunning) return;

    const interval = setInterval(() => {
      fetchAgents();
      if (selectedAgent) {
        fetchMessages(selectedAgent.id);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [heartbeatRunning, selectedAgent]);

  // Fetch messages when selected agent changes
  useEffect(() => {
    if (selectedAgent) {
      fetchMessages(selectedAgent.id);
      fetchRoomMembers(selectedAgent.id);
    } else {
      setMessages([]);
      setRoomMembers([]);
    }
  }, [selectedAgent?.id]);

  // Data fetching functions
  const fetchAgents = async () => {
    try {
      const data = await api.getAgents();
      setAgents(data);
      // Update selected agent if it exists in the new data
      if (selectedAgent) {
        const updated = data.find(a => a.id === selectedAgent.id);
        if (updated) {
          setSelectedAgent(updated);
        }
      }
    } catch (err) {
      console.error('Failed to fetch agents:', err);
    }
  };

  const fetchMessages = async (roomId: number) => {
    try {
      const data = await api.getRoomMessages(roomId);
      setMessages(data);
    } catch (err) {
      console.error('Failed to fetch messages:', err);
    }
  };

  const fetchRoomMembers = async (roomId: number) => {
    try {
      const data = await api.getRoomMembers(roomId);
      setRoomMembers(data);
    } catch (err) {
      console.error('Failed to fetch room members:', err);
    }
  };

  const fetchApiStatus = async () => {
    try {
      const data = await api.getApiStatus();
      setApiStatus(data);
    } catch (err) {
      console.error('Failed to fetch API status:', err);
    }
  };

  const fetchHeartbeatStatus = async () => {
    try {
      const data = await api.getHeartbeatStatus();
      setHeartbeatRunning(data.running);
    } catch (err) {
      console.error('Failed to fetch heartbeat status:', err);
    }
  };

  const fetchModels = async () => {
    try {
      const data = await api.getModels();
      setModels(data);
    } catch (err) {
      console.error('Failed to fetch models:', err);
    }
  };

  // Action handlers
  const handleSelectAgent = (agent: api.Agent) => {
    setSelectedAgent(agent);
  };

  const handleCreateAgent = async () => {
    try {
      const newAgent = await api.createAgent({
        name: `Agent ${agents.length + 1}`,
        model: models[0] || 'gpt-4o-mini',
      });
      await fetchAgents();
      setSelectedAgent(newAgent);
    } catch (err) {
      console.error('Failed to create agent:', err);
      alert('Failed to create agent');
    }
  };

  const handleDeleteAgent = async (id: number) => {
    if (!confirm('Are you sure you want to delete this agent?')) return;
    try {
      await api.deleteAgent(id);
      await fetchAgents();
      if (selectedAgent?.id === id) {
        setSelectedAgent(null);
      }
    } catch (err) {
      console.error('Failed to delete agent:', err);
      alert('Failed to delete agent');
    }
  };

  const handleSaveAgent = async (id: number, data: Partial<api.AgentCreate>) => {
    try {
      await api.updateAgent(id, data);
      await fetchAgents();
    } catch (err) {
      console.error('Failed to save agent:', err);
      alert('Failed to save agent');
    }
  };

  const handleSendMessage = async (content: string) => {
    if (!selectedAgent) return;
    try {
      await api.sendMessage(selectedAgent.id, content, 'Architect');
      await fetchMessages(selectedAgent.id);
    } catch (err) {
      console.error('Failed to send message:', err);
    }
  };

  const handleClearMessages = async () => {
    if (!selectedAgent) return;
    if (!confirm('Clear all messages in this room?')) return;
    try {
      await api.clearRoomMessages(selectedAgent.id);
      setMessages([]);
    } catch (err) {
      console.error('Failed to clear messages:', err);
    }
  };

  const handleToggleHeartbeat = async () => {
    try {
      if (heartbeatRunning) {
        await api.stopHeartbeat();
      } else {
        await api.startHeartbeat();
      }
      setHeartbeatRunning(!heartbeatRunning);
    } catch (err) {
      console.error('Failed to toggle heartbeat:', err);
    }
  };

  const handleAddRoomMember = async (agentId: number) => {
    if (!selectedAgent) return;
    try {
      await api.addRoomMember(selectedAgent.id, agentId);
      await fetchRoomMembers(selectedAgent.id);
    } catch (err) {
      console.error('Failed to add room member:', err);
    }
  };

  const handleRemoveRoomMember = async (agentId: number) => {
    if (!selectedAgent) return;
    try {
      await api.removeRoomMember(selectedAgent.id, agentId);
      await fetchRoomMembers(selectedAgent.id);
    } catch (err) {
      console.error('Failed to remove room member:', err);
    }
  };

  const handleApiKeySet = () => {
    fetchApiStatus();
    fetchModels();
  };

  return (
    <div className="h-screen flex flex-col">
      {/* Header */}
      <header className="bg-gray-800 border-b border-gray-700 px-4 py-3 flex items-center justify-between flex-shrink-0">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold">AI Chat Room</h1>
          {/* Status indicators */}
          <div className="flex items-center gap-2 text-sm">
            <span className={`flex items-center gap-1 ${apiStatus?.connected ? 'text-green-400' : 'text-red-400'}`}>
              <span className="w-2 h-2 rounded-full bg-current" />
              {apiStatus?.connected ? 'Connected' : 'Disconnected'}
            </span>
            <span className={`flex items-center gap-1 ${heartbeatRunning ? 'text-green-400' : 'text-gray-400'}`}>
              <span className="animate-pulse">{heartbeatRunning ? '❤️' : '💤'}</span>
              {heartbeatRunning ? 'Running' : 'Stopped'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* HUD OS Navigator button */}
          <button
            onClick={() => setHudOSNavigatorOpen(true)}
            className="p-2 rounded hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
            title="HUD OS Navigator"
            disabled={!selectedAgent}
          >
            💻
          </button>
          {/* Prompts button */}
          <button
            onClick={() => setPromptsModalOpen(true)}
            className="p-2 rounded hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
            title="Prompt Settings"
          >
            📝
          </button>
          {/* Settings button */}
          <button
            onClick={() => setSettingsModalOpen(true)}
            className="p-2 rounded hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
            title="Settings"
          >
            ⚙️
          </button>
        </div>
      </header>

      {/* Main Content */}
      <main className="flex-1 flex min-h-0 p-4 gap-4">
        {/* Left Panel: Agent List + Room Members */}
        <div className="w-64 flex-shrink-0 flex flex-col gap-4">
          <div className="flex-1 min-h-0">
            <AgentList
              agents={agents}
              selectedId={selectedAgent?.id ?? null}
              onSelect={handleSelectAgent}
              onCreate={handleCreateAgent}
              onDelete={handleDeleteAgent}
            />
          </div>
          <div className="h-48 flex-shrink-0">
            <RoomMembers
              roomId={selectedAgent?.id ?? null}
              members={roomMembers}
              availableAgents={agents}
              onAddMember={handleAddRoomMember}
              onRemoveMember={handleRemoveRoomMember}
            />
          </div>
        </div>

        {/* Center: Chat */}
        <div className="flex-1 min-h-0">
          <ChatRoom
            roomId={selectedAgent?.id ?? null}
            messages={messages}
            agents={agents}
            heartbeatRunning={heartbeatRunning}
            onSendMessage={handleSendMessage}
            onClearMessages={handleClearMessages}
            onToggleHeartbeat={handleToggleHeartbeat}
          />
        </div>

        {/* Right Panel: Agent Settings */}
        <div className={`flex-shrink-0 transition-all duration-200 ${settingsExpanded ? 'w-80' : 'w-10'}`}>
          <AgentSettings
            agent={selectedAgent}
            models={models}
            onSave={handleSaveAgent}
            expanded={settingsExpanded}
            onToggle={() => setSettingsExpanded(!settingsExpanded)}
            onOpenHUDHistory={() => setHudHistoryModalOpen(true)}
            onOpenKnowledge={() => setKnowledgeModalOpen(true)}
          />
        </div>
      </main>

      {/* Modals */}
      <SettingsModal
        isOpen={settingsModalOpen}
        onClose={() => setSettingsModalOpen(false)}
        apiStatus={apiStatus}
        onApiKeySet={handleApiKeySet}
      />

      <HUDHistoryModal
        isOpen={hudHistoryModalOpen}
        onClose={() => setHudHistoryModalOpen(false)}
        agent={selectedAgent}
      />

      <KnowledgeModal
        isOpen={knowledgeModalOpen}
        onClose={() => setKnowledgeModalOpen(false)}
        agent={selectedAgent}
      />

      <HUDOSNavigator
        isOpen={hudOSNavigatorOpen}
        onClose={() => setHudOSNavigatorOpen(false)}
        agent={selectedAgent}
      />
      <PromptsModal
        isOpen={promptsModalOpen}
        onClose={() => setPromptsModalOpen(false)}
      />
    </div>
  );
}
