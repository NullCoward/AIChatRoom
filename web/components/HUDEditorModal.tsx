'use client';

import { useState, useEffect, useMemo } from 'react';
import * as api from '@/lib/api';

interface HUDEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
}

interface PromptNode {
  description?: string;
  content?: string;
  [key: string]: PromptNode | string | undefined;
}

type TreeItem = {
  path: string;
  key: string;
  depth: number;
  hasContent: boolean;
  hasChildren: boolean;
  description?: string;
};

// Section icons for common sections
const SECTION_ICONS: Record<string, string> = {
  technical: '⚙️',
  philosophy: '🧠',
  response_format: '📝',
  actions: '⚡',
  knowledge: '💾',
  reactions: '👍',
  room_access: '🔐',
  attention: '👁️',
  topics: '💬',
  settings: '🔧',
  identity: '👤',
  communication: '📡',
  silence: '🤫',
  memory: '🧩',
  own_room: '🏠',
  time: '⏰',
};

// Build flat list of tree items for rendering
function buildTreeItems(data: Record<string, unknown>, parentPath: string = '', depth: number = 0): TreeItem[] {
  const items: TreeItem[] = [];

  for (const [key, value] of Object.entries(data)) {
    if (key === 'description' || key === 'content') continue;

    const path = parentPath ? `${parentPath}.${key}` : key;
    const node = value as PromptNode;

    const hasContent = typeof node === 'object' && node !== null && 'content' in node;
    const childKeys = typeof node === 'object' && node !== null
      ? Object.keys(node).filter(k => k !== 'description' && k !== 'content')
      : [];
    const hasChildren = childKeys.length > 0;

    items.push({
      path,
      key,
      depth,
      hasContent,
      hasChildren,
      description: typeof node === 'object' && node !== null ? node.description : undefined,
    });

    // Recurse into children
    if (typeof node === 'object' && node !== null) {
      const childData: Record<string, unknown> = {};
      for (const childKey of childKeys) {
        childData[childKey] = node[childKey];
      }
      items.push(...buildTreeItems(childData, path, depth + 1));
    }
  }

  return items;
}

// Get a node by path
function getNodeByPath(data: Record<string, unknown>, path: string): PromptNode | null {
  const parts = path.split('.');
  let current: unknown = data;

  for (const part of parts) {
    if (typeof current !== 'object' || current === null) return null;
    current = (current as Record<string, unknown>)[part];
  }

  return current as PromptNode | null;
}

// Set a node by path
function setNodeByPath(data: Record<string, unknown>, path: string, value: PromptNode): Record<string, unknown> {
  const result = JSON.parse(JSON.stringify(data));
  const parts = path.split('.');
  let current = result;

  for (let i = 0; i < parts.length - 1; i++) {
    if (!(parts[i] in current)) {
      current[parts[i]] = {};
    }
    current = current[parts[i]];
  }

  current[parts[parts.length - 1]] = value;
  return result;
}

// Delete a node by path
function deleteNodeByPath(data: Record<string, unknown>, path: string): Record<string, unknown> {
  const result = JSON.parse(JSON.stringify(data));
  const parts = path.split('.');
  let current = result;

  for (let i = 0; i < parts.length - 1; i++) {
    if (!(parts[i] in current)) return result;
    current = current[parts[i]];
  }

  delete current[parts[parts.length - 1]];
  return result;
}

export default function HUDEditorModal({ isOpen, onClose }: HUDEditorModalProps) {
  const [prompts, setPrompts] = useState<Record<string, unknown>>({});
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [editedDescription, setEditedDescription] = useState('');
  const [editedContent, setEditedContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [hasChanges, setHasChanges] = useState(false);
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set(['technical', 'philosophy']));
  const [showPreview, setShowPreview] = useState(false);
  const [newSectionName, setNewSectionName] = useState('');
  const [addingTo, setAddingTo] = useState<string | null>(null);

  // Fetch prompts when modal opens
  useEffect(() => {
    if (isOpen) {
      fetchPrompts();
    }
  }, [isOpen]);

  // Update edited values when selection changes
  useEffect(() => {
    if (selectedPath) {
      const node = getNodeByPath(prompts, selectedPath);
      if (node && typeof node === 'object') {
        setEditedDescription(node.description || '');
        setEditedContent(node.content || '');
      }
    }
  }, [selectedPath, prompts]);

  const fetchPrompts = async () => {
    setLoading(true);
    try {
      const data = await api.getPrompts();
      setPrompts(data);
      setHasChanges(false);
    } catch (err) {
      console.error('Failed to fetch prompts:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await api.savePrompts(prompts);
      setHasChanges(false);
    } catch (err) {
      console.error('Failed to save prompts:', err);
      alert('Failed to save prompts');
    } finally {
      setSaving(false);
    }
  };

  const handleUpdateNode = () => {
    if (!selectedPath) return;

    const node = getNodeByPath(prompts, selectedPath);
    if (!node || typeof node !== 'object') return;

    const updatedNode: PromptNode = {
      ...node,
      description: editedDescription || undefined,
      content: editedContent || undefined,
    };

    // Remove empty fields
    if (!updatedNode.description) delete updatedNode.description;
    if (!updatedNode.content) delete updatedNode.content;

    const newPrompts = setNodeByPath(prompts, selectedPath, updatedNode);
    setPrompts(newPrompts);
    setHasChanges(true);
  };

  const handleAddSection = (parentPath: string | null) => {
    if (!newSectionName.trim()) return;

    const key = newSectionName.trim().toLowerCase().replace(/\s+/g, '_');
    const path = parentPath ? `${parentPath}.${key}` : key;

    const newNode: PromptNode = {
      description: `Description for ${newSectionName}`,
      content: '',
    };

    const newPrompts = setNodeByPath(prompts, path, newNode);
    setPrompts(newPrompts);
    setHasChanges(true);
    setSelectedPath(path);
    setNewSectionName('');
    setAddingTo(null);

    // Expand parent
    if (parentPath) {
      setExpandedPaths(prev => new Set([...Array.from(prev), parentPath]));
    }
  };

  const handleDeleteSection = (path: string) => {
    if (!confirm(`Delete section "${path}"? This cannot be undone.`)) return;

    const newPrompts = deleteNodeByPath(prompts, path);
    setPrompts(newPrompts);
    setHasChanges(true);

    if (selectedPath === path) {
      setSelectedPath(null);
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

  // Build tree items
  const treeItems = useMemo(() => buildTreeItems(prompts), [prompts]);

  // Filter visible items based on expansion state
  const visibleItems = useMemo(() => {
    const visible: TreeItem[] = [];

    for (const item of treeItems) {
      // Always show root items
      if (item.depth === 0) {
        visible.push(item);
        continue;
      }

      // Check if all ancestors are expanded
      const pathParts = item.path.split('.');
      let allExpanded = true;
      for (let i = 1; i < pathParts.length; i++) {
        const ancestorPath = pathParts.slice(0, i).join('.');
        if (!expandedPaths.has(ancestorPath)) {
          allExpanded = false;
          break;
        }
      }

      if (allExpanded) {
        visible.push(item);
      }
    }

    return visible;
  }, [treeItems, expandedPaths]);

  // Build preview of the rendered prompts
  const previewContent = useMemo(() => {
    if (!selectedPath) return '';

    const node = getNodeByPath(prompts, selectedPath);
    if (!node || typeof node !== 'object') return '';

    const parts: string[] = [];

    // Build section header
    const sectionName = selectedPath.split('.').pop()?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase()) || '';

    if (node.content) {
      parts.push(`## ${sectionName}`);
      parts.push(node.content);
    }

    return parts.join('\n');
  }, [selectedPath, prompts]);

  if (!isOpen) return null;

  const selectedNode = selectedPath ? getNodeByPath(prompts, selectedPath) : null;

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-800 rounded-lg shadow-xl w-full max-w-6xl mx-4 max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700 flex-shrink-0">
          <div className="flex items-center gap-4">
            <div>
              <h2 className="text-lg font-semibold">HUD Prompt Editor</h2>
              <p className="text-sm text-gray-400">Configure agent prompts and behaviors</p>
            </div>
            {hasChanges && (
              <span className="text-xs bg-yellow-900/50 text-yellow-300 px-2 py-1 rounded">
                Unsaved changes
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchPrompts}
              className="text-gray-400 hover:text-white transition-colors px-2"
              title="Reload"
            >
              ↻
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className={`px-4 py-1.5 rounded text-sm transition-colors ${
                hasChanges
                  ? 'bg-blue-600 hover:bg-blue-700 text-white'
                  : 'bg-gray-700 text-gray-500'
              }`}
            >
              {saving ? 'Saving...' : 'Save All'}
            </button>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors ml-2"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 flex min-h-0">
          {loading ? (
            <div className="flex-1 flex items-center justify-center text-gray-400">
              Loading...
            </div>
          ) : (
            <>
              {/* Tree View */}
              <div className="w-72 border-r border-gray-700 overflow-y-auto flex-shrink-0">
                <div className="p-2">
                  {/* Add root section button */}
                  {addingTo === '' ? (
                    <div className="flex items-center gap-1 p-2 bg-gray-700 rounded mb-2">
                      <input
                        type="text"
                        value={newSectionName}
                        onChange={(e) => setNewSectionName(e.target.value)}
                        placeholder="Section name"
                        className="flex-1 bg-gray-600 border-none rounded px-2 py-1 text-sm focus:outline-none"
                        autoFocus
                        onKeyDown={(e) => {
                          if (e.key === 'Enter') handleAddSection(null);
                          if (e.key === 'Escape') setAddingTo(null);
                        }}
                      />
                      <button
                        onClick={() => handleAddSection(null)}
                        className="text-green-400 hover:text-green-300 px-1"
                      >
                        ✓
                      </button>
                      <button
                        onClick={() => setAddingTo(null)}
                        className="text-gray-400 hover:text-white px-1"
                      >
                        ✕
                      </button>
                    </div>
                  ) : (
                    <button
                      onClick={() => setAddingTo('')}
                      className="w-full text-left text-xs text-gray-500 hover:text-gray-300 p-2 mb-2"
                    >
                      + Add root section
                    </button>
                  )}

                  {/* Tree items */}
                  {visibleItems.map((item) => (
                    <div key={item.path}>
                      <button
                        onClick={() => {
                          setSelectedPath(item.path);
                          if (item.hasChildren) {
                            toggleExpanded(item.path);
                          }
                        }}
                        className={`w-full text-left p-2 rounded flex items-center gap-2 group transition-colors ${
                          selectedPath === item.path
                            ? 'bg-blue-600/30 text-blue-300'
                            : 'hover:bg-gray-700/50'
                        }`}
                        style={{ paddingLeft: `${item.depth * 16 + 8}px` }}
                      >
                        {/* Expand/collapse */}
                        {item.hasChildren ? (
                          <span className="w-4 text-gray-500">
                            {expandedPaths.has(item.path) ? '▼' : '▶'}
                          </span>
                        ) : (
                          <span className="w-4" />
                        )}

                        {/* Icon */}
                        <span className="text-sm">
                          {SECTION_ICONS[item.key] || (item.hasContent ? '📄' : '📁')}
                        </span>

                        {/* Label */}
                        <span className="flex-1 text-sm truncate">
                          {item.key.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                        </span>

                        {/* Content indicator */}
                        {item.hasContent && (
                          <span className="w-2 h-2 rounded-full bg-green-400" title="Has content" />
                        )}

                        {/* Delete button */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleDeleteSection(item.path);
                          }}
                          className="opacity-0 group-hover:opacity-100 text-red-400 hover:text-red-300 px-1"
                        >
                          ×
                        </button>
                      </button>

                      {/* Add child section */}
                      {expandedPaths.has(item.path) && (
                        addingTo === item.path ? (
                          <div
                            className="flex items-center gap-1 p-2 bg-gray-700 rounded my-1"
                            style={{ marginLeft: `${(item.depth + 1) * 16 + 8}px` }}
                          >
                            <input
                              type="text"
                              value={newSectionName}
                              onChange={(e) => setNewSectionName(e.target.value)}
                              placeholder="Section name"
                              className="flex-1 bg-gray-600 border-none rounded px-2 py-1 text-sm focus:outline-none"
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleAddSection(item.path);
                                if (e.key === 'Escape') setAddingTo(null);
                              }}
                            />
                            <button
                              onClick={() => handleAddSection(item.path)}
                              className="text-green-400 hover:text-green-300 px-1"
                            >
                              ✓
                            </button>
                            <button
                              onClick={() => setAddingTo(null)}
                              className="text-gray-400 hover:text-white px-1"
                            >
                              ✕
                            </button>
                          </div>
                        ) : (
                          <button
                            onClick={() => setAddingTo(item.path)}
                            className="text-xs text-gray-600 hover:text-gray-400 p-1"
                            style={{ marginLeft: `${(item.depth + 1) * 16 + 24}px` }}
                          >
                            + Add child
                          </button>
                        )
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Editor */}
              <div className="flex-1 flex flex-col min-h-0">
                {selectedPath && selectedNode && typeof selectedNode === 'object' ? (
                  <>
                    {/* Section Header */}
                    <div className="p-4 border-b border-gray-700 flex-shrink-0">
                      <div className="flex items-center justify-between">
                        <div>
                          <h3 className="font-semibold flex items-center gap-2">
                            <span>{SECTION_ICONS[selectedPath.split('.').pop() || ''] || '📄'}</span>
                            {selectedPath.split('.').pop()?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}
                          </h3>
                          <p className="text-xs text-gray-500 font-mono">{selectedPath}</p>
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={() => setShowPreview(!showPreview)}
                            className={`px-3 py-1 rounded text-sm ${
                              showPreview
                                ? 'bg-purple-600/30 text-purple-300'
                                : 'bg-gray-700 text-gray-400 hover:text-white'
                            }`}
                          >
                            {showPreview ? '✓ Preview' : 'Preview'}
                          </button>
                          <button
                            onClick={handleUpdateNode}
                            className="bg-green-600 hover:bg-green-700 text-white px-3 py-1 rounded text-sm"
                          >
                            Apply Changes
                          </button>
                        </div>
                      </div>
                    </div>

                    {/* Editor Content */}
                    <div className="flex-1 overflow-auto p-4 space-y-4">
                      {/* Description */}
                      <div>
                        <label className="block text-sm text-gray-400 mb-1">
                          Description
                          <span className="text-gray-600 ml-2">(internal documentation)</span>
                        </label>
                        <input
                          type="text"
                          value={editedDescription}
                          onChange={(e) => setEditedDescription(e.target.value)}
                          placeholder="Brief description of this section's purpose"
                          className="w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:border-blue-500"
                        />
                      </div>

                      {/* Content */}
                      <div className="flex-1 flex flex-col">
                        <label className="block text-sm text-gray-400 mb-1">
                          Content
                          <span className="text-gray-600 ml-2">(prompt text sent to agents)</span>
                        </label>
                        <textarea
                          value={editedContent}
                          onChange={(e) => setEditedContent(e.target.value)}
                          placeholder="Enter the prompt content here. Supports Markdown formatting."
                          className="flex-1 min-h-[300px] w-full bg-gray-700 border border-gray-600 rounded px-3 py-2 text-sm font-mono focus:outline-none focus:border-blue-500 resize-none"
                        />
                      </div>

                      {/* Preview */}
                      {showPreview && editedContent && (
                        <div>
                          <label className="block text-sm text-gray-400 mb-1">
                            Preview
                            <span className="text-gray-600 ml-2">(how it appears to agents)</span>
                          </label>
                          <div className="bg-gray-900 border border-gray-700 rounded p-4 text-sm">
                            <pre className="whitespace-pre-wrap font-mono text-gray-300">
                              {`## ${selectedPath.split('.').pop()?.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase())}\n${editedContent}`}
                            </pre>
                          </div>
                        </div>
                      )}

                      {/* Tips */}
                      <div className="bg-gray-700/30 rounded p-3 text-xs text-gray-500">
                        <strong className="text-gray-400">Tips:</strong>
                        <ul className="list-disc ml-4 mt-1 space-y-1">
                          <li>Use <code className="bg-gray-800 px-1 rounded">##</code> for section headers in content</li>
                          <li>Use <code className="bg-gray-800 px-1 rounded">`code`</code> for inline code formatting</li>
                          <li>Use <code className="bg-gray-800 px-1 rounded">```json</code> blocks for JSON examples</li>
                          <li>Technical sections define response formats; Philosophy sections shape agent personality</li>
                        </ul>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-gray-500">
                    <div className="text-center">
                      <div className="text-4xl mb-2">📝</div>
                      <div>Select a section to edit</div>
                      <div className="text-xs text-gray-600 mt-1">
                        Click any section on the left
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-gray-700 flex justify-between items-center flex-shrink-0">
          <div className="text-sm text-gray-500">
            {treeItems.length} sections • {treeItems.filter(i => i.hasContent).length} with content
          </div>
          <div className="flex items-center gap-2">
            {hasChanges && (
              <button
                onClick={fetchPrompts}
                className="text-gray-400 hover:text-white px-3 py-1.5 text-sm"
              >
                Discard Changes
              </button>
            )}
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
