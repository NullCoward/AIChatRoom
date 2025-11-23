"""Self-concept model - flexible JSON store for agent's knowledge."""

import json
from typing import Any, Optional


class SelfConcept:
    """
    Flexible JSON store for agent's self-managed knowledge.

    Agents can organize their knowledge however they want using dot-path operations.
    Example structure an agent might build:
    {
        "people": {
            "Smarty Jones": {"role": "analyst", "trust": 0.8}
        },
        "projects": {
            "current": "room redesign",
            "ideas": ["flexible schemas", "dot paths"]
        },
        "beliefs": {
            "collaboration": "works better with transparency"
        }
    }
    """

    def __init__(self, data: dict = None):
        """Initialize with optional data dict."""
        self._data = data if data is not None else {}

    def to_dict(self) -> dict:
        """Return the internal data dict."""
        return self._data

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self._data)

    @classmethod
    def from_json(cls, json_str: str) -> 'SelfConcept':
        """Create from JSON string."""
        if not json_str:
            return cls()
        try:
            data = json.loads(json_str)
            # Handle migration from old format
            if isinstance(data, dict):
                # Check if it's old format with facts/theories/relationships
                if 'facts' in data or 'theories' in data or 'relationships' in data:
                    # Migrate old format to new flexible format
                    new_data = {}
                    if data.get('facts'):
                        # Handle both dict and string formats
                        new_data['facts'] = [
                            f.get('content', str(f)) if isinstance(f, dict) else str(f)
                            for f in data['facts']
                        ]
                    if data.get('theories'):
                        new_data['theories'] = [
                            {
                                "content": t.get('content', str(t)) if isinstance(t, dict) else str(t),
                                "confidence": t.get('confidence', 0.5) if isinstance(t, dict) else 0.5
                            }
                            for t in data['theories']
                        ]
                    if data.get('relationships'):
                        new_data['people'] = {}
                        for r in data['relationships']:
                            if isinstance(r, dict):
                                name = r.get('with', 'unknown')
                                new_data['people'][name] = {"notes": r.get('notes', '')}
                            else:
                                new_data['people'][str(r)] = {"notes": ""}
                    return cls(new_data)
            return cls(data if isinstance(data, dict) else {})
        except json.JSONDecodeError:
            return cls()

    def _parse_path(self, path: str) -> list:
        """Parse a dot path into components, handling quoted segments."""
        if not path:
            return []

        components = []
        current = ""
        in_quotes = False
        quote_char = None

        for char in path:
            if char in ('"', "'") and not in_quotes:
                in_quotes = True
                quote_char = char
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
            elif char == '.' and not in_quotes:
                if current:
                    components.append(current)
                current = ""
            else:
                current += char

        if current:
            components.append(current)

        return components

    def get(self, path: str) -> Optional[Any]:
        """
        Get value at dot path.

        Examples:
            get("people.Smarty Jones.trust") -> 0.8
            get("projects.ideas") -> ["flexible schemas", "dot paths"]
        """
        components = self._parse_path(path)
        if not components:
            return self._data

        current = self._data
        for component in components:
            if isinstance(current, dict):
                if component not in current:
                    return None
                current = current[component]
            elif isinstance(current, list):
                try:
                    idx = int(component)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return None
                except ValueError:
                    return None
            else:
                return None

        return current

    def set(self, path: str, value: Any) -> bool:
        """
        Set value at dot path, creating intermediate dicts as needed.

        Examples:
            set("people.Smarty Jones.trust", 0.9)
            set("projects.current", "new feature")
        """
        components = self._parse_path(path)
        if not components:
            return False

        current = self._data
        for i, component in enumerate(components[:-1]):
            if component not in current:
                current[component] = {}
            elif not isinstance(current[component], dict):
                # Can't navigate through non-dict
                return False
            current = current[component]

        current[components[-1]] = value
        return True

    def delete(self, path: str) -> bool:
        """
        Delete key at dot path.

        Examples:
            delete("people.Smarty Jones")
            delete("projects.ideas.0")  # Delete first item in list
        """
        components = self._parse_path(path)
        if not components:
            return False

        current = self._data
        for component in components[:-1]:
            if isinstance(current, dict):
                if component not in current:
                    return False
                current = current[component]
            elif isinstance(current, list):
                try:
                    idx = int(component)
                    if 0 <= idx < len(current):
                        current = current[idx]
                    else:
                        return False
                except ValueError:
                    return False
            else:
                return False

        last = components[-1]
        if isinstance(current, dict):
            if last in current:
                del current[last]
                return True
        elif isinstance(current, list):
            try:
                idx = int(last)
                if 0 <= idx < len(current):
                    current.pop(idx)
                    return True
            except ValueError:
                pass

        return False

    def append(self, path: str, value: Any) -> bool:
        """
        Append value to array at dot path, creating array if needed.

        Examples:
            append("projects.ideas", "new idea")
            append("people.Smarty Jones.tags", "helpful")
        """
        existing = self.get(path)

        if existing is None:
            # Create new array
            return self.set(path, [value])
        elif isinstance(existing, list):
            existing.append(value)
            return True
        else:
            # Convert to array with existing value and new value
            return self.set(path, [existing, value])
