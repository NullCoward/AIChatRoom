'use client';

import { useState, useEffect } from 'react';
import * as api from '@/lib/api';

interface KnowledgeModalProps {
  isOpen: boolean;
  onClose: () => void;
  agent: api.Agent | null;
}

interface TreeNode {
  key: string;
  value: unknown;
  expanded: boolean;
  path: string[];
}

export default function KnowledgeModal({ isOpen, onClose, agent }: KnowledgeModalProps) {
  const [knowledge, setKnowledge] = useState<Record<string, unknown>>({});
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set(['']));
  const [loading, setLoading] = useState(false);
  const [editingPath, setEditingPath] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);
  const [clearing, setClearing] = useState(false);

  // Fetch knowledge when modal opens or agent changes
  useEffect(() => {
    if (isOpen && agent) {
      fetchKnowledge();
    }
  }, [isOpen, agent]);

  const fetchKnowledge = async () => {
    if (!agent) return;
    setLoading(true);
    try {
      const data = await api.getAgentKnowledge(agent.id);
      setKnowledge(data);
    } catch (err) {
      console.error('Failed to fetch knowledge:', err);
      setKnowledge({});
    } finally {
      setLoading(false);
    }
  };

  const toggleExpanded = (path: string) => {
    setExpandedPaths(prev => {
      const next = new Set(prev);
      if (next.has(path)) {
        next.delete(path);
      } else {
        next.add(path);
      }
      return next;
    });
  };

  const isExpandable = (value: unknown): boolean => {
    return typeof value === 'object' && value !== null;
  };

  const getValueDisplay = (value: unknown): string => {
    if (value === null) return 'null';
    if (value === undefined) return 'undefined';
    if (typeof value === 'string') return `"${value}"`;
    if (typeof value === 'number' || typeof value === 'boolean') return String(value);
    if (Array.isArray(value)) return `Array(${value.length})`;
    if (typeof value === 'object') return `Object(${Object.keys(value).length})`;
    return String(value);
  };

  const getValueColor = (value: unknown): string => {
    if (value === null || value === undefined) return 'text-gray-500';
    if (typeof value === 'string') return 'text-green-400';
    if (typeof value === 'number') return 'text-blue-400';
    if (typeof value === 'boolean') return 'text-yellow-400';
    return 'text-gray-300';
  };

  const startEditing = (path: string, value: unknown) => {
    setEditingPath(path);
    setEditValue(typeof value === 'string' ? value : JSON.stringify(value, null, 2));
  };

  const cancelEditing = () => {
    setEditingPath(null);
    setEditValue('');
  };

  const saveEdit = async () => {
    if (!agent || editingPath === null) return;

    setSaving(true);
    try {
      // Parse the new value
      let newValue: unknown;
      try {
        newValue = JSON.parse(editValue);
      } catch {
        // If it's not valid JSON, treat it as a string
        newValue = editValue;
      }

      // Build the updated knowledge tree
      const pathParts = editingPath.split('.').filter(p => p);
      const updated = JSON.parse(JSON.stringify(knowledge));

      if (pathParts.length === 0) {
        // Editing root
        await api.updateAgentKnowledge(agent.id, typeof newValue === 'object' ? newValue as Record<string, unknown> : { value: newValue });
      } else {
        // Navigate to parent and update
        let current = updated;
        for (let i = 0; i < pathParts.length - 1; i++) {
          current = current[pathParts[i]];
        }
        current[pathParts[pathParts.length - 1]] = newValue;
        await api.updateAgentKnowledge(agent.id, updated);
      }

      await fetchKnowledge();
      setEditingPath(null);
      setEditValue('');
    } catch (err) {
      console.error('Failed to save:', err);
      alert('Failed to save changes');
    } finally {
      setSaving(false);
    }
  };

  const clearKnowledge = async () => {
    if (!agent) return;
    if (!confirm(`Are you sure you want to clear ALL knowledge for ${agent.name}? This cannot be undone.`)) return;

    setClearing(true);
    try {
      await api.clearAgentKnowledge(agent.id);
      setKnowledge({});
    } catch (err) {
      console.error('Failed to clear knowledge:', err);
      alert('Failed to clear knowledge');
    } finally {
      setClearing(false);
    }
  };

  const renderTree = (obj: Record<string, unknown>, path: string = '', depth: number = 0): JSX.Element[] => {
    const items: JSX.Element[] = [];

    for (const [key, value] of Object.entries(obj)) {
      const currentPath = path ? `${path}.${key}` : key;
      const isExpanded = expandedPaths.has(currentPath);
      const expandable = isExpandable(value);
      const isEditing = editingPath === currentPath;

      items.push(
        <div key={currentPath} className="font-mono">
          <div
            className="flex items-center gap-1 py-1 hover:bg-gray-700/30 rounded px-2 group"
            style={{ paddingLeft: `${depth * 16 + 8}px` }}
          >
            {/* Expand/collapse button */}
            {expandable ? (
              <button
                onClick={() => toggleExpanded(currentPath)}
                className="w-4 h-4 flex items-center justify-center text-gray-500 hover:text-white"
              >
                {isExpanded ? '▼' : '▶'}
              </button>
            ) : (
              <span className="w-4" />
            )}

            {/* Key */}
            <span className="text-purple-400">{key}</span>
            <span className="text-gray-500">:</span>

            {/* Value */}
            {isEditing ? (
              <div className="flex-1 flex items-center gap-2 ml-2">
                <input
                  type="text"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  className="flex-1 bg-gray-700 border border-gray-600 rounded px-2 py-0.5 text-sm focus:outline-none focus:border-blue-500"
                  autoFocus
                />
                <button
                  onClick={saveEdit}
                  disabled={saving}
                  className="text-green-400 hover:text-green-300 text-sm"
                >
                  ✓
                </button>
                <button
                  onClick={cancelEditing}
                  className="text-red-400 hover:text-red-300 text-sm"
                >
                  ✕
                </button>
              </div>
            ) : (
              <>
                <span className={`ml-1 ${getValueColor(value)}`}>
                  {getValueDisplay(value)}
                </span>
                {!expandable && (
                  <button
                    onClick={() => startEditing(currentPath, value)}
                    className="ml-2 text-gray-600 hover:text-gray-400 opacity-0 group-hover:opacity-100 text-xs"
                  >
                    edit
                  </button>
                )}
              </>
            )}
          </div>

          {/* Children */}
          {expandable && isExpanded && (
            <div>
              {renderTree(value as Record<string, unknown>, currentPath, depth + 1)}
            </div>
          )}
        </div>
      );
    }

    return items;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-800 rounded-lg shadow-xl w-full max-w-3xl mx-4 max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700 flex-shrink-0">
          <div>
            <h2 className="text-lg font-semibold">Knowledge Explorer</h2>
            {agent && <p className="text-sm text-gray-400">{agent.name}'s Self-Concept</p>}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchKnowledge}
              className="text-gray-400 hover:text-white transition-colors px-2"
              title="Refresh"
            >
              ↻
            </button>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4 min-h-0">
          {!agent ? (
            <div className="flex items-center justify-center h-full text-gray-500">
              Select an agent to view their knowledge
            </div>
          ) : loading ? (
            <div className="flex items-center justify-center h-full text-gray-400">
              Loading...
            </div>
          ) : Object.keys(knowledge).length === 0 ? (
            <div className="flex items-center justify-center h-full text-gray-500">
              No knowledge data available
            </div>
          ) : (
            <div className="text-sm">
              {renderTree(knowledge)}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex justify-between items-center flex-shrink-0">
          <div className="flex items-center gap-4">
            <span className="text-sm text-gray-500">
              {Object.keys(knowledge).length} top-level keys
            </span>
            {agent && Object.keys(knowledge).length > 0 && (
              <button
                onClick={clearKnowledge}
                disabled={clearing}
                className="text-red-400 hover:text-red-300 text-sm transition-colors disabled:opacity-50"
              >
                {clearing ? 'Clearing...' : '🗑 Clear All Knowledge'}
              </button>
            )}
          </div>
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
