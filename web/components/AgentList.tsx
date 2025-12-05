'use client';

import { Agent } from '@/lib/api';

interface AgentListProps {
  agents: Agent[];
  selectedId: number | null;
  onSelect: (agent: Agent) => void;
  onCreate: () => void;
  onDelete: (id: number) => void;
}

const STATUS_ICONS: Record<string, { icon: string; color: string }> = {
  idle: { icon: '●', color: 'text-green-400' },
  thinking: { icon: '◐', color: 'text-orange-400' },
  typing: { icon: '⌨', color: 'text-blue-400' },
  sending: { icon: '↑', color: 'text-purple-400' },
  sleeping: { icon: '💤', color: 'text-gray-400' },
};

export default function AgentList({ agents, selectedId, onSelect, onCreate, onDelete }: AgentListProps) {
  return (
    <div className="flex flex-col h-full bg-gray-800 rounded-lg">
      <h2 className="text-lg font-semibold p-4 border-b border-gray-700">Agents</h2>

      <div className="flex-1 overflow-y-auto p-2">
        {agents.length === 0 ? (
          <p className="text-gray-500 text-center py-4">No agents yet</p>
        ) : (
          agents.map((agent) => {
            const status = STATUS_ICONS[agent.status] || STATUS_ICONS.idle;
            const isSelected = selectedId === agent.id;

            return (
              <button
                key={agent.id}
                onClick={() => onSelect(agent)}
                className={`w-full text-left p-3 rounded-lg mb-1 transition-colors ${
                  isSelected
                    ? 'bg-blue-600/30 border border-blue-500/50'
                    : 'hover:bg-gray-700/50'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`${status.color} ${agent.status === 'thinking' ? 'status-thinking' : ''}`}>
                    {status.icon}
                  </span>
                  <span className="flex-1 truncate">
                    {agent.name || 'Unnamed'}
                    <span className="text-gray-500 text-sm"> (#{agent.id})</span>
                  </span>
                </div>
              </button>
            );
          })
        )}
      </div>

      <div className="p-2 border-t border-gray-700 flex gap-2">
        <button
          onClick={onCreate}
          className="flex-1 bg-blue-600 hover:bg-blue-700 text-white py-2 px-4 rounded-lg transition-colors"
        >
          + New
        </button>
        <button
          onClick={() => selectedId && onDelete(selectedId)}
          disabled={!selectedId}
          className="flex-1 bg-gray-600 hover:bg-gray-500 disabled:opacity-50 disabled:cursor-not-allowed text-white py-2 px-4 rounded-lg transition-colors"
        >
          Delete
        </button>
      </div>
    </div>
  );
}
