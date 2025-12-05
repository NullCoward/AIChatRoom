'use client';

import { useState, useEffect } from 'react';
import { Agent, AgentCreate } from '@/lib/api';

interface AgentSettingsProps {
  agent: Agent | null;
  models: string[];
  onSave: (id: number, data: Partial<AgentCreate>) => void;
  expanded: boolean;
  onToggle: () => void;
  onOpenHUDHistory?: () => void;
  onOpenKnowledge?: () => void;
}

const STATUS_DISPLAY: Record<string, { text: string; color: string }> = {
  idle: { text: '● Idle', color: 'text-green-400' },
  thinking: { text: '◐ Waiting...', color: 'text-orange-400' },
  typing: { text: '⌨ Typing...', color: 'text-blue-400' },
  sending: { text: '↑ Sending...', color: 'text-purple-400' },
  sleeping: { text: '💤 Sleeping', color: 'text-gray-400' },
};

export default function AgentSettings({ agent, models, onSave, expanded, onToggle, onOpenHUDHistory, onOpenKnowledge }: AgentSettingsProps) {
  const [formData, setFormData] = useState<Partial<AgentCreate>>({});

  useEffect(() => {
    if (agent) {
      setFormData({
        name: agent.name,
        model: agent.model,
        background_prompt: agent.background_prompt,
        temperature: agent.temperature,
        room_wpm: agent.room_wpm,
        heartbeat_interval: agent.heartbeat_interval,
        can_create_agents: agent.can_create_agents,
      });
    }
  }, [agent]);

  const handleSave = () => {
    if (agent) {
      onSave(agent.id, formData);
    }
  };

  const status = agent ? (STATUS_DISPLAY[agent.status] || STATUS_DISPLAY.idle) : STATUS_DISPLAY.idle;

  // Collapsed state - show vertical bar with toggle
  if (!expanded) {
    return (
      <div className="bg-gray-800 rounded-lg h-full flex flex-col items-center py-3 w-10">
        <button
          onClick={onToggle}
          className="p-2 hover:bg-gray-700 rounded transition-colors text-gray-400 hover:text-white"
          title="Expand Agent Settings"
        >
          ◀
        </button>
        <div className="flex-1 flex items-center justify-center">
          <span className="text-gray-500 text-xs [writing-mode:vertical-lr] rotate-180">
            Agent Settings
          </span>
        </div>
        {agent && (
          <span className={`text-xs ${status.color}`} title={status.text}>●</span>
        )}
      </div>
    );
  }

  return (
    <div className="bg-gray-800 rounded-lg flex flex-col h-full">
      <div className="flex items-center p-3 flex-shrink-0 rounded-t-lg">
        <button
          onClick={onToggle}
          className="p-1 hover:bg-gray-700/50 transition-colors rounded text-gray-400 hover:text-white mr-2"
          title="Collapse"
        >
          ▶
        </button>
        <span className="font-semibold">Agent Settings</span>

        {/* Agent-specific tool buttons */}
        {agent && (
          <div className="flex items-center gap-1 ml-3">
            <button
              onClick={(e) => { e.stopPropagation(); onOpenHUDHistory?.(); }}
              className="p-1.5 rounded hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
              title="HUD History"
            >
              📜
            </button>
            <button
              onClick={(e) => { e.stopPropagation(); onOpenKnowledge?.(); }}
              className="p-1.5 rounded hover:bg-gray-700 transition-colors text-gray-400 hover:text-white"
              title="Knowledge Explorer"
            >
              🧠
            </button>
          </div>
        )}

        {agent && <span className={`ml-auto ${status.color}`}>{status.text}</span>}
      </div>

      <div className="p-4 pt-2 flex-1 flex flex-col min-h-0 overflow-auto">
          {!agent ? (
            <p className="text-gray-500 text-center py-4">Select an agent to edit</p>
          ) : (
            <>
              {/* Row 1: Name + Model + WPM + Speed */}
              <div className="flex gap-3 mb-3 flex-wrap">
                <div className="flex-1 min-w-[150px]">
                  <label className="block text-xs text-gray-400 mb-1">Name</label>
                  <input
                    type="text"
                    value={formData.name || ''}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div className="w-44">
                  <label className="block text-xs text-gray-400 mb-1">Model</label>
                  <select
                    value={formData.model || models[0] || ''}
                    onChange={(e) => setFormData({ ...formData, model: e.target.value })}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500"
                  >
                    {/* Include current model even if not in approved list */}
                    {formData.model && !models.includes(formData.model) && (
                      <option key={formData.model} value={formData.model} className="text-yellow-400">
                        {formData.model} (legacy)
                      </option>
                    )}
                    {models.map((m) => (
                      <option key={m} value={m}>{m}</option>
                    ))}
                  </select>
                </div>
                <div className="w-16">
                  <label className="block text-xs text-gray-400 mb-1">WPM</label>
                  <input
                    type="number"
                    value={formData.room_wpm || 80}
                    onChange={(e) => setFormData({ ...formData, room_wpm: parseInt(e.target.value) })}
                    className="w-full bg-gray-700 border border-gray-600 rounded px-2 py-1.5 text-sm focus:outline-none focus:border-blue-500"
                  />
                </div>
                <div className="w-32">
                  <label className="block text-xs text-gray-400 mb-1">
                    Speed: {(formData.heartbeat_interval || 5).toFixed(1)}s
                  </label>
                  <input
                    type="range"
                    min="1"
                    max="10"
                    step="0.5"
                    value={formData.heartbeat_interval || 5}
                    onChange={(e) => setFormData({ ...formData, heartbeat_interval: parseFloat(e.target.value) })}
                    className="w-full mt-1"
                  />
                </div>
              </div>

              {/* Row 2: Background label + Permissions + Save button */}
              <div className="flex items-center gap-4 mb-2">
                <label className="text-xs text-gray-400">Background</label>
                <label className="flex items-center gap-1.5 cursor-pointer ml-auto">
                  <input
                    type="checkbox"
                    checked={formData.can_create_agents || false}
                    onChange={(e) => setFormData({ ...formData, can_create_agents: e.target.checked })}
                    className="w-3.5 h-3.5 rounded bg-gray-700 border-gray-600"
                  />
                  <span className="text-xs text-gray-400">Can create agents</span>
                </label>
                <button
                  onClick={handleSave}
                  className="bg-blue-600 hover:bg-blue-700 text-white py-1 px-3 rounded text-sm transition-colors"
                >
                  Save
                </button>
              </div>

              {/* Background textarea - fills remaining space */}
              <textarea
                value={formData.background_prompt || ''}
                onChange={(e) => setFormData({ ...formData, background_prompt: e.target.value })}
                className="flex-1 w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500 resize-none min-h-[60px]"
                placeholder="Agent background/personality..."
              />
            </>
          )}
        </div>
    </div>
  );
}
