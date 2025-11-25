#!/usr/bin/env python3
"""Test suite for HUDService - Context window building and response parsing.

Run with: python -m pytest tests/test_hud_service.py -v
Or standalone: python tests/test_hud_service.py
"""

import sys
import os
import json
import unittest
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.hud_service import HUDService
from models import AIAgent, ChatMessage, ChatRoom, RoomMembership, SelfConcept
from models.ai_agent import HUD_FORMAT_JSON, HUD_FORMAT_COMPACT, HUD_FORMAT_TOON
import config


class TestHUDServiceBasics(unittest.TestCase):
    """Basic tests for HUD service initialization and utilities."""

    def setUp(self):
        self.hud = HUDService()

    def test_initialization(self):
        """Test HUD service initializes correctly."""
        self.assertIsNotNone(self.hud)

    def test_estimate_tokens_empty(self):
        """Test token estimation for empty string."""
        self.assertEqual(self.hud.estimate_tokens(""), 0)

    def test_estimate_tokens_simple(self):
        """Test token estimation for simple text."""
        # ~4 chars per token
        text = "Hello world"  # 11 chars
        tokens = self.hud.estimate_tokens(text)
        self.assertGreater(tokens, 0)
        self.assertLess(tokens, 10)

    def test_estimate_json_tokens(self):
        """Test token estimation for JSON objects."""
        obj = {"name": "Alice", "age": 25}
        tokens = self.hud.estimate_json_tokens(obj)
        self.assertGreater(tokens, 0)


class TestSystemDirectives(unittest.TestCase):
    """Tests for system directives building."""

    def setUp(self):
        self.hud = HUDService()

    def test_build_system_directives(self):
        """Test building system directives."""
        directives = self.hud.build_system_directives()
        self.assertIsInstance(directives, str)
        self.assertGreater(len(directives), 100)

    def test_directives_contain_key_sections(self):
        """Test directives contain key behavioral guidelines."""
        directives = self.hud.build_system_directives()
        self.assertIn("Collaboration", directives)
        self.assertIn("Communication", directives)


class TestMetaInstructions(unittest.TestCase):
    """Tests for meta instructions building."""

    def setUp(self):
        self.hud = HUDService()

    def test_build_persona_instructions(self):
        """Test building instructions for persona agents."""
        instructions = self.hud.build_meta_instructions("persona")
        self.assertIsInstance(instructions, str)
        self.assertGreater(len(instructions), 50)

    def test_build_bot_instructions(self):
        """Test building instructions for bot agents."""
        instructions = self.hud.build_meta_instructions("bot")
        self.assertIsInstance(instructions, str)


class TestAvailableActions(unittest.TestCase):
    """Tests for available actions building."""

    def setUp(self):
        self.hud = HUDService()

    def test_build_basic_actions(self):
        """Test building basic available actions."""
        actions = self.hud.build_available_actions("persona", can_create_agents=False)
        self.assertIsInstance(actions, dict)

        # Should have core action categories
        self.assertIn("knowledge_management", actions)
        self.assertIn("social_interactions", actions)
        self.assertIn("messaging", actions)

    def test_agent_management_requires_permission(self):
        """Test agent management actions require permission."""
        # Without permission
        actions_no_perm = self.hud.build_available_actions("persona", can_create_agents=False)
        self.assertNotIn("agent_management", actions_no_perm)

        # With permission
        actions_with_perm = self.hud.build_available_actions("persona", can_create_agents=True)
        self.assertIn("agent_management", actions_with_perm)

    def test_actions_have_descriptions(self):
        """Test action categories have descriptions."""
        actions = self.hud.build_available_actions("persona")
        for key, value in actions.items():
            if key.startswith("_"):
                continue
            self.assertIn("_description", value)
            self.assertIn("actions", value)


class TestResponseParsing(unittest.TestCase):
    """Tests for parsing agent responses."""

    def setUp(self):
        self.hud = HUDService()

    def test_parse_empty_response(self):
        """Test parsing empty response."""
        responses, actions = self.hud.parse_response("")
        self.assertEqual(responses, [])
        self.assertEqual(actions, [])

    def test_parse_json_response(self):
        """Test parsing valid JSON response."""
        response_json = json.dumps({
            "responses": [
                {"room_id": 1, "message": "Hello!"}
            ],
            "actions": []
        })
        responses, actions = self.hud.parse_response(response_json)

        self.assertEqual(len(responses), 1)
        self.assertEqual(responses[0]["room_id"], 1)
        self.assertEqual(responses[0]["message"], "Hello!")

    def test_parse_response_with_actions(self):
        """Test parsing response with actions."""
        response_json = json.dumps({
            "responses": [],
            "actions": [
                {"type": "set", "path": "mood", "value": "happy"}
            ]
        })
        responses, actions = self.hud.parse_response(response_json)

        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0]["type"], "set")

    def test_parse_response_with_messages_key(self):
        """Test parsing response using 'messages' instead of 'responses'."""
        response_json = json.dumps({
            "messages": [
                {"room_id": 5, "content": "Hi there"}
            ],
            "actions": []
        })
        responses, actions = self.hud.parse_response(response_json)

        self.assertEqual(len(responses), 1)
        # Should normalize to "message" key
        self.assertIn("message", responses[0])

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty."""
        responses, actions = self.hud.parse_response("not valid json at all")
        self.assertEqual(responses, [])
        self.assertEqual(actions, [])

    def test_parse_json_embedded_in_text(self):
        """Test parsing JSON embedded in surrounding text."""
        response = 'Here is my response: {"responses": [{"room_id": 1, "message": "Hi"}], "actions": []}'
        responses, actions = self.hud.parse_response(response)

        self.assertEqual(len(responses), 1)

    def test_parse_multiple_rooms(self):
        """Test parsing response to multiple rooms."""
        response_json = json.dumps({
            "responses": [
                {"room_id": 1, "message": "Hello room 1"},
                {"room_id": 2, "message": "Hello room 2"},
                {"room_id": 3, "message": "Hello room 3"}
            ],
            "actions": []
        })
        responses, actions = self.hud.parse_response(response_json)

        self.assertEqual(len(responses), 3)
        room_ids = [r["room_id"] for r in responses]
        self.assertEqual(room_ids, [1, 2, 3])

    def test_parse_toon_format(self):
        """Test parsing TOON format response."""
        # This tests the TOON parsing integration
        from services.toon_service import TOONSerializer
        serializer = TOONSerializer()

        original = {
            "responses": [{"room_id": 1, "message": "TOON test"}],
            "actions": []
        }
        toon_str = serializer.serialize(original, "response")

        responses, actions = self.hud.parse_response(toon_str, HUD_FORMAT_TOON)
        self.assertEqual(len(responses), 1)


class TestActionApplication(unittest.TestCase):
    """Tests for applying actions to agent state."""

    def setUp(self):
        self.hud = HUDService()
        self.agent = AIAgent(
            id=1,
            name="TestAgent",
            self_concept_json="{}"
        )

    def test_apply_set_action(self):
        """Test applying a 'set' action."""
        actions = [
            {"type": "set", "path": "mood", "value": "happy"}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 1)
        sc = SelfConcept.from_json(self.agent.self_concept_json)
        self.assertEqual(sc.get("mood"), "happy")

    def test_apply_delete_action(self):
        """Test applying a 'delete' action."""
        self.agent.self_concept_json = json.dumps({"to_delete": "value"})
        actions = [
            {"type": "delete", "path": "to_delete"}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 1)
        sc = SelfConcept.from_json(self.agent.self_concept_json)
        self.assertIsNone(sc.get("to_delete"))

    def test_apply_append_action(self):
        """Test applying an 'append' action."""
        self.agent.self_concept_json = json.dumps({"items": ["a"]})
        actions = [
            {"type": "append", "path": "items", "value": "b"}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 1)
        sc = SelfConcept.from_json(self.agent.self_concept_json)
        self.assertEqual(sc.get("items"), ["a", "b"])

    def test_apply_set_with_weight(self):
        """Test applying 'set' action with weight."""
        actions = [
            {"type": "set", "path": "fact", "value": "important", "w": 0.9}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 1)
        sc = SelfConcept.from_json(self.agent.self_concept_json)
        fact = sc.get("fact")
        self.assertIsInstance(fact, dict)
        self.assertEqual(fact["v"], "important")
        self.assertEqual(fact["w"], 0.9)

    def test_apply_set_name_action(self):
        """Test applying 'set_name' action."""
        actions = [
            {"type": "set_name", "name": "NewName"}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 1)
        self.assertEqual(self.agent.name, "NewName")

    def test_apply_set_wpm_action(self):
        """Test applying 'set_wpm' action."""
        actions = [
            {"type": "set_wpm", "wpm": 120}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 1)
        self.assertEqual(self.agent.room_wpm, 120)

    def test_apply_sleep_action(self):
        """Test applying 'sleep' action."""
        future_time = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        actions = [
            {"type": "sleep", "until": future_time}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 1)
        self.assertIsNotNone(self.agent._pending_sleep)

    def test_apply_multiple_actions(self):
        """Test applying multiple actions at once."""
        actions = [
            {"type": "set", "path": "a", "value": 1},
            {"type": "set", "path": "b", "value": 2},
            {"type": "set", "path": "c", "value": 3}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 3)

    def test_apply_no_actions(self):
        """Test applying empty actions list."""
        applied = self.hud.apply_actions(self.agent, [])
        self.assertEqual(applied, 0)

    def test_apply_invalid_action_type(self):
        """Test handling unknown action type."""
        actions = [
            {"type": "unknown_action", "data": "test"}
        ]
        applied = self.hud.apply_actions(self.agent, actions)
        self.assertEqual(applied, 0)

    def test_apply_reaction_action(self):
        """Test applying 'react' action stores pending reaction."""
        actions = [
            {"type": "react", "message_id": 42, "reaction": "thumbs_up"}
        ]
        applied = self.hud.apply_actions(self.agent, actions)

        self.assertEqual(applied, 1)
        self.assertTrue(hasattr(self.agent, '_pending_reactions'))
        self.assertEqual(len(self.agent._pending_reactions), 1)


class TestRecentActions(unittest.TestCase):
    """Tests for recent action tracking."""

    def setUp(self):
        self.hud = HUDService()
        self.agent = AIAgent(id=1, name="Test", self_concept_json="{}")

    def test_actions_recorded(self):
        """Test that applied actions are recorded."""
        actions = [{"type": "set", "path": "test", "value": "value"}]
        self.hud.apply_actions(self.agent, actions)

        recent = self.hud.get_recent_actions(1)
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0]["type"], "set")

    def test_action_has_timestamp(self):
        """Test that recorded actions have timestamps."""
        actions = [{"type": "set", "path": "test", "value": "value"}]
        self.hud.apply_actions(self.agent, actions)

        recent = self.hud.get_recent_actions(1)
        self.assertIn("timestamp", recent[0])

    def test_max_recent_actions(self):
        """Test that recent actions are limited."""
        # Apply more than max actions
        for i in range(30):
            actions = [{"type": "set", "path": f"key{i}", "value": i}]
            self.hud.apply_actions(self.agent, actions)

        recent = self.hud.get_recent_actions(1)
        self.assertLessEqual(len(recent), 20)  # Default max is 20


class TestHUDBuilding(unittest.TestCase):
    """Tests for full HUD building."""

    def setUp(self):
        self.hud = HUDService()
        self.agent = AIAgent(
            id=5,
            name="TestBot",
            background_prompt="A helpful assistant",
            agent_type="bot",
            model="gpt-4o-mini",
            self_concept_json='{"initialized": true}'
        )

    def test_build_hud_basic(self):
        """Test building basic HUD."""
        room_data = [{
            'room': ChatRoom(id=5, name="TestRoom"),
            'membership': RoomMembership(
                agent_id=5,
                room_id=5,
                is_self_room=True,
                attention_pct=100.0
            ),
            'messages': [],
            'members': [5],
            'word_budget': 50
        }]

        hud_str, tokens = self.hud.build_hud_multi_room(self.agent, room_data)

        self.assertIsInstance(hud_str, str)
        self.assertGreater(len(hud_str), 100)
        self.assertGreater(tokens, 0)

    def test_build_hud_with_messages(self):
        """Test building HUD with room messages."""
        messages = [
            ChatMessage(id=1, room_id=5, sender_name="Alice", content="Hello"),
            ChatMessage(id=2, room_id=5, sender_name="Bob", content="Hi there")
        ]

        room_data = [{
            'room': ChatRoom(id=5, name="TestRoom"),
            'membership': RoomMembership(agent_id=5, room_id=5, attention_pct=100.0),
            'messages': messages,
            'members': [5, 6],
            'word_budget': 50
        }]

        hud_str, tokens = self.hud.build_hud_multi_room(self.agent, room_data)

        # HUD should contain the messages
        self.assertIn("Hello", hud_str)
        self.assertIn("Hi there", hud_str)

    def test_build_hud_multiple_rooms(self):
        """Test building HUD with multiple rooms."""
        room_data = [
            {
                'room': ChatRoom(id=5, name="Room1"),
                'membership': RoomMembership(agent_id=5, room_id=5, attention_pct=50.0),
                'messages': [],
                'members': [5],
                'word_budget': 50
            },
            {
                'room': ChatRoom(id=10, name="Room2"),
                'membership': RoomMembership(agent_id=5, room_id=10, attention_pct=50.0),
                'messages': [],
                'members': [5, 10],
                'word_budget': 50
            }
        ]

        hud_str, tokens = self.hud.build_hud_multi_room(self.agent, room_data)

        # Parse and verify both rooms present
        hud = json.loads(hud_str)
        self.assertEqual(len(hud["rooms"]), 2)

    def test_hud_contains_agent_identity(self):
        """Test HUD contains agent identity section."""
        room_data = [{
            'room': ChatRoom(id=5, name="TestRoom"),
            'membership': RoomMembership(agent_id=5, room_id=5, attention_pct=100.0),
            'messages': [],
            'members': [5],
            'word_budget': 50
        }]

        hud_str, _ = self.hud.build_hud_multi_room(self.agent, room_data)
        hud = json.loads(hud_str)

        self.assertIn("self", hud)
        self.assertIn("identity", hud["self"])
        self.assertEqual(hud["self"]["identity"]["id"], 5)

    def test_hud_format_selection(self):
        """Test HUD respects format selection."""
        self.agent.hud_input_format = HUD_FORMAT_COMPACT

        room_data = [{
            'room': ChatRoom(id=5, name="TestRoom"),
            'membership': RoomMembership(agent_id=5, room_id=5, attention_pct=100.0),
            'messages': [],
            'members': [5],
            'word_budget': 50
        }]

        hud_str, _ = self.hud.build_hud_multi_room(self.agent, room_data)

        # Compact format uses short keys
        self.assertIn("sys", hud_str)  # "system" -> "sys"


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestHUDServiceBasics))
    suite.addTests(loader.loadTestsFromTestCase(TestSystemDirectives))
    suite.addTests(loader.loadTestsFromTestCase(TestMetaInstructions))
    suite.addTests(loader.loadTestsFromTestCase(TestAvailableActions))
    suite.addTests(loader.loadTestsFromTestCase(TestResponseParsing))
    suite.addTests(loader.loadTestsFromTestCase(TestActionApplication))
    suite.addTests(loader.loadTestsFromTestCase(TestRecentActions))
    suite.addTests(loader.loadTestsFromTestCase(TestHUDBuilding))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("HUD Service Test Suite")
    print("=" * 70)
    print()

    success = run_tests()

    print()
    print("=" * 70)
    if success:
        print("ALL TESTS PASSED")
    else:
        print("SOME TESTS FAILED - See above for details")
    print("=" * 70)

    sys.exit(0 if success else 1)
