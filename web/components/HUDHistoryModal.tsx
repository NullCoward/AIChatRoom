'use client';

import { useState, useEffect, useRef, useMemo } from 'react';
import * as api from '@/lib/api';

interface HUDHistoryModalProps {
  isOpen: boolean;
  onClose: () => void;
  agent: api.Agent | null;
}

type ViewMode = 'structured' | 'raw' | 'response' | 'diff';

// Mini sparkline component for token usage visualization
function TokenSparkline({ data, maxTokens }: { data: number[]; maxTokens: number }) {
  if (data.length === 0) return null;

  const height = 24;
  const width = 60;
  const points = data.slice(-20).map((val, i, arr) => {
    const x = (i / (arr.length - 1 || 1)) * width;
    const y = height - (val / maxTokens) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <svg width={width} height={height} className="inline-block ml-2">
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        className="text-blue-400"
      />
    </svg>
  );
}

// Token usage bar chart
function TokenUsageChart({ history }: { history: api.HUDHistoryEntry[] }) {
  if (history.length === 0) return null;

  const maxTokens = Math.max(...history.map(h => h.tokens || 0), 1);
  const recentHistory = history.slice(-30);

  return (
    <div className="h-16 flex items-end gap-px">
      {recentHistory.map((entry, i) => {
        const height = ((entry.tokens || 0) / maxTokens) * 100;
        const hasError = !!entry.error;
        return (
          <div
            key={i}
            className={`flex-1 min-w-[3px] max-w-[12px] rounded-t transition-all ${
              hasError ? 'bg-red-500/70' : 'bg-blue-500/70'
            } hover:bg-blue-400`}
            style={{ height: `${Math.max(height, 4)}%` }}
            title={`${entry.tokens} tokens - ${new Date(entry.timestamp).toLocaleTimeString()}`}
          />
        );
      })}
    </div>
  );
}

// Structured HUD viewer with collapsible sections
function StructuredHUDViewer({ content }: { content: string }) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['sys', 'me', 'r']));

  // Try to parse as JSON first, then as TOON-like format
  const parsed = useMemo(() => {
    if (!content) return null;

    // Try JSON parse
    try {
      return JSON.parse(content);
    } catch {
      // Not JSON, try to extract structure from TOON format
      return null;
    }
  }, [content]);

  const toggleSection = (key: string) => {
    setExpandedSections(prev => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const renderValue = (value: unknown, path: string, depth: number = 0): JSX.Element => {
    const indent = depth * 16;

    if (value === null || value === undefined) {
      return <span className="text-gray-500">null</span>;
    }

    if (typeof value === 'boolean') {
      return <span className="text-yellow-400">{value ? 'true' : 'false'}</span>;
    }

    if (typeof value === 'number') {
      return <span className="text-blue-400">{value}</span>;
    }

    if (typeof value === 'string') {
      // Check if it's a long string
      if (value.length > 100) {
        return (
          <span className="text-green-400">
            "{value.slice(0, 100)}..."
            <span className="text-gray-500 text-xs ml-1">({value.length} chars)</span>
          </span>
        );
      }
      return <span className="text-green-400">"{value}"</span>;
    }

    if (Array.isArray(value)) {
      if (value.length === 0) {
        return <span className="text-gray-500">[]</span>;
      }

      const isExpanded = expandedSections.has(path);
      return (
        <div>
          <button
            onClick={() => toggleSection(path)}
            className="text-gray-400 hover:text-white"
          >
            {isExpanded ? '▼' : '▶'}
            <span className="text-purple-400 ml-1">Array({value.length})</span>
          </button>
          {isExpanded && (
            <div style={{ marginLeft: indent + 16 }}>
              {value.map((item, i) => (
                <div key={i} className="border-l border-gray-700 pl-2 my-1">
                  <span className="text-gray-500 text-xs">[{i}]</span>{' '}
                  {renderValue(item, `${path}[${i}]`, depth + 1)}
                </div>
              ))}
            </div>
          )}
        </div>
      );
    }

    if (typeof value === 'object') {
      const entries = Object.entries(value);
      if (entries.length === 0) {
        return <span className="text-gray-500">{'{}'}</span>;
      }

      const isExpanded = expandedSections.has(path);

      // Section labels for known HUD sections
      const sectionLabels: Record<string, string> = {
        sys: '🔧 System',
        me: '👤 Self',
        m: '📋 Meta',
        r: '🚪 Rooms',
        system: '🔧 System',
        self: '👤 Self',
        meta: '📋 Meta',
        rooms: '🚪 Rooms',
      };

      const pathKey = path.split('.').pop() || path;
      const label = sectionLabels[pathKey] || pathKey;

      return (
        <div>
          <button
            onClick={() => toggleSection(path)}
            className="text-gray-400 hover:text-white flex items-center gap-1"
          >
            {isExpanded ? '▼' : '▶'}
            <span className="text-purple-400">{label}</span>
            <span className="text-gray-600 text-xs">({entries.length} keys)</span>
          </button>
          {isExpanded && (
            <div className="ml-4 border-l border-gray-700/50 pl-2">
              {entries.map(([key, val]) => (
                <div key={key} className="my-1">
                  <span className="text-cyan-400">{key}</span>
                  <span className="text-gray-500">: </span>
                  {renderValue(val, `${path}.${key}`, depth + 1)}
                </div>
              ))}
            </div>
          )}
        </div>
      );
    }

    return <span>{String(value)}</span>;
  };

  if (!parsed) {
    // Fall back to syntax-highlighted raw view for non-JSON content
    return <RawContentViewer content={content} />;
  }

  return (
    <div className="font-mono text-sm">
      {renderValue(parsed, 'root', 0)}
    </div>
  );
}

// Syntax-highlighted raw content viewer
function RawContentViewer({ content }: { content: string }) {
  // Apply basic syntax highlighting
  const highlighted = useMemo(() => {
    if (!content) return '';

    return content
      // Highlight section headers (e.g., "hud{...}:")
      .replace(/^(\w+)\{([^}]+)\}:/gm, '<span class="text-purple-400">$1</span>{<span class="text-cyan-400">$2</span>}:')
      // Highlight array schemas (e.g., "messages[3]{...}:")
      .replace(/(\w+)\[(\d+)\]\{([^}]+)\}:/g, '<span class="text-purple-400">$1</span>[<span class="text-blue-400">$2</span>]{<span class="text-cyan-400">$3</span>}:')
      // Highlight strings in quotes
      .replace(/"([^"]+)"/g, '<span class="text-green-400">"$1"</span>')
      // Highlight numbers
      .replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="text-blue-400">$1</span>')
      // Highlight booleans
      .replace(/\b(true|false|null)\b/g, '<span class="text-yellow-400">$1</span>');
  }, [content]);

  return (
    <pre
      className="text-sm text-gray-300 whitespace-pre-wrap font-mono"
      dangerouslySetInnerHTML={{ __html: highlighted || '(no content)' }}
    />
  );
}

// Diff viewer comparing two entries
function DiffViewer({ current, previous }: { current: string; previous: string | null }) {
  if (!previous) {
    return (
      <div className="text-gray-500 text-center py-8">
        No previous entry to compare
      </div>
    );
  }

  // Simple line-by-line diff
  const currentLines = current.split('\n');
  const previousLines = previous.split('\n');

  // Find changed lines
  const maxLines = Math.max(currentLines.length, previousLines.length);
  const diffLines: { type: 'same' | 'added' | 'removed' | 'changed'; current?: string; previous?: string }[] = [];

  for (let i = 0; i < maxLines; i++) {
    const curr = currentLines[i];
    const prev = previousLines[i];

    if (curr === prev) {
      diffLines.push({ type: 'same', current: curr });
    } else if (curr && !prev) {
      diffLines.push({ type: 'added', current: curr });
    } else if (!curr && prev) {
      diffLines.push({ type: 'removed', previous: prev });
    } else {
      diffLines.push({ type: 'changed', current: curr, previous: prev });
    }
  }

  // Count changes
  const changes = diffLines.filter(l => l.type !== 'same').length;

  return (
    <div className="font-mono text-sm">
      <div className="mb-3 text-xs text-gray-400">
        {changes} line{changes !== 1 ? 's' : ''} changed
      </div>
      <div className="space-y-0.5">
        {diffLines.map((line, i) => {
          if (line.type === 'same') {
            return (
              <div key={i} className="text-gray-500 pl-4">
                {line.current || ' '}
              </div>
            );
          }
          if (line.type === 'added') {
            return (
              <div key={i} className="bg-green-900/30 text-green-300 pl-4 border-l-2 border-green-500">
                + {line.current}
              </div>
            );
          }
          if (line.type === 'removed') {
            return (
              <div key={i} className="bg-red-900/30 text-red-300 pl-4 border-l-2 border-red-500">
                - {line.previous}
              </div>
            );
          }
          // Changed
          return (
            <div key={i}>
              <div className="bg-red-900/30 text-red-300 pl-4 border-l-2 border-red-500">
                - {line.previous}
              </div>
              <div className="bg-green-900/30 text-green-300 pl-4 border-l-2 border-green-500">
                + {line.current}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function HUDHistoryModal({ isOpen, onClose, agent }: HUDHistoryModalProps) {
  const [history, setHistory] = useState<api.HUDHistoryEntry[]>([]);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>('structured');
  const [searchQuery, setSearchQuery] = useState('');
  const listRef = useRef<HTMLDivElement>(null);

  const selectedEntry = selectedIndex !== null ? history[selectedIndex] : null;
  const previousEntry = selectedIndex !== null && selectedIndex < history.length - 1
    ? history[selectedIndex + 1]
    : null;

  // Fetch history when modal opens or agent changes
  useEffect(() => {
    if (isOpen && agent) {
      fetchHistory();
    }
  }, [isOpen, agent]);

  const fetchHistory = async () => {
    if (!agent) return;
    setLoading(true);
    try {
      const data = await api.getHUDHistory(agent.id, 100);
      setHistory(data);
      setSelectedIndex(null);
    } catch (err) {
      console.error('Failed to fetch HUD history:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleClearHistory = async () => {
    if (!agent) return;
    if (!confirm('Clear all HUD history for this agent?')) return;

    try {
      await api.clearHUDHistory(agent.id);
      setHistory([]);
      setSelectedIndex(null);
    } catch (err) {
      console.error('Failed to clear HUD history:', err);
    }
  };

  // Filtered history based on search
  const filteredHistory = useMemo(() => {
    if (!searchQuery) return history;
    const query = searchQuery.toLowerCase();
    return history.filter(entry =>
      entry.response?.toLowerCase().includes(query) ||
      entry.hud?.toLowerCase().includes(query) ||
      entry.error?.toLowerCase().includes(query)
    );
  }, [history, searchQuery]);

  // Calculate statistics
  const stats = useMemo(() => {
    if (history.length === 0) return null;
    const tokens = history.map(h => h.tokens || 0);
    const errors = history.filter(h => h.error).length;
    return {
      total: history.length,
      totalTokens: tokens.reduce((a, b) => a + b, 0),
      avgTokens: Math.round(tokens.reduce((a, b) => a + b, 0) / tokens.length),
      maxTokens: Math.max(...tokens),
      minTokens: Math.min(...tokens),
      errors,
      successRate: Math.round(((history.length - errors) / history.length) * 100),
    };
  }, [history]);

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

  const formatTokens = (tokens: number) => {
    if (tokens >= 1000) {
      return `${(tokens / 1000).toFixed(1)}k`;
    }
    return tokens.toString();
  };

  if (!isOpen) return null;

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
              <h2 className="text-lg font-semibold">HUD History</h2>
              {agent && <p className="text-sm text-gray-400">{agent.name} (ID: {agent.id})</p>}
            </div>
            {stats && (
              <div className="flex items-center gap-4 text-xs text-gray-400 border-l border-gray-700 pl-4">
                <span>{stats.total} entries</span>
                <span>{formatTokens(stats.totalTokens)} total tokens</span>
                <span className={stats.successRate < 90 ? 'text-yellow-400' : 'text-green-400'}>
                  {stats.successRate}% success
                </span>
              </div>
            )}
          </div>
          <div className="flex items-center gap-2">
            <input
              type="text"
              placeholder="Search..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="bg-gray-700 border border-gray-600 rounded px-2 py-1 text-sm w-32 focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={fetchHistory}
              className="text-gray-400 hover:text-white transition-colors px-2"
              title="Refresh"
            >
              ↻
            </button>
            <button
              onClick={handleClearHistory}
              className="text-red-400 hover:text-red-300 transition-colors text-sm px-2"
            >
              Clear
            </button>
            <button
              onClick={onClose}
              className="text-gray-400 hover:text-white transition-colors ml-2"
            >
              ✕
            </button>
          </div>
        </div>

        {/* Token Chart */}
        {history.length > 0 && (
          <div className="px-4 py-3 border-b border-gray-700/50 bg-gray-800/50">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-500">Token Usage (last 30 interactions)</span>
              {stats && (
                <span className="text-xs text-gray-500">
                  avg: {formatTokens(stats.avgTokens)} | max: {formatTokens(stats.maxTokens)}
                </span>
              )}
            </div>
            <TokenUsageChart history={history} />
          </div>
        )}

        {/* Content */}
        <div className="flex-1 flex min-h-0">
          {!agent ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              Select an agent to view HUD history
            </div>
          ) : loading ? (
            <div className="flex-1 flex items-center justify-center text-gray-400">
              Loading...
            </div>
          ) : filteredHistory.length === 0 ? (
            <div className="flex-1 flex items-center justify-center text-gray-500">
              {searchQuery ? 'No matching entries' : 'No HUD history available'}
            </div>
          ) : (
            <>
              {/* Entry List */}
              <div
                ref={listRef}
                className="w-80 border-r border-gray-700 overflow-y-auto flex-shrink-0"
              >
                {filteredHistory.map((entry, index) => {
                  const originalIndex = history.indexOf(entry);
                  const isSelected = selectedIndex === originalIndex;

                  return (
                    <button
                      key={index}
                      onClick={() => setSelectedIndex(originalIndex)}
                      className={`w-full text-left p-3 border-b border-gray-700/50 hover:bg-gray-700/50 transition-colors ${
                        isSelected ? 'bg-gray-700' : ''
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs text-gray-400">
                          {formatRelativeTime(entry.timestamp)}
                        </span>
                        <TokenSparkline
                          data={history.slice(Math.max(0, originalIndex - 5), originalIndex + 1).map(h => h.tokens || 0)}
                          maxTokens={stats?.maxTokens || 1000}
                        />
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <span className={`text-xs px-1.5 py-0.5 rounded ${
                          entry.error ? 'bg-red-900/50 text-red-300' : 'bg-green-900/50 text-green-300'
                        }`}>
                          {entry.error ? 'ERR' : 'OK'}
                        </span>
                        <span className="text-xs text-gray-500">
                          {formatTokens(entry.tokens || 0)} tok
                        </span>
                        {entry.hud_tokens && (
                          <span className="text-xs text-gray-600">
                            ({formatTokens(entry.hud_tokens)} HUD)
                          </span>
                        )}
                      </div>
                      <div className="text-sm text-gray-300 mt-1 truncate">
                        {entry.response?.slice(0, 60) || '(no response)'}
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Detail View */}
              <div className="flex-1 flex flex-col min-h-0 overflow-hidden">
                {selectedEntry ? (
                  <>
                    {/* Entry Header */}
                    <div className="p-4 border-b border-gray-700 flex-shrink-0 bg-gray-800/50">
                      <div className="flex items-center justify-between">
                        <div>
                          <span className="text-sm text-gray-300">
                            {formatTimestamp(selectedEntry.timestamp)}
                          </span>
                          <span className="text-xs text-gray-500 ml-2">
                            ({formatRelativeTime(selectedEntry.timestamp)})
                          </span>
                        </div>
                        <div className="flex items-center gap-3">
                          {selectedEntry.hud_tokens && (
                            <div className="text-xs">
                              <span className="text-gray-500">HUD:</span>
                              <span className="text-blue-400 ml-1">{formatTokens(selectedEntry.hud_tokens)}</span>
                            </div>
                          )}
                          <div className="text-xs">
                            <span className="text-gray-500">Total:</span>
                            <span className="text-blue-400 ml-1">{formatTokens(selectedEntry.tokens || 0)}</span>
                          </div>
                        </div>
                      </div>
                      {selectedEntry.error && (
                        <div className="mt-2 p-2 bg-red-900/30 rounded text-sm text-red-300">
                          {selectedEntry.error}
                        </div>
                      )}
                    </div>

                    {/* View Mode Tabs */}
                    <div className="flex border-b border-gray-700 flex-shrink-0 bg-gray-800/30">
                      <button
                        onClick={() => setViewMode('structured')}
                        className={`px-4 py-2 text-sm flex items-center gap-1 ${
                          viewMode === 'structured'
                            ? 'text-blue-400 border-b-2 border-blue-400'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        🌳 Structured
                      </button>
                      <button
                        onClick={() => setViewMode('raw')}
                        className={`px-4 py-2 text-sm flex items-center gap-1 ${
                          viewMode === 'raw'
                            ? 'text-blue-400 border-b-2 border-blue-400'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        📄 Raw HUD
                      </button>
                      <button
                        onClick={() => setViewMode('response')}
                        className={`px-4 py-2 text-sm flex items-center gap-1 ${
                          viewMode === 'response'
                            ? 'text-blue-400 border-b-2 border-blue-400'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        💬 Response
                      </button>
                      <button
                        onClick={() => setViewMode('diff')}
                        className={`px-4 py-2 text-sm flex items-center gap-1 ${
                          viewMode === 'diff'
                            ? 'text-blue-400 border-b-2 border-blue-400'
                            : 'text-gray-400 hover:text-white'
                        }`}
                      >
                        ⟷ Diff
                        {previousEntry && <span className="text-xs text-gray-500">(vs prev)</span>}
                      </button>
                    </div>

                    {/* Content */}
                    <div className="flex-1 overflow-auto p-4">
                      {viewMode === 'structured' && (
                        <StructuredHUDViewer content={selectedEntry.hud || ''} />
                      )}
                      {viewMode === 'raw' && (
                        <RawContentViewer content={selectedEntry.hud || '(no HUD content)'} />
                      )}
                      {viewMode === 'response' && (
                        <pre className="text-sm text-gray-300 whitespace-pre-wrap font-mono">
                          {selectedEntry.response || '(no response)'}
                        </pre>
                      )}
                      {viewMode === 'diff' && (
                        <DiffViewer
                          current={selectedEntry.hud || ''}
                          previous={previousEntry?.hud || null}
                        />
                      )}
                    </div>
                  </>
                ) : (
                  <div className="flex-1 flex items-center justify-center text-gray-500">
                    <div className="text-center">
                      <div className="text-4xl mb-2">📜</div>
                      <div>Select an entry to view details</div>
                      <div className="text-xs text-gray-600 mt-1">
                        Click any entry on the left
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
            {filteredHistory.length} of {history.length} entries
            {searchQuery && <span className="ml-2">matching "{searchQuery}"</span>}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setSelectedIndex(prev =>
                prev !== null && prev > 0 ? prev - 1 : prev
              )}
              disabled={selectedIndex === null || selectedIndex === 0}
              className="text-gray-400 hover:text-white disabled:text-gray-600 px-2"
              title="Newer entry"
            >
              ← Newer
            </button>
            <button
              onClick={() => setSelectedIndex(prev =>
                prev !== null && prev < history.length - 1 ? prev + 1 : prev
              )}
              disabled={selectedIndex === null || selectedIndex === history.length - 1}
              className="text-gray-400 hover:text-white disabled:text-gray-600 px-2"
              title="Older entry"
            >
              Older →
            </button>
            <button
              onClick={onClose}
              className="bg-gray-700 hover:bg-gray-600 text-white px-4 py-2 rounded text-sm transition-colors ml-4"
            >
              Close
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
