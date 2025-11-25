#!/usr/bin/env python3
"""Test suite for data models (AIAgent, ChatMessage, ChatRoom, RoomMembership, SelfConcept).

Run with: python -m pytest tests/test_models.py -v
Or standalone: python tests/test_models.py
"""

import sys
import os
import json
import unittest
from datetime import datetime, timedelta

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import AIAgent, ChatMessage, ChatRoom, RoomMembership, SelfConcept
from models.ai_agent import (
    HUD_FORMAT_JSON, HUD_FORMAT_COMPACT, HUD_FORMAT_TOON,
    HUD_INPUT_FORMATS, HUD_OUTPUT_FORMATS
)


class TestAIAgent(unittest.TestCase):
    """Tests for AIAgent model."""

    def test_create_default_agent(self):
        """Test creating an agent with default values."""
        agent = AIAgent()
        self.assertIsNone(agent.id)
        self.assertEqual(agent.name, "")
        self.assertEqual(agent.agent_type, "persona")
        self.assertEqual(agent.model, "gpt-4o-mini")
        self.assertEqual(agent.temperature, 0.7)
        self.assertFalse(agent.is_architect)
        self.assertEqual(agent.status, "idle")

    def test_create_persona_agent(self):
        """Test creating a persona agent with custom values."""
        agent = AIAgent(
            id=1,
            name="Alice",
            background_prompt="A friendly AI assistant",
            agent_type="persona",
            temperature=0.9
        )
        self.assertEqual(agent.id, 1)
        self.assertEqual(agent.name, "Alice")
        self.assertEqual(agent.agent_type, "persona")
        self.assertEqual(agent.temperature, 0.9)

    def test_create_bot_agent(self):
        """Test creating a bot agent."""
        agent = AIAgent(
            id=2,
            name="HelperBot",
            background_prompt="A task-oriented assistant",
            agent_type="bot"
        )
        self.assertEqual(agent.agent_type, "bot")

    def test_create_architect(self):
        """Test creating The Architect agent."""
        agent = AIAgent(
            id=0,
            name="The Architect",
            is_architect=True
        )
        self.assertTrue(agent.is_architect)

    def test_to_dict(self):
        """Test converting agent to dictionary."""
        agent = AIAgent(
            id=1,
            name="TestAgent",
            model="gpt-4o",
            temperature=0.5,
            room_wpm=100
        )
        data = agent.to_dict()

        self.assertEqual(data['id'], 1)
        self.assertEqual(data['name'], "TestAgent")
        self.assertEqual(data['model'], "gpt-4o")
        self.assertEqual(data['temperature'], 0.5)
        self.assertEqual(data['room_wpm'], 100)
        self.assertIn('created_at', data)

    def test_from_dict(self):
        """Test creating agent from dictionary."""
        data = {
            'id': 5,
            'name': 'FromDict',
            'background_prompt': 'Test prompt',
            'model': 'gpt-4o-mini',
            'temperature': 0.8,
            'agent_type': 'bot',
            'can_create_agents': True
        }
        agent = AIAgent.from_dict(data)

        self.assertEqual(agent.id, 5)
        self.assertEqual(agent.name, 'FromDict')
        self.assertEqual(agent.agent_type, 'bot')
        self.assertTrue(agent.can_create_agents)

    def test_roundtrip_dict(self):
        """Test agent survives to_dict -> from_dict roundtrip."""
        original = AIAgent(
            id=10,
            name="Roundtrip",
            background_prompt="Testing roundtrip",
            model="gpt-4o",
            temperature=1.2,
            hud_input_format=HUD_FORMAT_COMPACT,
            hud_output_format=HUD_FORMAT_TOON,
            room_wpm=120
        )
        data = original.to_dict()
        restored = AIAgent.from_dict(data)

        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(restored.model, original.model)
        self.assertEqual(restored.hud_input_format, original.hud_input_format)
        self.assertEqual(restored.hud_output_format, original.hud_output_format)

    def test_hud_format_constants(self):
        """Test HUD format constants are valid."""
        self.assertEqual(HUD_FORMAT_JSON, "json")
        self.assertEqual(HUD_FORMAT_COMPACT, "compact_json")
        self.assertEqual(HUD_FORMAT_TOON, "toon")
        self.assertIn(HUD_FORMAT_JSON, HUD_INPUT_FORMATS)
        self.assertIn(HUD_FORMAT_JSON, HUD_OUTPUT_FORMATS)

    def test_sleep_state(self):
        """Test agent sleep state handling."""
        sleep_time = datetime.utcnow() + timedelta(hours=1)
        agent = AIAgent(
            id=1,
            name="Sleepy",
            sleep_until=sleep_time
        )
        self.assertIsNotNone(agent.sleep_until)

        # Test roundtrip with sleep_until
        data = agent.to_dict()
        restored = AIAgent.from_dict(data)
        self.assertIsNotNone(restored.sleep_until)

    def test_migration_from_old_hud_format(self):
        """Test migration from old single hud_format field."""
        data = {
            'id': 1,
            'name': 'OldFormat',
            'hud_format': 'compact_json'  # Old field name
        }
        agent = AIAgent.from_dict(data)
        self.assertEqual(agent.hud_input_format, 'compact_json')


class TestChatMessage(unittest.TestCase):
    """Tests for ChatMessage model."""

    def test_create_default_message(self):
        """Test creating a message with default values."""
        msg = ChatMessage()
        self.assertIsNone(msg.id)
        self.assertEqual(msg.room_id, 0)
        self.assertEqual(msg.message_type, "text")

    def test_create_text_message(self):
        """Test creating a text message."""
        msg = ChatMessage(
            id=1,
            room_id=5,
            sender_name="Alice",
            content="Hello, world!",
            sequence_number=100
        )
        self.assertEqual(msg.room_id, 5)
        self.assertEqual(msg.sender_name, "Alice")
        self.assertEqual(msg.content, "Hello, world!")
        self.assertFalse(msg.is_system_message)
        self.assertFalse(msg.is_image)

    def test_create_system_message(self):
        """Test creating a system message."""
        msg = ChatMessage(
            room_id=1,
            sender_name="System",
            content="Alice joined the room",
            message_type="system"
        )
        self.assertTrue(msg.is_system_message)

    def test_create_image_message(self):
        """Test creating an image message."""
        msg = ChatMessage(
            room_id=1,
            sender_name="Artist",
            content="Generated image",
            message_type="image",
            image_url="https://example.com/image.png"
        )
        self.assertTrue(msg.is_image)
        self.assertEqual(msg.image_url, "https://example.com/image.png")

    def test_reply_to_message(self):
        """Test creating a reply message."""
        msg = ChatMessage(
            room_id=1,
            sender_name="Bob",
            content="I agree!",
            reply_to_id=42
        )
        self.assertEqual(msg.reply_to_id, 42)

    def test_to_dict(self):
        """Test converting message to dictionary."""
        msg = ChatMessage(
            id=10,
            room_id=5,
            sender_name="Test",
            content="Test content",
            sequence_number=50
        )
        data = msg.to_dict()

        self.assertEqual(data['id'], 10)
        self.assertEqual(data['room_id'], 5)
        self.assertEqual(data['sender_name'], "Test")
        self.assertIn('timestamp', data)

    def test_from_dict(self):
        """Test creating message from dictionary."""
        data = {
            'id': 20,
            'room_id': 3,
            'sender_name': 'FromDict',
            'content': 'Test from dict',
            'message_type': 'text',
            'reply_to_id': 15
        }
        msg = ChatMessage.from_dict(data)

        self.assertEqual(msg.id, 20)
        self.assertEqual(msg.room_id, 3)
        self.assertEqual(msg.reply_to_id, 15)

    def test_roundtrip_dict(self):
        """Test message survives to_dict -> from_dict roundtrip."""
        original = ChatMessage(
            id=100,
            room_id=10,
            sender_name="Roundtrip",
            content="Test roundtrip message",
            sequence_number=500,
            message_type="text",
            reply_to_id=99
        )
        data = original.to_dict()
        restored = ChatMessage.from_dict(data)

        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.room_id, original.room_id)
        self.assertEqual(restored.content, original.content)
        self.assertEqual(restored.reply_to_id, original.reply_to_id)

    def test_timestamp_handling(self):
        """Test timestamp serialization and deserialization."""
        now = datetime.utcnow()
        msg = ChatMessage(timestamp=now)
        data = msg.to_dict()

        # Timestamp should be ISO format string
        self.assertIsInstance(data['timestamp'], str)

        # Should restore to datetime
        restored = ChatMessage.from_dict(data)
        self.assertIsInstance(restored.timestamp, datetime)


class TestChatRoom(unittest.TestCase):
    """Tests for ChatRoom model."""

    def test_create_default_room(self):
        """Test creating a room with default values."""
        room = ChatRoom()
        self.assertIsNone(room.id)
        self.assertEqual(room.name, "")

    def test_create_named_room(self):
        """Test creating a named room."""
        room = ChatRoom(id=1, name="General")
        self.assertEqual(room.id, 1)
        self.assertEqual(room.name, "General")

    def test_to_dict(self):
        """Test converting room to dictionary."""
        room = ChatRoom(id=5, name="TestRoom")
        data = room.to_dict()

        self.assertEqual(data['id'], 5)
        self.assertEqual(data['name'], "TestRoom")
        self.assertIn('created_at', data)

    def test_from_dict(self):
        """Test creating room from dictionary."""
        data = {
            'id': 10,
            'name': 'FromDict'
        }
        room = ChatRoom.from_dict(data)

        self.assertEqual(room.id, 10)
        self.assertEqual(room.name, 'FromDict')

    def test_roundtrip_dict(self):
        """Test room survives to_dict -> from_dict roundtrip."""
        original = ChatRoom(id=20, name="Roundtrip")
        data = original.to_dict()
        restored = ChatRoom.from_dict(data)

        self.assertEqual(restored.id, original.id)
        self.assertEqual(restored.name, original.name)


class TestRoomMembership(unittest.TestCase):
    """Tests for RoomMembership model."""

    def test_create_default_membership(self):
        """Test creating a membership with default values."""
        membership = RoomMembership()
        self.assertEqual(membership.agent_id, 0)
        self.assertEqual(membership.room_id, 0)
        self.assertEqual(membership.attention_pct, 10.0)
        self.assertFalse(membership.is_dynamic)
        self.assertFalse(membership.is_self_room)

    def test_create_self_room_membership(self):
        """Test creating a self-room membership."""
        membership = RoomMembership(
            agent_id=5,
            room_id=5,  # Same as agent_id for self-room
            is_self_room=True,
            attention_pct=100.0
        )
        self.assertTrue(membership.is_self_room)
        self.assertEqual(membership.attention_pct, 100.0)

    def test_create_dynamic_membership(self):
        """Test creating a dynamic attention membership."""
        membership = RoomMembership(
            agent_id=5,
            room_id=10,
            is_dynamic=True
        )
        self.assertTrue(membership.is_dynamic)

    def test_to_dict(self):
        """Test converting membership to dictionary."""
        membership = RoomMembership(
            id=1,
            agent_id=5,
            room_id=10,
            attention_pct=25.0,
            status="thinking"
        )
        data = membership.to_dict()

        self.assertEqual(data['agent_id'], 5)
        self.assertEqual(data['room_id'], 10)
        self.assertEqual(data['attention_pct'], 25.0)
        self.assertEqual(data['status'], "thinking")

    def test_from_dict(self):
        """Test creating membership from dictionary."""
        data = {
            'agent_id': 7,
            'room_id': 3,
            'attention_pct': 50.0,
            'is_self_room': True,
            'last_message_id': '100'
        }
        membership = RoomMembership.from_dict(data)

        self.assertEqual(membership.agent_id, 7)
        self.assertEqual(membership.room_id, 3)
        self.assertTrue(membership.is_self_room)

    def test_roundtrip_dict(self):
        """Test membership survives to_dict -> from_dict roundtrip."""
        original = RoomMembership(
            id=50,
            agent_id=10,
            room_id=20,
            attention_pct=75.0,
            is_dynamic=True,
            last_response_word_count=150
        )
        data = original.to_dict()
        restored = RoomMembership.from_dict(data)

        self.assertEqual(restored.agent_id, original.agent_id)
        self.assertEqual(restored.room_id, original.room_id)
        self.assertEqual(restored.attention_pct, original.attention_pct)
        self.assertEqual(restored.is_dynamic, original.is_dynamic)

    def test_last_response_time_handling(self):
        """Test last_response_time serialization."""
        now = datetime.utcnow()
        membership = RoomMembership(last_response_time=now)
        data = membership.to_dict()

        restored = RoomMembership.from_dict(data)
        self.assertIsNotNone(restored.last_response_time)


class TestSelfConcept(unittest.TestCase):
    """Tests for SelfConcept model - the flexible JSON knowledge store."""

    def test_create_empty(self):
        """Test creating empty self-concept."""
        sc = SelfConcept()
        self.assertEqual(sc.to_dict(), {})

    def test_create_with_data(self):
        """Test creating self-concept with initial data."""
        data = {"name": "Alice", "role": "assistant"}
        sc = SelfConcept(data)
        self.assertEqual(sc.to_dict(), data)

    def test_get_simple_path(self):
        """Test getting value at simple path."""
        sc = SelfConcept({"name": "Alice", "age": 25})
        self.assertEqual(sc.get("name"), "Alice")
        self.assertEqual(sc.get("age"), 25)

    def test_get_nested_path(self):
        """Test getting value at nested path."""
        sc = SelfConcept({
            "people": {
                "Alice": {"trust": 0.8, "role": "friend"}
            }
        })
        self.assertEqual(sc.get("people.Alice.trust"), 0.8)
        self.assertEqual(sc.get("people.Alice.role"), "friend")

    def test_get_missing_path(self):
        """Test getting non-existent path returns None."""
        sc = SelfConcept({"a": 1})
        self.assertIsNone(sc.get("b"))
        self.assertIsNone(sc.get("a.b.c"))

    def test_get_array_index(self):
        """Test getting array element by index."""
        sc = SelfConcept({"items": ["a", "b", "c"]})
        self.assertEqual(sc.get("items.0"), "a")
        self.assertEqual(sc.get("items.2"), "c")

    def test_get_empty_path(self):
        """Test getting with empty path returns full data."""
        data = {"a": 1, "b": 2}
        sc = SelfConcept(data)
        self.assertEqual(sc.get(""), data)

    def test_set_simple_path(self):
        """Test setting value at simple path."""
        sc = SelfConcept()
        self.assertTrue(sc.set("name", "Bob"))
        self.assertEqual(sc.get("name"), "Bob")

    def test_set_nested_path_creates_intermediate(self):
        """Test setting nested path creates intermediate dicts."""
        sc = SelfConcept()
        self.assertTrue(sc.set("people.Alice.trust", 0.9))
        self.assertEqual(sc.get("people.Alice.trust"), 0.9)
        self.assertIsInstance(sc.get("people"), dict)
        self.assertIsInstance(sc.get("people.Alice"), dict)

    def test_set_overwrites_existing(self):
        """Test setting overwrites existing value."""
        sc = SelfConcept({"name": "Old"})
        sc.set("name", "New")
        self.assertEqual(sc.get("name"), "New")

    def test_delete_simple_path(self):
        """Test deleting at simple path."""
        sc = SelfConcept({"name": "Alice", "age": 25})
        self.assertTrue(sc.delete("age"))
        self.assertIsNone(sc.get("age"))
        self.assertEqual(sc.get("name"), "Alice")

    def test_delete_nested_path(self):
        """Test deleting at nested path."""
        sc = SelfConcept({
            "people": {
                "Alice": {"trust": 0.8},
                "Bob": {"trust": 0.5}
            }
        })
        self.assertTrue(sc.delete("people.Alice"))
        self.assertIsNone(sc.get("people.Alice"))
        self.assertIsNotNone(sc.get("people.Bob"))

    def test_delete_array_element(self):
        """Test deleting array element by index."""
        sc = SelfConcept({"items": ["a", "b", "c"]})
        self.assertTrue(sc.delete("items.1"))
        self.assertEqual(sc.get("items"), ["a", "c"])

    def test_delete_missing_returns_false(self):
        """Test deleting non-existent path returns False."""
        sc = SelfConcept({"a": 1})
        self.assertFalse(sc.delete("b"))

    def test_append_to_new_array(self):
        """Test appending creates new array if path doesn't exist."""
        sc = SelfConcept()
        self.assertTrue(sc.append("items", "first"))
        self.assertEqual(sc.get("items"), ["first"])

    def test_append_to_existing_array(self):
        """Test appending to existing array."""
        sc = SelfConcept({"items": ["a", "b"]})
        self.assertTrue(sc.append("items", "c"))
        self.assertEqual(sc.get("items"), ["a", "b", "c"])

    def test_append_converts_scalar_to_array(self):
        """Test appending to scalar converts it to array."""
        sc = SelfConcept({"value": "original"})
        self.assertTrue(sc.append("value", "new"))
        self.assertEqual(sc.get("value"), ["original", "new"])

    def test_to_json(self):
        """Test JSON serialization."""
        sc = SelfConcept({"name": "Test", "count": 42})
        json_str = sc.to_json()
        self.assertIsInstance(json_str, str)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["name"], "Test")

    def test_from_json(self):
        """Test JSON deserialization."""
        json_str = '{"name": "Test", "nested": {"value": 123}}'
        sc = SelfConcept.from_json(json_str)
        self.assertEqual(sc.get("name"), "Test")
        self.assertEqual(sc.get("nested.value"), 123)

    def test_from_json_empty(self):
        """Test from_json with empty string."""
        sc = SelfConcept.from_json("")
        self.assertEqual(sc.to_dict(), {})

    def test_from_json_invalid(self):
        """Test from_json with invalid JSON returns empty."""
        sc = SelfConcept.from_json("not valid json")
        self.assertEqual(sc.to_dict(), {})

    def test_migration_from_old_format_facts(self):
        """Test migration from old facts/theories format."""
        old_json = json.dumps({
            "facts": [
                {"content": "Fact 1"},
                {"content": "Fact 2"}
            ]
        })
        sc = SelfConcept.from_json(old_json)
        facts = sc.get("facts")
        self.assertIsInstance(facts, list)
        self.assertIn("Fact 1", facts)

    def test_migration_from_old_format_relationships(self):
        """Test migration from old relationships format."""
        old_json = json.dumps({
            "relationships": [
                {"with": "Alice", "notes": "Friend"}
            ]
        })
        sc = SelfConcept.from_json(old_json)
        alice = sc.get("people.Alice")
        self.assertIsNotNone(alice)
        self.assertEqual(alice.get("notes"), "Friend")

    def test_quoted_path_segments(self):
        """Test paths with quoted segments for names with dots."""
        sc = SelfConcept()
        # Set a path with a name that would normally be parsed as multiple segments
        sc.set("people.'John Doe'.trust", 0.9)
        self.assertEqual(sc.get("people.'John Doe'.trust"), 0.9)

    def test_roundtrip_json(self):
        """Test self-concept survives JSON roundtrip."""
        original = SelfConcept({
            "identity": {"name": "Test", "role": "assistant"},
            "knowledge": {"facts": ["fact1", "fact2"]},
            "settings": {"verbose": True}
        })
        json_str = original.to_json()
        restored = SelfConcept.from_json(json_str)

        self.assertEqual(restored.get("identity.name"), "Test")
        self.assertEqual(restored.get("knowledge.facts"), ["fact1", "fact2"])


class TestSelfConceptEdgeCases(unittest.TestCase):
    """Edge case tests for SelfConcept."""

    def test_set_through_non_dict_fails(self):
        """Test setting through non-dict intermediate fails gracefully."""
        sc = SelfConcept({"value": "string"})
        # Can't set value.nested because value is a string
        self.assertFalse(sc.set("value.nested", "fail"))

    def test_deeply_nested_operations(self):
        """Test operations on deeply nested paths."""
        sc = SelfConcept()
        sc.set("a.b.c.d.e.f", "deep")
        self.assertEqual(sc.get("a.b.c.d.e.f"), "deep")
        self.assertTrue(sc.delete("a.b.c.d.e.f"))
        self.assertIsNone(sc.get("a.b.c.d.e.f"))

    def test_mixed_dict_array_navigation(self):
        """Test navigating through mixed dict and array structures."""
        sc = SelfConcept({
            "projects": [
                {"name": "Project A", "tasks": ["task1", "task2"]},
                {"name": "Project B", "tasks": ["task3"]}
            ]
        })
        self.assertEqual(sc.get("projects.0.name"), "Project A")
        self.assertEqual(sc.get("projects.1.tasks.0"), "task3")

    def test_special_characters_in_values(self):
        """Test handling values with special characters."""
        sc = SelfConcept()
        sc.set("message", "Hello, world! How's it going?")
        sc.set("code", "function() { return 42; }")
        self.assertEqual(sc.get("message"), "Hello, world! How's it going?")
        self.assertEqual(sc.get("code"), "function() { return 42; }")

    def test_unicode_content(self):
        """Test handling unicode content."""
        sc = SelfConcept()
        sc.set("greeting", "Hello!")
        sc.set("name", "Test Name")
        self.assertEqual(sc.get("greeting"), "Hello!")


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestAIAgent))
    suite.addTests(loader.loadTestsFromTestCase(TestChatMessage))
    suite.addTests(loader.loadTestsFromTestCase(TestChatRoom))
    suite.addTests(loader.loadTestsFromTestCase(TestRoomMembership))
    suite.addTests(loader.loadTestsFromTestCase(TestSelfConcept))
    suite.addTests(loader.loadTestsFromTestCase(TestSelfConceptEdgeCases))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("Models Test Suite")
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
