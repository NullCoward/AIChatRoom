'use client';

import { useState, useEffect, useRef } from 'react';
import { Message, Agent } from '@/lib/api';

interface ChatRoomProps {
  roomId: number | null;
  messages: Message[];
  agents: Agent[];
  heartbeatRunning: boolean;
  onSendMessage: (content: string) => void;
  onClearMessages: () => void;
  onToggleHeartbeat: () => void;
}

export default function ChatRoom({
  roomId,
  messages,
  agents,
  heartbeatRunning,
  onSendMessage,
  onClearMessages,
  onToggleHeartbeat,
}: ChatRoomProps) {
  const [inputValue, setInputValue] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (inputValue.trim()) {
      onSendMessage(inputValue.trim());
      setInputValue('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  // Get sender display name
  const getSenderName = (senderName: string): string => {
    if (senderName === 'The Architect' || senderName === 'User' || senderName === 'System') {
      return senderName;
    }
    // Check if it's an agent ID
    const agentId = parseInt(senderName);
    if (!isNaN(agentId)) {
      const agent = agents.find(a => a.id === agentId);
      return agent ? `${agent.name} (#${agentId})` : `Agent #${agentId}`;
    }
    return senderName;
  };

  // Get message style based on sender
  const getMessageStyle = (senderName: string): string => {
    if (senderName === 'The Architect' || senderName === 'User') {
      return 'chat-message chat-message-user';
    }
    if (senderName === 'System') {
      return 'chat-message chat-message-system';
    }
    return 'chat-message chat-message-agent';
  };

  const formatTime = (timestamp: string): string => {
    try {
      const date = new Date(timestamp);
      return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div className="bg-gray-800 rounded-lg flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-700">
        <h2 className="font-semibold">Chat Room</h2>
        <div className="flex gap-2">
          <button
            onClick={onClearMessages}
            disabled={!roomId}
            className="bg-gray-600 hover:bg-gray-500 disabled:opacity-50 disabled:cursor-not-allowed text-white py-1 px-3 rounded-lg text-sm transition-colors"
          >
            Clear
          </button>
          <button
            onClick={onToggleHeartbeat}
            className={`py-1 px-3 rounded-lg text-sm transition-colors ${
              heartbeatRunning
                ? 'bg-red-600 hover:bg-red-700 text-white'
                : 'bg-green-600 hover:bg-green-700 text-white'
            }`}
          >
            {heartbeatRunning ? '⏹ Stop' : '▶ Start'}
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2 font-mono text-sm">
        {!roomId ? (
          <p className="text-gray-500 text-center">Select an agent to view their room</p>
        ) : messages.length === 0 ? (
          <p className="text-gray-500 text-center">No messages yet</p>
        ) : (
          messages.map((msg) => (
            <div key={msg.id} className={getMessageStyle(msg.sender_name)}>
              <div className="flex items-baseline gap-2">
                <span className="text-gray-500 text-xs">[{formatTime(msg.timestamp)}]</span>
                <span className="font-semibold text-blue-400">{getSenderName(msg.sender_name)}:</span>
              </div>
              <p className="mt-1 whitespace-pre-wrap">{msg.content}</p>
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 border-t border-gray-700">
        <div className="flex gap-2">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a message..."
            disabled={!roomId}
            className="flex-1 bg-gray-700 border border-gray-600 rounded-lg px-4 py-2 focus:outline-none focus:border-blue-500 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!roomId || !inputValue.trim()}
            className="bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed text-white py-2 px-6 rounded-lg transition-colors"
          >
            Send
          </button>
        </div>
      </div>
    </div>
  );
}
