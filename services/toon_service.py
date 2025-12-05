"""TOON (Token-Oriented Object Notation) serializer and deserializer.

TOON is a compact format designed to reduce token usage in LLM context windows.
It declares field names once at the top and uses positional values, similar to
how Protocol Buffers work but optimized for LLM readability.

Example:
    JSON:  {"name": "Alice", "age": 25, "active": true}
    TOON:  person{name,age,active}: Alice, 25, true

This module provides:
- TOONSerializer: Convert Python dicts to TOON strings
- TOONDeserializer: Convert TOON strings back to Python dicts
- Schema definitions for HUD structures
- Telemetry for comparing token usage
"""

import re
import json
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from .logging_config import get_logger

logger = get_logger("toon")


# =============================================================================
# Telemetry for Token Comparison
# =============================================================================

@dataclass
class TOONTelemetry:
    """Tracks token savings between JSON and TOON formats."""

    json_chars: int = 0
    toon_chars: int = 0
    json_estimated_tokens: int = 0
    toon_estimated_tokens: int = 0
    timestamp: str = ""

    @property
    def char_savings(self) -> int:
        return self.json_chars - self.toon_chars

    @property
    def char_savings_pct(self) -> float:
        if self.json_chars == 0:
            return 0.0
        return (self.char_savings / self.json_chars) * 100

    @property
    def token_savings(self) -> int:
        return self.json_estimated_tokens - self.toon_estimated_tokens

    @property
    def token_savings_pct(self) -> float:
        if self.json_estimated_tokens == 0:
            return 0.0
        return (self.token_savings / self.json_estimated_tokens) * 100

    def to_dict(self) -> dict:
        return {
            "json_chars": self.json_chars,
            "toon_chars": self.toon_chars,
            "json_tokens": self.json_estimated_tokens,
            "toon_tokens": self.toon_estimated_tokens,
            "char_savings": self.char_savings,
            "char_savings_pct": round(self.char_savings_pct, 1),
            "token_savings": self.token_savings,
            "token_savings_pct": round(self.token_savings_pct, 1),
            "timestamp": self.timestamp
        }


class TelemetryCollector:
    """Collects and aggregates TOON vs JSON telemetry."""

    def __init__(self, max_entries: int = 100):
        self._entries: List[TOONTelemetry] = []
        self._max_entries = max_entries

    def record(self, json_str: str, toon_str: str) -> TOONTelemetry:
        """Record a comparison between JSON and TOON representations."""
        entry = TOONTelemetry(
            json_chars=len(json_str),
            toon_chars=len(toon_str),
            json_estimated_tokens=len(json_str) // 4 + 1,
            toon_estimated_tokens=len(toon_str) // 4 + 1,
            timestamp=datetime.utcnow().isoformat()
        )

        self._entries.append(entry)
        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries:]

        logger.debug(
            f"TOON telemetry: {entry.char_savings} chars saved "
            f"({entry.char_savings_pct:.1f}%), ~{entry.token_savings} tokens"
        )

        return entry

    def get_summary(self) -> dict:
        """Get aggregate statistics."""
        if not self._entries:
            return {"entries": 0, "avg_savings_pct": 0}

        total_json = sum(e.json_chars for e in self._entries)
        total_toon = sum(e.toon_chars for e in self._entries)
        total_json_tokens = sum(e.json_estimated_tokens for e in self._entries)
        total_toon_tokens = sum(e.toon_estimated_tokens for e in self._entries)

        return {
            "entries": len(self._entries),
            "total_json_chars": total_json,
            "total_toon_chars": total_toon,
            "total_char_savings": total_json - total_toon,
            "avg_char_savings_pct": round(((total_json - total_toon) / total_json * 100) if total_json else 0, 1),
            "total_json_tokens": total_json_tokens,
            "total_toon_tokens": total_toon_tokens,
            "total_token_savings": total_json_tokens - total_toon_tokens,
            "avg_token_savings_pct": round(((total_json_tokens - total_toon_tokens) / total_json_tokens * 100) if total_json_tokens else 0, 1),
            "recent_entries": [e.to_dict() for e in self._entries[-5:]]
        }

    def get_entries(self) -> List[dict]:
        """Get all telemetry entries."""
        return [e.to_dict() for e in self._entries]


# Global telemetry collector
_telemetry = TelemetryCollector()


def get_telemetry() -> TelemetryCollector:
    """Get the global telemetry collector."""
    return _telemetry


# =============================================================================
# Compact JSON Mode (Phase 1)
# =============================================================================

# Key mappings for compact JSON - maps verbose keys to short keys
COMPACT_KEY_MAP = {
    # Top-level sections
    "system": "sys",
    "self": "me",
    "meta": "m",
    "rooms": "r",

    # System section
    "directives": "dir",

    # Self/identity section
    "identity": "id",
    "knowledge": "k",
    "memory_used": "mem",
    "recent_actions": "acts",

    # Identity fields
    "name": "n",
    "model": "mod",
    "seed": "sd",
    "role": "rl",

    # Meta section
    "instructions": "ins",
    "available_actions": "aa",

    # Room fields
    "members": "mbr",
    "attention_pct": "att",
    "time_since_last": "tsl",
    "word_budget": "wb",
    "messages": "msg",
    "is_self_room": "self",
    "billboard": "bb",
    "my_keys": "keys",
    "pending_access_requests": "par",

    # Message fields
    "timestamp": "ts",
    "sender": "s",
    "content": "c",
    "type": "t",
    "reply_to": "rt",
    "reactions": "rx",

    # Action categories
    "knowledge_management": "km",
    "social_interactions": "si",
    "messaging": "mg",
    "room_management": "rm",
    "access_control": "ac",
    "attention": "at",
    "timing": "tm",
    "agent_management": "am",
    "_description": "_d",
    "_note": "_n",
    "actions": "a",

    # Action fields
    "path": "p",
    "value": "v",
    "message_id": "mid",
    "reaction": "re",
    "room_id": "rid",
    "agent_id": "aid",
    "message": "mg",
    "request_id": "reqid",
    "background_prompt": "bp",
    "agent_type": "at",
    "in_room_id": "irid",
}

# Reverse mapping for deserialization
COMPACT_KEY_REVERSE = {v: k for k, v in COMPACT_KEY_MAP.items()}


def compact_keys(obj: Any) -> Any:
    """Recursively replace verbose keys with compact versions."""
    if isinstance(obj, dict):
        return {
            COMPACT_KEY_MAP.get(k, k): compact_keys(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [compact_keys(item) for item in obj]
    else:
        return obj


def expand_keys(obj: Any) -> Any:
    """Recursively replace compact keys with verbose versions."""
    if isinstance(obj, dict):
        return {
            COMPACT_KEY_REVERSE.get(k, k): expand_keys(v)
            for k, v in obj.items()
        }
    elif isinstance(obj, list):
        return [expand_keys(item) for item in obj]
    else:
        return obj


def to_compact_json(obj: Any, indent: Optional[int] = None) -> str:
    """Convert object to compact JSON with shortened keys."""
    compacted = compact_keys(obj)
    return json.dumps(compacted, indent=indent, ensure_ascii=False)


def from_compact_json(json_str: str) -> Any:
    """Parse compact JSON and expand keys to verbose versions."""
    obj = json.loads(json_str)
    return expand_keys(obj)


# =============================================================================
# TOON Serializer (Phase 2)
# =============================================================================

class TOONSerializer:
    """Serializes Python objects to TOON format."""

    def __init__(self):
        self._indent_level = 0
        self._indent_str = "  "

    def serialize(self, obj: Any, name: str = "root") -> str:
        """Serialize a Python object to TOON format."""
        return self._serialize_value(obj, name, top_level=True)

    def _serialize_value(self, obj: Any, name: str = "", top_level: bool = False) -> str:
        """Serialize a value based on its type."""
        if obj is None:
            return "null"
        elif isinstance(obj, bool):
            return "true" if obj else "false"
        elif isinstance(obj, (int, float)):
            return str(obj)
        elif isinstance(obj, str):
            return self._serialize_string(obj)
        elif isinstance(obj, list):
            return self._serialize_array(obj, name)
        elif isinstance(obj, dict):
            return self._serialize_object(obj, name, top_level)
        else:
            return self._serialize_string(str(obj))

    def _serialize_string(self, s: str) -> str:
        """Serialize a string, quoting only if necessary."""
        # Quote if string contains special characters or could be confused
        needs_quotes = (
            not s or  # empty string
            s in ("true", "false", "null") or  # reserved words
            s[0].isdigit() or  # starts with digit
            "," in s or "{" in s or "}" in s or "[" in s or "]" in s or
            ":" in s or "\n" in s or '"' in s
        )

        if needs_quotes:
            # Escape quotes and newlines
            escaped = s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
            return f'"{escaped}"'
        return s

    def _serialize_array(self, arr: List, name: str) -> str:
        """Serialize an array to TOON format."""
        if not arr:
            return "[]"

        # For arrays of objects with consistent structure, use schema notation
        if all(isinstance(item, dict) for item in arr) and arr:
            # Check if all items have the same keys
            first_keys = set(arr[0].keys())
            if all(set(item.keys()) == first_keys for item in arr):
                return self._serialize_uniform_array(arr, name, list(arr[0].keys()))

        # Mixed or simple array
        items = [self._serialize_value(item) for item in arr]
        if len(items) <= 5 and all(len(str(i)) < 30 for i in items):
            # Inline short arrays
            return f"[{', '.join(items)}]"
        else:
            # Multi-line for longer arrays
            self._indent_level += 1
            indent = self._indent_str * self._indent_level
            lines = [f"\n{indent}{item}" for item in items]
            self._indent_level -= 1
            return "[" + ",".join(lines) + "\n" + (self._indent_str * self._indent_level) + "]"

    def _serialize_uniform_array(self, arr: List[dict], name: str, keys: List[str]) -> str:
        """Serialize an array of uniform objects using schema notation.

        Detects nested complex values and uses expanded format if needed.
        """
        # Check if any item has complex nested values (non-empty lists or dicts)
        def has_complex_values(item: dict) -> bool:
            for v in item.values():
                if isinstance(v, list) and v:
                    return True
                if isinstance(v, dict) and v:
                    return True
            return False

        any_complex = any(has_complex_values(item) for item in arr)

        if any_complex:
            # Use expanded format for objects with complex nested values
            return self._serialize_complex_array(arr, name, keys)

        # Simple format: name[N]{key1,key2,...}:
  val1, val2, ...
  ...
        schema = ",".join(keys)
        lines = [f"{name}[{len(arr)}]{{{schema}}}:"]

        self._indent_level += 1
        indent = self._indent_str * self._indent_level

        for item in arr:
            values = [self._serialize_value(item.get(k)) for k in keys]
            lines.append(f"{indent}{', '.join(values)}")

        self._indent_level -= 1
        return "
".join(lines)

    def _serialize_complex_array(self, arr: List[dict], name: str, keys: List[str]) -> str:
        """Serialize an array where items have complex nested values.

        Each item becomes a multi-line block with nested values properly indented.
        """
        lines = [f"{name}[{len(arr)}]:"]

        self._indent_level += 1
        indent = self._indent_str * self._indent_level

        for i, item in enumerate(arr):
            # Start each item with its schema
            item_keys = list(item.keys())
            schema = ",".join(item_keys)
            lines.append(f"{indent}[{i}]{{{schema}}}:")

            self._indent_level += 1
            inner_indent = self._indent_str * self._indent_level

            for key in item_keys:
                value = item.get(key)
                if isinstance(value, (list, dict)) and value:
                    # Complex value gets its own line with name
                    serialized = self._serialize_value(value, key)
                    lines.append(f"{inner_indent}{serialized}")
                else:
                    # Simple value on its own line
                    lines.append(f"{inner_indent}{key}: {self._serialize_value(value)}")

            self._indent_level -= 1

        self._indent_level -= 1
        return "
".join(lines)

    def _serialize_object    def _serialize_object(self, obj: dict, name: str, top_level: bool = False) -> str:
        """Serialize an object to TOON format."""
        if not obj:
            return "{}"

        keys = list(obj.keys())

        # For top-level or named objects, use schema notation
        if top_level or name:
            schema = ",".join(keys)
            header = f"{name}{{{schema}}}:" if name else f"{{{schema}}}:"

            # Check if values are simple enough for inline
            simple_values = all(
                isinstance(v, (str, int, float, bool, type(None))) and
                (not isinstance(v, str) or len(v) < 50)
                for v in obj.values()
            )

            if simple_values and len(obj) <= 4:
                values = [self._serialize_value(v) for v in obj.values()]
                return f"{header} {', '.join(values)}"
            else:
                # Multi-line for complex objects
                lines = [header]
                self._indent_level += 1
                indent = self._indent_str * self._indent_level

                for key, value in obj.items():
                    if isinstance(value, (dict, list)) and value:
                        # Nested complex value
                        serialized = self._serialize_value(value, key)
                        lines.append(f"{indent}{serialized}")
                    else:
                        lines.append(f"{indent}{self._serialize_value(value)}")

                self._indent_level -= 1
                return "\n".join(lines)
        else:
            # Inline object without schema (rare case)
            items = [f"{k}:{self._serialize_value(v)}" for k, v in obj.items()]
            return "{" + ", ".join(items) + "}"


class TOONDeserializer:
    """Deserializes TOON format back to Python objects."""

    def __init__(self):
        self._pos = 0
        self._text = ""

    def deserialize(self, toon_str: str) -> Any:
        """Deserialize a TOON string to Python objects."""
        self._text = toon_str.strip()
        self._pos = 0
        return self._parse_value()

    def _parse_value(self) -> Any:
        """Parse the next value."""
        self._skip_whitespace()

        if self._pos >= len(self._text):
            return None

        char = self._text[self._pos]

        if char == '"':
            return self._parse_string()
        elif char == '[':
            return self._parse_array()
        elif char == '{':
            return self._parse_object()
        elif char.isalpha():
            # Could be true/false/null or unquoted string or schema
            return self._parse_identifier_or_schema()
        elif char.isdigit() or char == '-':
            return self._parse_number()
        else:
            return self._parse_unquoted_string()

    def _skip_whitespace(self):
        """Skip whitespace and newlines."""
        while self._pos < len(self._text) and self._text[self._pos] in " \t\n\r":
            self._pos += 1

    def _parse_string(self) -> str:
        """Parse a quoted string."""
        assert self._text[self._pos] == '"'
        self._pos += 1

        result = []
        while self._pos < len(self._text):
            char = self._text[self._pos]
            if char == '"':
                self._pos += 1
                return "".join(result)
            elif char == '\\':
                self._pos += 1
                if self._pos < len(self._text):
                    escaped = self._text[self._pos]
                    if escaped == 'n':
                        result.append('\n')
                    elif escaped == 't':
                        result.append('\t')
                    else:
                        result.append(escaped)
                    self._pos += 1
            else:
                result.append(char)
                self._pos += 1

        return "".join(result)

    def _parse_array(self) -> list:
        """Parse an array."""
        assert self._text[self._pos] == '['
        self._pos += 1

        result = []
        self._skip_whitespace()

        while self._pos < len(self._text) and self._text[self._pos] != ']':
            value = self._parse_value()
            result.append(value)

            self._skip_whitespace()
            if self._pos < len(self._text) and self._text[self._pos] == ',':
                self._pos += 1
            self._skip_whitespace()

        if self._pos < len(self._text):
            self._pos += 1  # Skip ]

        return result

    def _parse_object(self) -> dict:
        """Parse an inline object {key:value, ...}."""
        assert self._text[self._pos] == '{'
        self._pos += 1

        result = {}
        self._skip_whitespace()

        while self._pos < len(self._text) and self._text[self._pos] != '}':
            # Parse key
            key = self._parse_identifier()
            self._skip_whitespace()

            if self._pos < len(self._text) and self._text[self._pos] == ':':
                self._pos += 1
                self._skip_whitespace()
                value = self._parse_value()
                result[key] = value

            self._skip_whitespace()
            if self._pos < len(self._text) and self._text[self._pos] == ',':
                self._pos += 1
            self._skip_whitespace()

        if self._pos < len(self._text):
            self._pos += 1  # Skip }

        return result

    def _parse_identifier(self) -> str:
        """Parse an identifier (unquoted key or value)."""
        start = self._pos
        while self._pos < len(self._text) and (
            self._text[self._pos].isalnum() or self._text[self._pos] in "_.-"
        ):
            self._pos += 1
        return self._text[start:self._pos]

    def _parse_identifier_or_schema(self) -> Any:
        """Parse an identifier, which could be a keyword, unquoted string, or schema.
        
        Handles three cases:
        1. Keywords: true, false, null
        2. Schema notation: name{fields} or name[N]{fields} (no space before { or [)
        3. Unquoted strings: parsed until delimiter (comma, brace, bracket, newline)
        """
        start_pos = self._pos  # Remember start for unquoted string fallback
        word = self._parse_identifier()

        if word == "true":
            return True
        elif word == "false":
            return False
        elif word == "null":
            return None

        # Check for schema notation: name{fields}: or name[N]{fields}:
        # Schema notation requires { or [ IMMEDIATELY after identifier (no whitespace)
        if self._pos < len(self._text):
            if self._text[self._pos] == '{':
                return self._parse_schema_object(word)
            elif self._text[self._pos] == '[':
                return self._parse_schema_array(word)

        # Not a keyword or schema - parse as unquoted string until delimiter
        # Continue consuming characters until we hit a delimiter
        while self._pos < len(self._text) and self._text[self._pos] not in ",}]\n":
            self._pos += 1
        
        # Return everything from start position, trimmed
        return self._text[start_pos:self._pos].strip()

    def _parse_schema_object(self, name: str) -> dict:
        """Parse a schema-notation object: name{field1,field2}: val1, val2"""
        # Parse field list
        assert self._text[self._pos] == '{'
        self._pos += 1

        fields = []
        while self._pos < len(self._text) and self._text[self._pos] != '}':
            self._skip_whitespace()
            field = self._parse_identifier()
            if field:
                fields.append(field)
            self._skip_whitespace()
            if self._pos < len(self._text) and self._text[self._pos] == ',':
                self._pos += 1

        if self._pos < len(self._text):
            self._pos += 1  # Skip }

        self._skip_whitespace()
        if self._pos < len(self._text) and self._text[self._pos] == ':':
            self._pos += 1

        # Parse values
        result = {}
        for field in fields:
            self._skip_whitespace()
            value = self._parse_value()
            result[field] = value
            self._skip_whitespace()
            if self._pos < len(self._text) and self._text[self._pos] == ',':
                self._pos += 1

        return result

    def _parse_schema_array(self, name: str) -> list:
        """Parse a schema-notation array: name[N]{fields}: entries..."""
        # Parse size
        assert self._text[self._pos] == '['
        self._pos += 1

        size_str = ""
        while self._pos < len(self._text) and self._text[self._pos].isdigit():
            size_str += self._text[self._pos]
            self._pos += 1

        size = int(size_str) if size_str else 0

        if self._pos < len(self._text) and self._text[self._pos] == ']':
            self._pos += 1

        # Parse field schema if present
        fields = []
        self._skip_whitespace()
        if self._pos < len(self._text) and self._text[self._pos] == '{':
            self._pos += 1
            while self._pos < len(self._text) and self._text[self._pos] != '}':
                self._skip_whitespace()
                field = self._parse_identifier()
                if field:
                    fields.append(field)
                self._skip_whitespace()
                if self._pos < len(self._text) and self._text[self._pos] == ',':
                    self._pos += 1
            if self._pos < len(self._text):
                self._pos += 1  # Skip }

        self._skip_whitespace()
        if self._pos < len(self._text) and self._text[self._pos] == ':':
            self._pos += 1

        # Parse array entries
        result = []
        for _ in range(size):
            self._skip_whitespace()
            if fields:
                # Each entry is a set of values matching the schema
                entry = {}
                for i, field in enumerate(fields):
                    self._skip_whitespace()
                    value = self._parse_value()
                    entry[field] = value
                    self._skip_whitespace()
                    if self._pos < len(self._text) and self._text[self._pos] == ',':
                        self._pos += 1
                result.append(entry)
            else:
                value = self._parse_value()
                result.append(value)
                self._skip_whitespace()
                if self._pos < len(self._text) and self._text[self._pos] == ',':
                    self._pos += 1

        return result

    def _parse_number(self) -> Union[int, float]:
        """Parse a number."""
        start = self._pos
        if self._text[self._pos] == '-':
            self._pos += 1

        while self._pos < len(self._text) and self._text[self._pos].isdigit():
            self._pos += 1

        if self._pos < len(self._text) and self._text[self._pos] == '.':
            self._pos += 1
            while self._pos < len(self._text) and self._text[self._pos].isdigit():
                self._pos += 1
            return float(self._text[start:self._pos])

        return int(self._text[start:self._pos])

    def _parse_unquoted_string(self) -> str:
        """Parse an unquoted string until delimiter."""
        start = self._pos
        while self._pos < len(self._text) and self._text[self._pos] not in ",}]\n":
            self._pos += 1
        return self._text[start:self._pos].strip()


# =============================================================================
# HUD-Specific TOON Conversion
# =============================================================================

def hud_to_toon(hud_dict: dict) -> str:
    """Convert a HUD dictionary to TOON format optimized for LLM consumption."""
    serializer = TOONSerializer()
    return serializer.serialize(hud_dict, "hud")


def toon_to_hud(toon_str: str) -> dict:
    """Convert TOON string back to HUD dictionary."""
    deserializer = TOONDeserializer()
    return deserializer.deserialize(toon_str)


# =============================================================================
# Format Selection & Comparison
# =============================================================================

class HUDFormat:
    """Enumeration of HUD format options."""
    JSON = "json"           # Standard JSON with indentation
    COMPACT_JSON = "compact_json"  # JSON with short keys, no indent
    TOON = "toon"           # Full TOON format


def serialize_hud(hud_dict: dict, format: str = HUDFormat.JSON, record_telemetry: bool = True) -> str:
    """Serialize HUD to the specified format.

    Args:
        hud_dict: The HUD dictionary to serialize
        format: One of HUDFormat.JSON, HUDFormat.COMPACT_JSON, or HUDFormat.TOON
        record_telemetry: Whether to record comparison telemetry

    Returns:
        Serialized string in the requested format
    """
    # Always compute JSON for baseline comparison
    json_str = json.dumps(hud_dict, indent=2, ensure_ascii=False)

    if format == HUDFormat.JSON:
        result = json_str
    elif format == HUDFormat.COMPACT_JSON:
        result = to_compact_json(hud_dict, indent=None)
    elif format == HUDFormat.TOON:
        result = hud_to_toon(hud_dict)
    else:
        logger.warning(f"Unknown HUD format '{format}', defaulting to JSON")
        result = json_str

    # Record telemetry comparing against standard JSON
    if record_telemetry and format != HUDFormat.JSON:
        _telemetry.record(json_str, result)

    return result


def get_format_comparison(hud_dict: dict) -> dict:
    """Get a comparison of all formats for a given HUD.

    Useful for testing and analysis.
    """
    json_str = json.dumps(hud_dict, indent=2, ensure_ascii=False)
    json_no_indent = json.dumps(hud_dict, ensure_ascii=False)
    compact_str = to_compact_json(hud_dict, indent=None)
    toon_str = hud_to_toon(hud_dict)

    def estimate_tokens(s: str) -> int:
        return len(s) // 4 + 1

    return {
        "json_pretty": {
            "chars": len(json_str),
            "tokens": estimate_tokens(json_str),
            "sample": json_str[:200] + "..." if len(json_str) > 200 else json_str
        },
        "json_minified": {
            "chars": len(json_no_indent),
            "tokens": estimate_tokens(json_no_indent),
            "savings_vs_pretty": f"{((len(json_str) - len(json_no_indent)) / len(json_str) * 100):.1f}%"
        },
        "compact_json": {
            "chars": len(compact_str),
            "tokens": estimate_tokens(compact_str),
            "savings_vs_pretty": f"{((len(json_str) - len(compact_str)) / len(json_str) * 100):.1f}%",
            "sample": compact_str[:200] + "..." if len(compact_str) > 200 else compact_str
        },
        "toon": {
            "chars": len(toon_str),
            "tokens": estimate_tokens(toon_str),
            "savings_vs_pretty": f"{((len(json_str) - len(toon_str)) / len(json_str) * 100):.1f}%",
            "sample": toon_str[:200] + "..." if len(toon_str) > 200 else toon_str
        }
    }
