'use client';

import { useState, useEffect } from 'react';
import * as api from '@/lib/api';

interface PromptsModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const PROMPT_LABELS: Record<keyof api.PromptBlocks, { label: string; description: string }> = {
  system_directives: {
    label: 'System Directives',
    description: 'General instructions for all agents about how to participate in conversations.'
  },
  persona_instructions: {
    label: 'Persona Instructions',
    description: 'Instructions for persona-type agents about their identity and pacing.'
  },
  bot_instructions: {
    label: 'Bot Instructions',
    description: 'Instructions for bot-type agents about their role and capabilities.'
  },
  batch_instructions: {
    label: 'Batch Instructions',
    description: 'Instructions for batched multi-agent processing with from_agent field support.'
  }
};

export default function PromptsModal({ isOpen, onClose }: PromptsModalProps) {
  const [prompts, setPrompts] = useState<api.PromptBlocks | null>(null);
  const [editedPrompts, setEditedPrompts] = useState<Partial<api.PromptBlocks>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);
  const [activeTab, setActiveTab] = useState<keyof api.PromptBlocks>('system_directives');

  useEffect(() => {
    if (isOpen) {
      fetchPrompts();
    }
  }, [isOpen]);

  const fetchPrompts = async () => {
    setLoading(true);
    setMessage(null);
    try {
      const data = await api.getPromptBlocks();
      setPrompts(data);
      setEditedPrompts({});
    } catch (err: any) {
      setMessage({ text: err.message || 'Failed to load prompts', type: 'error' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    if (Object.keys(editedPrompts).length === 0) {
      setMessage({ text: 'No changes to save', type: 'error' });
      return;
    }

    setSaving(true);
    setMessage(null);
    try {
      await api.savePromptBlocks(editedPrompts);
      setMessage({ text: 'Prompts saved successfully!', type: 'success' });
      // Refresh prompts to get updated values
      await fetchPrompts();
    } catch (err: any) {
      setMessage({ text: err.message || 'Failed to save prompts', type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleTextChange = (key: keyof api.PromptBlocks, value: string) => {
    setEditedPrompts(prev => ({ ...prev, [key]: value }));
  };

  const getCurrentValue = (key: keyof api.PromptBlocks): string => {
    if (key in editedPrompts) {
      return editedPrompts[key] || '';
    }
    return prompts?.[key] || '';
  };

  const hasChanges = Object.keys(editedPrompts).length > 0;

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-800 rounded-lg shadow-xl w-full max-w-4xl mx-4 max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700">
          <h2 className="text-lg font-semibold">Prompt Settings</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Tabs */}
        <div className="flex border-b border-gray-700 overflow-x-auto">
          {(Object.keys(PROMPT_LABELS) as Array<keyof api.PromptBlocks>).map((key) => (
            <button
              key={key}
              onClick={() => setActiveTab(key)}
              className={`px-4 py-2 text-sm font-medium whitespace-nowrap transition-colors ${
                activeTab === key
                  ? 'text-blue-400 border-b-2 border-blue-400 bg-gray-700/50'
                  : 'text-gray-400 hover:text-white hover:bg-gray-700/30'
              }`}
            >
              {PROMPT_LABELS[key].label}
              {key in editedPrompts && <span className="ml-1 text-amber-400">*</span>}
            </button>
          ))}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          {loading ? (
            <div className="flex items-center justify-center h-64">
              <div className="text-gray-400">Loading prompts...</div>
            </div>
          ) : (
            <div className="space-y-4">
              <p className="text-sm text-gray-400">{PROMPT_LABELS[activeTab].description}</p>
              <textarea
                value={getCurrentValue(activeTab)}
                onChange={(e) => handleTextChange(activeTab, e.target.value)}
                className="w-full h-96 bg-gray-700 border border-gray-600 rounded p-3 text-sm font-mono focus:outline-none focus:border-blue-500 resize-none"
                placeholder="Enter prompt text..."
              />
              <div className="text-xs text-gray-500">
                {getCurrentValue(activeTab).length} characters
              </div>
            </div>
          )}

          {/* Message */}
          {message && (
            <div className={`mt-4 p-3 rounded text-sm ${
              message.type === 'success' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
            }`}>
              {message.text}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex items-center justify-between">
          <div className="text-sm text-gray-400">
            {hasChanges ? (
              <span className="text-amber-400">You have unsaved changes</span>
            ) : (
              <span>No changes</span>
            )}
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => setEditedPrompts({})}
              disabled={!hasChanges}
              className="bg-gray-700 hover:bg-gray-600 disabled:bg-gray-800 disabled:text-gray-600 text-white px-4 py-2 rounded text-sm transition-colors"
            >
              Reset
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors"
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
            <button
              onClick={onClose}
              className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
