'use client';

import { useState } from 'react';
import { Agent, RoomMember } from '@/lib/api';

interface RoomMembersProps {
  roomId: number | null;
  members: RoomMember[];
  availableAgents: Agent[];
  onAddMember: (agentId: number) => void;
  onRemoveMember: (agentId: number) => void;
}

const STATUS_COLORS: Record<string, string> = {
  idle: 'text-green-400',
  thinking: 'text-orange-400',
  typing: 'text-blue-400',
  sending: 'text-purple-400',
  sleeping: 'text-gray-400',
};

export default function RoomMembers({
  roomId,
  members,
  availableAgents,
  onAddMember,
  onRemoveMember,
}: RoomMembersProps) {
  const [selectedAgent, setSelectedAgent] = useState<string>('');

  const handleAdd = () => {
    if (selectedAgent) {
      onAddMember(parseInt(selectedAgent));
      setSelectedAgent('');
    }
  };

  // Filter out agents already in the room
  const memberIds = new Set(members.map(m => m.agent_id));
  const addableAgents = availableAgents.filter(a => !memberIds.has(a.id));

  return (
    <div className="bg-gray-800 rounded-lg p-4 h-full flex flex-col">
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-semibold">Room Members</h2>
        <div className="flex gap-2">
          <select
            value={selectedAgent}
            onChange={(e) => setSelectedAgent(e.target.value)}
            className="bg-gray-700 border border-gray-600 rounded-lg px-2 py-1 text-sm focus:outline-none focus:border-blue-500"
          >
            <option value="">Add agent...</option>
            {addableAgents.map((a) => (
              <option key={a.id} value={a.id}>
                {a.id}: {a.name || 'Unnamed'}
              </option>
            ))}
          </select>
          <button
            onClick={handleAdd}
            disabled={!selectedAgent}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white px-3 py-1 rounded-lg text-sm transition-colors"
          >
            +
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {!roomId ? (
          <p className="text-gray-500 text-center">No room selected</p>
        ) : members.length === 0 ? (
          <p className="text-gray-500 text-center">No members in room</p>
        ) : (
          <div className="space-y-1">
            {members
              .sort((a, b) => (a.is_owner ? -1 : b.is_owner ? 1 : a.agent_id - b.agent_id))
              .map((member) => (
                <div
                  key={member.agent_id}
                  className="flex items-center justify-between p-2 rounded-lg hover:bg-gray-700/30"
                >
                  <div className="flex items-center gap-2">
                    <span className={member.is_owner ? 'text-yellow-400' : 'text-blue-400'}>
                      {member.is_owner ? '★' : '  '}
                    </span>
                    <span>
                      {member.agent_name || 'Unnamed'}
                      <span className="text-gray-500 text-sm"> (#{member.agent_id})</span>
                    </span>
                    <span className={`text-sm ${STATUS_COLORS[member.status] || STATUS_COLORS.idle}`}>
                      ● {member.status}
                    </span>
                  </div>
                  {!member.is_owner && (
                    <button
                      onClick={() => onRemoveMember(member.agent_id)}
                      className="text-gray-500 hover:text-red-400 px-2 transition-colors"
                      title="Remove from room"
                    >
                      ×
                    </button>
                  )}
                </div>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
