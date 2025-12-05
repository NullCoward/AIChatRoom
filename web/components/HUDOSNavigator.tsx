'use client';

import { useState, useEffect, useMemo } from 'react';
import * as api from '@/lib/api';

interface HUDOSNavigatorProps {
  isOpen: boolean;
  onClose: () => void;
  agent: api.Agent | null;
}

// Section icons for the tree
const SECTION_ICONS: Record<string, string> = {
  warnings: '⚠️',
  system: '💻',
  directives: '📜',
  memory: '🧠',
  self: '👤',
  identity: '🪪',
  knowledge: '💾',
  recent_actions: '📋',
  meta: '⚙️',
  instructions: '📝',
  available_actions: '⚡',
  response_format: '📤',
  rooms: '🏠',
  messages: '💬',
  members: '👥',
  total: '📊',
  base_hud: '🔒',
  allocatable: '📦',
  allocations: '📈',
};

type ViewMode = 'tree' | 'json' | 'toon' | 'split';
type SourceMode = 'live' | 'history';

interface HistoryHUD {
  timestamp: string;
  structure: Record<string, unknown>;
  json: string;
  toon: string;
  response: string;
  tokens: number;
  error?: string;
}

export default function HUDOSNavigator({ isOpen, onClose, agent }: HUDOSNavigatorProps) {
  const [preview, setPreview] = useState<api.HUDPreview | null>(null);
  const [schema, setSchema] = useState<api.HUDSchema | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('split');
  const [sourceMode, setSourceMode] = useState<SourceMode>('live');
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set(['', 'system', 'self', 'meta', 'rooms']));
  const [selectedPath, setSelectedPath] = useState<string>('');

  // History state
  const [history, setHistory] = useState<api.HUDHistoryEntry[]>([]);
  const [selectedHistoryIndex, setSelectedHistoryIndex] = useState<number | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);

  // Fetch data when modal opens
  useEffect(() => {
    if (isOpen && agent) {
      fetchData();
      fetchHistory();
    }
  }, [isOpen, agent]);

  // Reset to live mode when agent changes
  useEffect(() => {
    setSourceMode('live');
    setSelectedHistoryIndex(null);
  }, [agent?.id]);

  const fetchData = async () => {
    if (!agent) return;
    setLoading(true);
    try {
      const [previewData, schemaData] = await Promise.all([
        api.getHUDPreview(agent.id),
        api.getHUDSchema()
      ]);
      setPreview(previewData);
      setSchema(schemaData);
    } catch (err) {
      console.error('Failed to fetch HUD data:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchHistory = async () => {
    if (!agent) return;
    setHistoryLoading(true);
    try {
      const data = await api.getHUDHistory(agent.id, 50);
      setHistory(data);
    } catch (err) {
      console.error('Failed to fetch HUD history:', err);
    } finally {
      setHistoryLoading(false);
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

  // Get icon for a key
  const getIcon = (key: string): string => {
    return SECTION_ICONS[key] || '📄';
  };

  // Parse history entry HUD into structure
  const parseHistoryHUD = (entry: api.HUDHistoryEntry): HistoryHUD | null => {
    try {
      // Try to parse the HUD content as JSON
      let structure: Record<string, unknown>;
      try {
        structure = JSON.parse(entry.hud);
      } catch {
        // If not JSON, wrap it
        structure = { raw: entry.hud };
      }

      return {
        timestamp: entry.timestamp,
        structure,
        json: JSON.stringify(structure, null, 2),
        toon: entry.hud, // Original format (might be TOON)
        response: entry.response,
        tokens: entry.tokens,
        error: entry.error,
      };
    } catch {
      return null;
    }
  };

  // Get current display data based on source mode
  const displayData = useMemo(() => {
    if (sourceMode === 'live') {
      return preview ? {
        structure: preview.structure,
        json: preview.json,
        toon: preview.toon,
        stats: preview.stats,
        isHistory: false,
      } : null;
    } else if (selectedHistoryIndex !== null && history[selectedHistoryIndex]) {
      const parsed = parseHistoryHUD(history[selectedHistoryIndex]);
      if (parsed) {
        return {
          structure: parsed.structure,
          json: parsed.json,
          toon: parsed.toon,
          stats: {
            json_chars: parsed.json.length,
            toon_chars: parsed.toon.length,
            json_tokens: Math.round(parsed.json.length / 4),
            toon_tokens: Math.round(parsed.toon.length / 4),
            savings_chars: parsed.json.length - parsed.toon.length,
            savings_tokens: 0,
            savings_pct: Math.round((1 - parsed.toon.length / parsed.json.length) * 100),
          },
          isHistory: true,
          historyEntry: history[selectedHistoryIndex],
        };
      }
    }
    return null;
  }, [sourceMode, preview, selectedHistoryIndex, history]);

  // Render tree node
  const renderTreeNode = (
    obj: Record<string, unknown>,
    path: string = '',
    depth: number = 0
  ): JSX.Element[] => {
    const items: JSX.Element[] = [];

    for (const [key, value] of Object.entries(obj)) {
      const currentPath = path ? `${path}.${key}` : key;
      const isExpanded = expandedPaths.has(currentPath);
      const isSelected = selectedPath === currentPath;
      const isObject = typeof value === 'object' && value !== null && !Array.isArray(value);
      const isArray = Array.isArray(value);
      const hasChildren = isObject || isArray;

      items.push(
        <div key={currentPath} className="select-none">
          <div
            className={`flex items-center gap-1 py-0.5 px-2 cursor-pointer rounded transition-colors ${
              isSelected ? 'bg-blue-600/40' : 'hover:bg-gray-700/40'
            }`}
            style={{ paddingLeft: `${depth * 16 + 8}px` }}
            onClick={() => {
              if (hasChildren) toggleExpanded(currentPath);
              setSelectedPath(currentPath);
            }}
          >
            {/* Expand/collapse indicator */}
            {hasChildren ? (
              <span className="w-4 text-gray-500 text-xs">
                {isExpanded ? '▼' : '▶'}
              </span>
            ) : (
              <span className="w-4" />
            )}

            {/* Icon */}
            <span className="text-sm">{getIcon(key)}</span>

            {/* Key name */}
            <span className="text-purple-400 font-mono text-sm">{key}</span>

            {/* Value preview for non-objects */}
            {!hasChildren && (
              <span className="text-gray-400 text-xs ml-2 truncate max-w-[200px]">
                {typeof value === 'string'
                  ? `"${value.length > 30 ? value.slice(0, 30) + '...' : value}"`
                  : String(value)}
              </span>
            )}

            {/* Type badge */}
            {hasChildren && (
              <span className="text-gray-600 text-xs ml-2">
                {isArray ? `[${(value as unknown[]).length}]` : `{${Object.keys(value as object).length}}`}
              </span>
            )}
          </div>

          {/* Children */}
          {hasChildren && isExpanded && (
            <div>
              {isArray
                ? (value as unknown[]).map((item, idx) => {
                    if (typeof item === 'object' && item !== null) {
                      return renderTreeNode(
                        { [idx]: item } as Record<string, unknown>,
                        currentPath,
                        depth + 1
                      );
                    }
                    return (
                      <div
                        key={`${currentPath}.${idx}`}
                        className="flex items-center gap-1 py-0.5 px-2 text-sm"
                        style={{ paddingLeft: `${(depth + 1) * 16 + 8}px` }}
                      >
                        <span className="w-4" />
                        <span className="text-gray-500">[{idx}]</span>
                        <span className="text-green-400 ml-2 truncate max-w-[300px]">
                          {typeof item === 'string' ? `"${item}"` : String(item)}
                        </span>
                      </div>
                    );
                  })
                : renderTreeNode(value as Record<string, unknown>, currentPath, depth + 1)}
            </div>
          )}
        </div>
      );
    }

    return items;
  };

  // Format timestamp for display
  const formatTimestamp = (ts: string) => {
    const date = new Date(ts);
    return date.toLocaleString();
  };

  const formatRelativeTime = (ts: string) => {
    const now = new Date();
    const date = new Date(ts);
    const diff = now.getTime() - date.getTime();

    if (diff < 60000) return 'just now';
    if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
    if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
    return `${Math.floor(diff / 86400000)}d ago`;
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-900 rounded-lg shadow-2xl w-[95vw] max-w-7xl h-[90vh] flex flex-col border border-gray-700"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-gray-700 flex-shrink-0">
          <div className="flex items-center gap-4">
            <div>
              <h2 className="text-xl font-bold flex items-center gap-2">
                <span>💻</span> HUD OS Navigator
                {sourceMode === 'history' && (
                  <span className="text-sm font-normal text-amber-400 ml-2">
                    📜 Viewing History
                  </span>
                )}
              </h2>
              {agent && <p className="text-sm text-gray-400">Agent: {agent.name}</p>}
            </div>

            {/* Source mode toggle */}
            <div className="flex bg-gray-800 rounded-lg p-1 ml-4">
              <button
                onClick={() => {
                  setSourceMode('live');
                  setSelectedHistoryIndex(null);
                }}
                className={`px-3 py-1 rounded text-sm transition-colors ${
                  sourceMode === 'live'
                    ? 'bg-green-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                🔴 Live
              </button>
              <button
                onClick={() => setSourceMode('history')}
                className={`px-3 py-1 rounded text-sm transition-colors ${
                  sourceMode === 'history'
                    ? 'bg-amber-600 text-white'
                    : 'text-gray-400 hover:text-white'
                }`}
              >
                📜 History
              </button>
            </div>

            {/* View mode tabs */}
            <div className="flex bg-gray-800 rounded-lg p-1 ml-4">
              {(['tree', 'split', 'json', 'toon'] as ViewMode[]).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={`px-3 py-1 rounded text-sm transition-colors ${
                    viewMode === mode
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-400 hover:text-white'
                  }`}
                >
                  {mode === 'tree' && '🌳 Tree'}
                  {mode === 'split' && '📊 Split'}
                  {mode === 'json' && '{ } JSON'}
                  {mode === 'toon' && '⚡ TOON'}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Stats */}
            {displayData?.stats && (
              <div className="flex items-center gap-4 text-sm">
                <div className="text-gray-400">
                  JSON: <span className="text-yellow-400">{displayData.stats.json_tokens} tok</span>
                </div>
                <div className="text-gray-400">
                  TOON: <span className="text-green-400">{displayData.stats.toon_tokens} tok</span>
                </div>
                {displayData.stats.savings_pct > 0 && (
                  <div className="text-green-400 font-semibold">
                    -{displayData.stats.savings_pct}% savings
                  </div>
                )}
              </div>
            )}

            {sourceMode === 'live' && (
              <button
                onClick={fetchData}
                className="text-gray-400 hover:text-white transition-colors p-2"
                title="Refresh"
              >
                ↻
              </button>
            )}
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors text-xl"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-hidden flex min-h-0">
          {/* History sidebar (when in history mode) */}
          {sourceMode === 'history' && (
            <div className="w-72 border-r border-gray-700 flex flex-col overflow-hidden bg-gray-850">
              <div className="p-3 border-b border-gray-700 flex items-center justify-between">
                <h3 className="text-sm font-semibold text-gray-300">
                  📜 Heartbeat History
                </h3>
                <button
                  onClick={fetchHistory}
                  className="text-gray-500 hover:text-white text-sm"
                  title="Refresh history"
                >
                  ↻
                </button>
              </div>
              <div className="flex-1 overflow-y-auto">
                {historyLoading ? (
                  <div className="p-4 text-center text-gray-500">Loading...</div>
                ) : history.length === 0 ? (
                  <div className="p-4 text-center text-gray-500">No history available</div>
                ) : (
                  history.map((entry, index) => (
                    <button
                      key={index}
                      onClick={() => setSelectedHistoryIndex(index)}
                      className={`w-full text-left p-3 border-b border-gray-700/50 transition-colors ${
                        selectedHistoryIndex === index
                          ? 'bg-amber-900/30 border-l-2 border-l-amber-500'
                          : 'hover:bg-gray-800'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">
                          {formatRelativeTime(entry.timestamp)}
                        </span>
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          entry.error ? 'bg-red-900/50 text-red-300' : 'bg-green-900/50 text-green-300'
                        }`}>
                          {entry.error ? 'ERR' : 'OK'}
                        </span>
                      </div>
                      <div className="text-xs text-gray-500 mt-1">
                        {entry.tokens} tokens
                      </div>
                      <div className="text-sm text-gray-300 mt-1 truncate">
                        {entry.response?.slice(0, 50) || '(no response)'}
                      </div>
                    </button>
                  ))
                )}
              </div>
            </div>
          )}

          {/* Main content area */}
          {!agent ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              Select an agent to view their HUD
            </div>
          ) : loading && sourceMode === 'live' ? (
            <div className="flex-1 flex items-center justify-center text-gray-400">
              <div className="animate-pulse">Loading HUD data...</div>
            </div>
          ) : sourceMode === 'history' && selectedHistoryIndex === null ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              <div className="text-center">
                <div className="text-4xl mb-3">📜</div>
                <div className="text-lg">Select a heartbeat from the history</div>
                <div className="text-sm text-gray-600 mt-1">
                  Click any entry on the left to view its HUD
                </div>
              </div>
            </div>
          ) : !displayData ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              Failed to load HUD data
            </div>
          ) : (
            <>
              {/* Tree View (left side for split, full for tree mode) */}
              {(viewMode === 'tree' || viewMode === 'split') && (
                <div
                  className={`${
                    viewMode === 'split' ? 'w-1/3 border-r border-gray-700' : 'flex-1'
                  } overflow-auto p-4`}
                >
                  <div className="mb-3">
                    <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wide">
                      Structure Navigator
                    </h3>
                  </div>
                  <div className="font-mono text-sm">
                    {renderTreeNode(displayData.structure)}
                  </div>
                </div>
              )}

              {/* Code views (right side for split, full for json/toon) */}
              {(viewMode === 'json' || viewMode === 'toon' || viewMode === 'split') && (
                <div className={`${viewMode === 'split' ? 'flex-1' : 'flex-1'} flex flex-col overflow-hidden`}>
                  {viewMode === 'split' ? (
                    // Split view: JSON and TOON side by side
                    <div className="flex-1 flex overflow-hidden">
                      {/* JSON Panel */}
                      <div className="flex-1 flex flex-col overflow-hidden border-r border-gray-700">
                        <div className="p-3 border-b border-gray-700 flex items-center justify-between bg-gray-800/50">
                          <h3 className="text-sm font-semibold text-yellow-400 flex items-center gap-2">
                            {'{ }'} JSON Format
                          </h3>
                          <span className="text-xs text-gray-500">
                            {displayData.stats.json_chars} chars / ~{displayData.stats.json_tokens} tokens
                          </span>
                        </div>
                        <pre className="flex-1 overflow-auto p-4 text-xs text-gray-300 bg-gray-950 font-mono whitespace-pre">
                          {displayData.json}
                        </pre>
                      </div>

                      {/* TOON Panel */}
                      <div className="flex-1 flex flex-col overflow-hidden">
                        <div className="p-3 border-b border-gray-700 flex items-center justify-between bg-gray-800/50">
                          <h3 className="text-sm font-semibold text-green-400 flex items-center gap-2">
                            ⚡ TOON Format
                          </h3>
                          <span className="text-xs text-gray-500">
                            {displayData.stats.toon_chars} chars / ~{displayData.stats.toon_tokens} tokens
                          </span>
                        </div>
                        <pre className="flex-1 overflow-auto p-4 text-xs text-gray-300 bg-gray-950 font-mono whitespace-pre">
                          {displayData.toon}
                        </pre>
                      </div>
                    </div>
                  ) : (
                    // Single view: just JSON or TOON
                    <div className="flex-1 flex flex-col overflow-hidden">
                      <div className="p-3 border-b border-gray-700 flex items-center justify-between bg-gray-800/50">
                        <h3 className={`text-sm font-semibold flex items-center gap-2 ${
                          viewMode === 'json' ? 'text-yellow-400' : 'text-green-400'
                        }`}>
                          {viewMode === 'json' ? '{ } JSON Format' : '⚡ TOON Format'}
                        </h3>
                        <span className="text-xs text-gray-500">
                          {viewMode === 'json'
                            ? `${displayData.stats.json_chars} chars / ~${displayData.stats.json_tokens} tokens`
                            : `${displayData.stats.toon_chars} chars / ~${displayData.stats.toon_tokens} tokens`}
                        </span>
                      </div>
                      <pre className="flex-1 overflow-auto p-4 text-sm text-gray-300 bg-gray-950 font-mono whitespace-pre">
                        {viewMode === 'json' ? displayData.json : displayData.toon}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer with context info */}
        <div className="p-3 border-t border-gray-700 bg-gray-800/30 flex-shrink-0">
          <div className="flex items-center justify-between text-xs text-gray-500">
            <div className="flex items-center gap-4">
              {sourceMode === 'history' && selectedHistoryIndex !== null && history[selectedHistoryIndex] && (
                <span className="text-amber-400">
                  📅 {formatTimestamp(history[selectedHistoryIndex].timestamp)}
                </span>
              )}
              <span>💡 HUD = Heads-Up Display, the context window sent to agents each heartbeat</span>
            </div>
            <div className="flex items-center gap-4">
              <span>system: Core directives</span>
              <span>self: Agent identity & knowledge</span>
              <span>meta: Instructions & actions</span>
              <span>rooms: Messages & members</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
