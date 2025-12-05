# HUD OS Specification

**HUD OS** is built on a single primitive: the **Holon**.

```
Holon = {
  understanding,   // What to know
  state,          // What is (can contain other Holons)
  actions         // What can be done
}
```

A **holon** is both a whole unto itself and a part of something larger. It's a single unit of recursion.

---

## The Primitive

```python
class Holon:
    understanding: str      # Instructions/context
    state: dict            # Data (can contain other Holons)
    actions: list[Action]  # Available operations
```

---

## HUD OS = One Holon

```python
hud_os = Holon(
    understanding = """
        You receive structured data and respond with actions.
        Respond in JSON format: {"actions": [...]}
        You have memory actions to manage your knowledge.
    """,

    state = {
        "knowledge": {},           # AI's persistent memory

        "user": Holon(             # User's holon - just state!
            understanding = "You are a customer support agent...",
            state = {
                "customer": {"name": "Alice", "vip": True},
                "messages": [
                    {"role": "customer", "content": "Help!"},
                    {"role": "agent", "content": "On it!"}
                ]
            },
            actions = [
                Action("send_message", params={"message": "str"}),
                Action("escalate", params={"reason": "str"}),
            ]
        )
    },

    actions = [
        Action("memory.set", params={"path": "str", "value": "any"}),
        Action("memory.delete", params={"path": "str"}),
        Action("sleep", params={"until": "datetime"}),
    ]
)
```

---

## Serialized Output

```json
{
  "understanding": "You receive structured data and respond with actions...",

  "state": {
    "knowledge": {},

    "user": {
      "understanding": "You are a customer support agent...",
      "state": {
        "customer": {"name": "Alice", "vip": true},
        "messages": [
          {"role": "customer", "content": "Help!"},
          {"role": "agent", "content": "On it!"}
        ]
      },
      "actions": [
        {"name": "send_message", "params": {"message": "str"}},
        {"name": "escalate", "params": {"reason": "str"}}
      ]
    }
  },

  "actions": [
    {"name": "memory.set", "params": {"path": "str", "value": "any"}},
    {"name": "memory.delete", "params": {"path": "str"}},
    {"name": "sleep", "params": {"until": "datetime"}}
  ]
}
```

---

## Visual

```
┌─────────────────────────────────────────────────────────────┐
│  Holon (OS)                                                  │
│                                                              │
│  understanding: "Respond in JSON, use actions..."            │
│                                                              │
│  state: {                                                    │
│    knowledge: {...},                                         │
│                                                              │
│    user: ┌────────────────────────────────────────────────┐ │
│          │  Holon (User)                                  │ │
│          │                                                │ │
│          │  understanding: "You are a support agent..."   │ │
│          │                                                │ │
│          │  state: {                                      │ │
│          │    customer: {...},                            │ │
│          │    messages: [...]                             │ │
│          │  }                                             │ │
│          │                                                │ │
│          │  actions: [send_message, escalate, ...]        │ │
│          └────────────────────────────────────────────────┘ │
│  }                                                           │
│                                                              │
│  actions: [memory.set, memory.delete, sleep]                 │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## Implementation

```python
from dataclasses import dataclass, field
from typing import Any
import json

@dataclass
class Action:
    name: str
    params: dict[str, str] = field(default_factory=dict)
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "params": self.params,
            "description": self.description
        }

@dataclass
class Holon:
    """
    A holon is both a whole unto itself and a part of something larger.
    It's a single unit of recursion: understanding + state + actions.
    """
    understanding: str = ""
    state: dict[str, Any] = field(default_factory=dict)
    actions: list[Action] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Recursively serialize, converting nested Holons."""
        return {
            "understanding": self.understanding,
            "state": self._serialize_state(self.state),
            "actions": [a.to_dict() for a in self.actions]
        }

    def _serialize_state(self, state: dict) -> dict:
        """Recursively serialize state, handling nested Holons."""
        result = {}
        for key, value in state.items():
            if isinstance(value, Holon):
                result[key] = value.to_dict()
            elif isinstance(value, dict):
                result[key] = self._serialize_state(value)
            elif isinstance(value, list):
                result[key] = [
                    item.to_dict() if isinstance(item, Holon) else item
                    for item in value
                ]
            else:
                result[key] = value
        return result

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), **kwargs)
```

---

## Usage: AI Chat Room

```python
from hudos import Holon, Action

def build_hud(agent) -> Holon:
    """Build HUD for a chat room agent."""

    # User holon (the app's context)
    user = Holon(
        understanding = agent.background_prompt,
        state = {
            "identity": {
                "id": agent.id,
                "name": agent.name,
                "type": agent.agent_type
            },
            "rooms": build_rooms_state(agent)
        },
        actions = [
            Action("send_message", {"room_id": "int", "message": "str"}),
            Action("create_key", {"room_id": "int", "key": "str"}),
            Action("request_access", {"room_id": "int", "key": "str"}),
            Action("leave_room", {"room_id": "int"}),
        ]
    )

    # OS holon (wraps user)
    os = Holon(
        understanding = SYSTEM_INSTRUCTIONS,
        state = {
            "knowledge": agent.knowledge or {},
            "user": user
        },
        actions = [
            Action("memory.set", {"path": "str", "value": "any"}),
            Action("memory.delete", {"path": "str"}),
            Action("sleep", {"seconds": "int"}),
        ]
    )

    return os


def build_rooms_state(agent) -> dict:
    """Build rooms data for agent."""
    rooms = {}
    for membership in agent.room_memberships:
        room = membership.room
        messages = get_messages(room.id)
        rooms[room.name] = {
            "id": room.id,
            "messages": [
                {"sender": m.sender_name, "content": m.content}
                for m in messages
            ]
        }
    return rooms


# In heartbeat service
def process_heartbeat(agent):
    hud = build_hud(agent)
    prompt = hud.to_json(indent=2)

    response = call_ai(agent.model, prompt)
    actions = parse_actions(response)

    for action in actions:
        execute_action(agent, action)
```

---

## Token Budget (Runtime Concern)

Token management happens when serializing, not in the Holon structure:

```python
def to_json_with_budget(self, budget: int) -> str:
    """Serialize and fit to token budget."""
    full = self.to_dict()

    # Measure
    tokens = count_tokens(full)

    # Truncate if needed (lists in state, oldest first)
    while tokens > budget:
        full = truncate_largest_list(full)
        tokens = count_tokens(full)

    return json.dumps(full)
```

---

## Design Principles

1. **One Primitive**: Holon = {understanding, state, actions}

2. **Composition Through State**: Holons contain Holons in their state

3. **Recursive Serialization**: to_dict() handles nested Holons automatically

4. **Runtime Concerns Separate**: Token budgets, truncation happen at serialization

5. **No Special Cases**: OS and User are both just Holons

---

## Etymology

**Holon** (Greek: ὅλον, *holon* = "whole")

Coined by Arthur Koestler in *The Ghost in the Machine* (1967).

> A holon is something that is simultaneously a whole and a part.

Perfect for our primitive:
- Each Holon is complete (understanding + state + actions)
- Each Holon can be part of another Holon's state
- Single unit of recursion, infinitely composable

---

## That's It

- **Holon**: understanding + state + actions
- **HUD OS**: A Holon whose state contains knowledge + user Holon
- **User**: A Holon inside OS's state
- **Serialization**: Recursive to_dict()
- **Budget**: Handled at runtime

One primitive. Infinite composition. Holons all the way down.
