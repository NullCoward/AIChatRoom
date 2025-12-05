'use client';

import { useState, useEffect } from 'react';
import * as api from '@/lib/api';

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  apiStatus: api.ApiStatus | undefined;
  onApiKeySet: () => void;
}

export default function SettingsModal({ isOpen, onClose, apiStatus, onApiKeySet }: SettingsModalProps) {
  const [apiKey, setApiKey] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // Heartbeat settings
  const [heartbeatStatus, setHeartbeatStatus] = useState<api.HeartbeatStatus | null>(null);
  const [pullForward, setPullForward] = useState(0);
  const [savingPullForward, setSavingPullForward] = useState(false);

  // Clear form when modal opens/closes
  useEffect(() => {
    if (isOpen) {
      setApiKey('');
      setMessage(null);
      fetchHeartbeatStatus();
    }
  }, [isOpen]);

  const fetchHeartbeatStatus = async () => {
    try {
      const status = await api.getHeartbeatStatus();
      setHeartbeatStatus(status);
      setPullForward(status.pull_forward);
    } catch (err) {
      console.error('Failed to fetch heartbeat status:', err);
    }
  };

  const handleSaveApiKey = async () => {
    if (!apiKey.trim()) {
      setMessage({ text: 'Please enter an API key', type: 'error' });
      return;
    }

    setSaving(true);
    setMessage(null);

    try {
      await api.setApiKey(apiKey.trim());
      setMessage({ text: 'API key saved successfully!', type: 'success' });
      setApiKey('');
      onApiKeySet();
    } catch (err: any) {
      setMessage({ text: err.message || 'Failed to save API key', type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleSavePullForward = async () => {
    setSavingPullForward(true);
    try {
      await api.setPullForward(pullForward);
      await fetchHeartbeatStatus();
      setMessage({ text: 'Pull-forward setting saved!', type: 'success' });
    } catch (err: any) {
      setMessage({ text: err.message || 'Failed to save setting', type: 'error' });
    } finally {
      setSavingPullForward(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-800 rounded-lg shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700 sticky top-0 bg-gray-800">
          <h2 className="text-lg font-semibold">Settings</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Content */}
        <div className="p-4 space-y-6">
          {/* API Status */}
          <div className="bg-gray-700/50 rounded-lg p-4">
            <h3 className="text-sm font-medium text-gray-300 mb-2">API Status</h3>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${apiStatus?.connected ? 'bg-green-400' : 'bg-red-400'}`} />
              <span className="text-sm">
                {apiStatus?.connected ? 'Connected to OpenAI' : 'Not connected'}
              </span>
            </div>
            {apiStatus?.message && (
              <p className="text-sm text-gray-400 mt-1">{apiStatus.message}</p>
            )}
            {apiStatus?.models && apiStatus.models.length > 0 && (
              <p className="text-xs text-gray-500 mt-2">
                {apiStatus.models.length} models available
              </p>
            )}
          </div>

          {/* API Key */}
          <div>
            <label className="block text-sm font-medium text-gray-300 mb-2">
              OpenAI API Key
            </label>
            <div className="flex gap-2">
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                className="flex-1 bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
              />
              <button
                onClick={handleSaveApiKey}
                disabled={saving}
                className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors"
              >
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
            <p className="text-xs text-gray-500 mt-1">
              Your API key is stored locally and used to communicate with OpenAI.
            </p>
          </div>

          {/* Heartbeat Optimization */}
          <div className="border-t border-gray-700 pt-4">
            <h3 className="text-sm font-medium text-gray-300 mb-3">Heartbeat Optimization</h3>

            <div className="bg-gray-700/50 rounded-lg p-4 space-y-4">
              {/* Pull-forward setting */}
              <div>
                <label className="block text-sm text-gray-300 mb-2">
                  Pull-Forward Window (seconds)
                </label>
                <div className="flex items-center gap-4">
                  <input
                    type="range"
                    min="0"
                    max="5"
                    step="0.5"
                    value={pullForward}
                    onChange={(e) => setPullForward(parseFloat(e.target.value))}
                    className="flex-1 h-2 bg-gray-600 rounded-lg appearance-none cursor-pointer accent-blue-500"
                  />
                  <span className="w-12 text-center font-mono text-sm">
                    {pullForward.toFixed(1)}s
                  </span>
                  <button
                    onClick={handleSavePullForward}
                    disabled={savingPullForward || pullForward === (heartbeatStatus?.pull_forward ?? 0)}
                    className="bg-blue-600 hover:bg-blue-700 disabled:bg-gray-600 text-white px-3 py-1 rounded text-sm transition-colors"
                  >
                    {savingPullForward ? '...' : 'Apply'}
                  </button>
                </div>
                <p className="text-xs text-gray-500 mt-2">
                  When a heartbeat fires, also process agents whose heartbeats are scheduled
                  within this window. Set to 0 to disable bundling.
                </p>
                {pullForward > 0 && (
                  <p className="text-xs text-amber-400/80 mt-1">
                    Bundling enabled: Agents with heartbeats up to {pullForward}s in the future will be processed together.
                  </p>
                )}
              </div>

              {/* Current status */}
              {heartbeatStatus && (
                <div className="text-xs text-gray-500 pt-2 border-t border-gray-600">
                  Status: {heartbeatStatus.running ? (
                    <span className="text-green-400">Running</span>
                  ) : (
                    <span className="text-gray-400">Stopped</span>
                  )} | Interval: {heartbeatStatus.interval}s | Pull-forward: {heartbeatStatus.pull_forward}s
                </div>
              )}
            </div>
          </div>

          {/* Message */}
          {message && (
            <div className={`p-3 rounded text-sm ${
              message.type === 'success' ? 'bg-green-900/50 text-green-300' : 'bg-red-900/50 text-red-300'
            }`}>
              {message.text}
            </div>
          )}

          {/* About */}
          <div className="border-t border-gray-700 pt-4">
            <h3 className="text-sm font-medium text-gray-300 mb-2">About</h3>
            <p className="text-sm text-gray-400">
              AI Chat Room - A multi-agent chat application with autonomous AI agents.
            </p>
            <p className="text-xs text-gray-500 mt-1">
              Agents communicate through a heartbeat system and maintain their own self-concept.
            </p>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex justify-end sticky bottom-0 bg-gray-800">
          <button
            onClick={onClose}
            className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
