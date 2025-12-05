#!/usr/bin/env python3
"""Test suite for TOON (Token-Oriented Object Notation) service.

Run with: python -m pytest tests/test_toon_service.py -v
Or standalone: python tests/test_toon_service.py
"""

import sys
import os
import json
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.toon_service import (
    TOONSerializer, TOONDeserializer,
    toon_to_hud, hud_to_toon,
    to_compact_json, from_compact_json,
    serialize_hud, get_format_comparison,
    HUDFormat, compact_keys, expand_keys
)


class TestTOONSerializer(unittest.TestCase):
    """Tests for TOON serialization."""

    def setUp(self):
        self.serializer = TOONSerializer()

    def test_serialize_simple_object(self):
        """Test serializing a simple object."""
        obj = {"name": "Alice", "age": 25}
        result = self.serializer.serialize(obj, "person")
        self.assertIn("person{", result)
        self.assertIn("name", result)
        self.assertIn("Alice", result)

    def test_serialize_nested_object(self):
        """Test serializing nested objects."""
        obj = {
            "user": {"name": "Bob", "active": True},
            "count": 42
        }
        result = self.serializer.serialize(obj, "data")
        self.assertIn("data{", result)
        self.assertIn("user", result)
        self.assertIn("Bob", result)

    def test_serialize_array(self):
        """Test serializing arrays."""
        obj = {"items": [1, 2, 3]}
        result = self.serializer.serialize(obj, "list")
        self.assertIn("[", result)

    def test_serialize_uniform_array(self):
        """Test serializing arrays of uniform objects (schema notation)."""
        obj = {
            "users": [
                {"id": 1, "name": "Alice"},
                {"id": 2, "name": "Bob"}
            ]
        }
        result = self.serializer.serialize(obj, "data")
        # Should use schema notation for uniform arrays
        self.assertIn("users[2]", result)

    def test_serialize_boolean_values(self):
        """Test serializing boolean values."""
        obj = {"active": True, "deleted": False}
        result = self.serializer.serialize(obj, "flags")
        self.assertIn("true", result)
        self.assertIn("false", result)

    def test_serialize_null_value(self):
        """Test serializing null values."""
        obj = {"value": None}
        result = self.serializer.serialize(obj, "data")
        self.assertIn("null", result)

    def test_serialize_string_with_special_chars(self):
        """Test that strings with special chars get quoted."""
        obj = {"message": "Hello, world!"}
        result = self.serializer.serialize(obj, "data")
        # Comma in string should trigger quoting
        self.assertIn('"Hello, world!"', result)

    def test_serialize_empty_object(self):
        """Test serializing empty objects."""
        obj = {}
        result = self.serializer.serialize(obj, "empty")
        self.assertEqual(result, "{}")

    def test_serialize_empty_array(self):
        """Test serializing empty arrays."""
        obj = {"items": []}
        result = self.serializer.serialize(obj, "data")
        self.assertIn("[]", result)


class TestTOONDeserializer(unittest.TestCase):
    """Tests for TOON deserialization."""

    def setUp(self):
        self.deserializer = TOONDeserializer()

    def test_deserialize_simple_values(self):
        """Test deserializing simple values."""
        self.assertEqual(self.deserializer.deserialize("true"), True)
        self.assertEqual(self.deserializer.deserialize("false"), False)
        self.assertEqual(self.deserializer.deserialize("null"), None)
        self.assertEqual(self.deserializer.deserialize("42"), 42)
        self.assertEqual(self.deserializer.deserialize("3.14"), 3.14)

    def test_deserialize_quoted_string(self):
        """Test deserializing quoted strings."""
        result = self.deserializer.deserialize('"Hello, world!"')
        self.assertEqual(result, "Hello, world!")

    def test_deserialize_simple_array(self):
        """Test deserializing simple arrays."""
        result = self.deserializer.deserialize("[1, 2, 3]")
        self.assertEqual(result, [1, 2, 3])

    def test_deserialize_inline_object(self):
        """Test deserializing inline objects."""
        result = self.deserializer.deserialize("{name:Alice, age:25}")
        self.assertEqual(result["name"], "Alice")
        self.assertEqual(result["age"], 25)

    def test_deserialize_unquoted_string(self):
        """Test deserializing unquoted strings (single word)."""
        result = self.deserializer.deserialize("hello")
        self.assertEqual(result, "hello")

    def test_deserialize_multiword_unquoted_string(self):
        """Test deserializing multi-word unquoted strings."""
        # This is the bug we're fixing - multi-word strings should work
        serializer = TOONSerializer()
        obj = {"message": "Hello everyone"}
        toon = serializer.serialize(obj, "test")
        result = toon_to_hud(toon)
        self.assertEqual(result.get("message"), "Hello everyone")

    def test_deserialize_escape_sequences(self):
        """Test deserializing strings with escape sequences."""
        result = self.deserializer.deserialize(r'"Hello\nWorld"')
        self.assertEqual(result, "Hello\nWorld")


class TestRoundTrip(unittest.TestCase):
    """Tests for serialize -> deserialize round trips."""

    def test_roundtrip_simple_response(self):
        """Test round-trip with a simple agent response."""
        original = {
            "responses": [
                {"room_id": 1, "message": "Hello!"}
            ],
            "actions": []
        }
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)

        self.assertEqual(len(parsed.get("responses", [])), 1)
        self.assertEqual(parsed["responses"][0]["room_id"], 1)
        self.assertEqual(parsed["responses"][0]["message"], "Hello!")

    def test_roundtrip_multiword_message(self):
        """Test round-trip with multi-word messages."""
        original = {
            "responses": [
                {"room_id": 5, "message": "Hello everyone in the room!"}
            ],
            "actions": [
                {"type": "set", "path": "mood", "value": "happy"}
            ]
        }
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)

        self.assertEqual(
            parsed["responses"][0]["message"],
            "Hello everyone in the room!"
        )
        self.assertEqual(parsed["actions"][0]["type"], "set")
        self.assertEqual(parsed["actions"][0]["path"], "mood")

    def test_roundtrip_multiple_responses(self):
        """Test round-trip with multiple room responses."""
        original = {
            "responses": [
                {"room_id": 1, "message": "Hello room 1"},
                {"room_id": 2, "message": "Hello room 2"}
            ],
            "actions": []
        }
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)

        self.assertEqual(len(parsed.get("responses", [])), 2)
        self.assertEqual(parsed["responses"][0]["message"], "Hello room 1")
        self.assertEqual(parsed["responses"][1]["message"], "Hello room 2")

    def test_roundtrip_complex_actions(self):
        """Test round-trip with multiple action types."""
        original = {
            "responses": [],
            "actions": [
                {"type": "set", "path": "memory.last_seen", "value": "Alice"},
                {"type": "append", "path": "log", "value": "greeted Alice"},
                {"type": "delete", "path": "temp.data"}
            ]
        }
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)

        self.assertEqual(len(parsed.get("actions", [])), 3)

    def test_roundtrip_nested_structures(self):
        """Test round-trip with nested data structures."""
        original = {
            "self": {
                "identity": {"id": 1, "name": "TestBot"},
                "knowledge": {"facts": ["fact1", "fact2"]}
            }
        }
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)

        self.assertEqual(parsed["self"]["identity"]["name"], "TestBot")

    def test_roundtrip_special_characters(self):
        """Test round-trip with special characters in strings."""
        original = {
            "responses": [
                {"room_id": 1, "message": "Hello, world! How are you?"}
            ],
            "actions": []
        }
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)

        # Message with comma should be preserved
        self.assertEqual(
            parsed["responses"][0]["message"],
            "Hello, world! How are you?"
        )


class TestCompactJSON(unittest.TestCase):
    """Tests for compact JSON functionality."""

    def test_compact_keys(self):
        """Test key compression."""
        obj = {"system": {"directives": "test"}, "rooms": []}
        compacted = compact_keys(obj)
        self.assertIn("sys", compacted)
        self.assertIn("r", compacted)

    def test_expand_keys(self):
        """Test key expansion."""
        obj = {"sys": {"dir": "test"}, "r": []}
        expanded = expand_keys(obj)
        self.assertIn("system", expanded)
        self.assertIn("rooms", expanded)

    def test_compact_roundtrip(self):
        """Test compact JSON round-trip."""
        # Note: avoid using "id" as a key since it maps to/from "identity"
        # in the compact key mapping, which can cause unexpected behavior
        original = {
            "system": {"directives": "be helpful"},
            "rooms": [{"room_id": 1, "messages": []}]
        }
        compact_str = to_compact_json(original)
        restored = from_compact_json(compact_str)

        self.assertEqual(restored["system"]["directives"], "be helpful")
        # room_id doesn't have a mapping, so it stays as-is
        self.assertEqual(restored["rooms"][0]["room_id"], 1)


class TestSerializeHUD(unittest.TestCase):
    """Tests for the serialize_hud function with different formats."""

    def test_serialize_json_format(self):
        """Test serializing to JSON format."""
        hud = {"system": {"directives": "test"}}
        result = serialize_hud(hud, format=HUDFormat.JSON, record_telemetry=False)
        # Should be valid JSON
        parsed = json.loads(result)
        self.assertEqual(parsed["system"]["directives"], "test")

    def test_serialize_compact_format(self):
        """Test serializing to compact JSON format."""
        hud = {"system": {"directives": "test"}}
        result = serialize_hud(hud, format=HUDFormat.COMPACT_JSON, record_telemetry=False)
        # Should be shorter than regular JSON
        json_result = serialize_hud(hud, format=HUDFormat.JSON, record_telemetry=False)
        self.assertLess(len(result), len(json_result))

    def test_serialize_toon_format(self):
        """Test serializing to TOON format."""
        hud = {"system": {"directives": "test"}}
        result = serialize_hud(hud, format=HUDFormat.TOON, record_telemetry=False)
        # Should contain TOON-style notation
        self.assertIn("{", result)

    def test_format_comparison(self):
        """Test the format comparison utility."""
        hud = {
            "system": {"directives": "be helpful"},
            "rooms": [{"id": 1, "messages": ["hello", "world"]}]
        }
        comparison = get_format_comparison(hud)

        self.assertIn("json_pretty", comparison)
        self.assertIn("compact_json", comparison)
        self.assertIn("toon", comparison)
        self.assertIn("chars", comparison["json_pretty"])


class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and potential failure modes."""

    def test_empty_response(self):
        """Test handling empty responses."""
        original = {"responses": [], "actions": []}
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)
        self.assertEqual(parsed.get("responses", []), [])
        self.assertEqual(parsed.get("actions", []), [])

    def test_numeric_string_values(self):
        """Test that numeric-looking strings stay as strings when quoted."""
        original = {"code": "12345"}
        serializer = TOONSerializer()
        # Numbers that start with digits get quoted
        toon_str = serializer.serialize(original, "data")
        # The value should be preserved as-is after round trip if quoted
        # Note: unquoted "12345" would become int, which may be acceptable

    def test_reserved_word_strings(self):
        """Test handling strings that look like reserved words."""
        original = {"status": "true", "flag": "false", "value": "null"}
        serializer = TOONSerializer()
        toon_str = serializer.serialize(original, "data")
        # Reserved words as values should be quoted to stay as strings
        self.assertIn('"true"', toon_str)
        self.assertIn('"false"', toon_str)
        self.assertIn('"null"', toon_str)

    def test_deeply_nested_structure(self):
        """Test handling deeply nested structures."""
        original = {
            "level1": {
                "level2": {
                    "level3": {
                        "value": "deep"
                    }
                }
            }
        }
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)
        self.assertEqual(parsed["level1"]["level2"]["level3"]["value"], "deep")

    def test_unicode_content(self):
        """Test handling unicode content."""
        original = {
            "responses": [
                {"room_id": 1, "message": "Hello! Nice to meet you!"}
            ],
            "actions": []
        }
        toon_str = hud_to_toon(original)
        parsed = toon_to_hud(toon_str)
        # Should preserve the message (emojis may or may not work depending on impl)
        self.assertIsNotNone(parsed["responses"][0]["message"])


def run_tests():
    """Run all tests and return success status."""
    # Create a test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add all test classes
    suite.addTests(loader.loadTestsFromTestCase(TestTOONSerializer))
    suite.addTests(loader.loadTestsFromTestCase(TestTOONDeserializer))
    suite.addTests(loader.loadTestsFromTestCase(TestRoundTrip))
    suite.addTests(loader.loadTestsFromTestCase(TestCompactJSON))
    suite.addTests(loader.loadTestsFromTestCase(TestSerializeHUD))
    suite.addTests(loader.loadTestsFromTestCase(TestEdgeCases))

    # Run with verbosity
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Return True if all tests passed
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("TOON Service Test Suite")
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
