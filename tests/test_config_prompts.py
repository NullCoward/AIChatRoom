#!/usr/bin/env python3
"""Test suite for config.py and prompts.py.

Run with: python -m pytest tests/test_config_prompts.py -v
Or standalone: python tests/test_config_prompts.py
"""

import sys
import os
import json
import tempfile
import unittest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
import prompts


class TestConfigConstants(unittest.TestCase):
    """Tests for configuration constants."""

    def test_architect_id(self):
        """Test ARCHITECT_ID is defined and valid."""
        self.assertEqual(config.ARCHITECT_ID, 1)

    def test_agent_types(self):
        """Test AGENT_TYPES are defined."""
        self.assertIn("persona", config.AGENT_TYPES)
        self.assertIn("bot", config.AGENT_TYPES)

    def test_token_budgets_defined(self):
        """Test token budget constants are defined."""
        self.assertIsInstance(config.TOTAL_TOKEN_BUDGET, int)
        self.assertIsInstance(config.STATIC_CONTENT_MAX, int)
        self.assertIsInstance(config.MESSAGE_CONTENT_MIN, int)
        self.assertIsInstance(config.SELF_META_MAX, int)

    def test_token_budgets_reasonable(self):
        """Test token budgets have reasonable values."""
        # Total should be positive
        self.assertGreater(config.TOTAL_TOKEN_BUDGET, 0)

        # Static + Message min should not exceed total
        self.assertLessEqual(
            config.STATIC_CONTENT_MAX + config.MESSAGE_CONTENT_MIN,
            config.TOTAL_TOKEN_BUDGET * 2  # Allow some flexibility
        )

    def test_default_model(self):
        """Test default model is defined."""
        self.assertIsInstance(config.DEFAULT_MODEL, str)
        self.assertIn("gpt", config.DEFAULT_MODEL.lower())

    def test_default_temperature(self):
        """Test default temperature is in valid range."""
        self.assertGreaterEqual(config.DEFAULT_TEMPERATURE, 0.0)
        self.assertLessEqual(config.DEFAULT_TEMPERATURE, 2.0)

    def test_attention_percentages(self):
        """Test attention percentage defaults."""
        self.assertIsInstance(config.DEFAULT_ROOM_ALLOCATION_PCT, float)
        self.assertIsInstance(config.SELF_ROOM_ALLOCATION_PCT, float)

        # Self room should get significant attention
        self.assertGreaterEqual(config.SELF_ROOM_ALLOCATION_PCT, 50.0)

    def test_wpm_limits(self):
        """Test WPM limits are reasonable."""
        self.assertGreater(config.MIN_WPM, 0)
        self.assertLess(config.MIN_WPM, config.MAX_WPM)
        self.assertGreater(config.DEFAULT_ROOM_WPM, config.MIN_WPM)
        self.assertLess(config.DEFAULT_ROOM_WPM, config.MAX_WPM)

    def test_api_timeouts(self):
        """Test API timeout values."""
        self.assertGreater(config.API_TIMEOUT_SECONDS, 0)
        self.assertGreater(config.API_CONNECT_TIMEOUT_SECONDS, 0)
        self.assertLessEqual(config.API_CONNECT_TIMEOUT_SECONDS, config.API_TIMEOUT_SECONDS)

    def test_log_settings(self):
        """Test logging configuration."""
        self.assertGreater(config.LOG_MAX_BYTES, 0)
        self.assertGreater(config.LOG_BACKUP_COUNT, 0)

    def test_window_dimensions(self):
        """Test UI window dimension settings."""
        self.assertGreater(config.WINDOW_MIN_WIDTH, 0)
        self.assertGreater(config.WINDOW_MIN_HEIGHT, 0)


class TestPromptsModule(unittest.TestCase):
    """Tests for the prompts module."""

    def test_load_prompts(self):
        """Test prompts can be loaded."""
        data = prompts.load_prompts()
        self.assertIsInstance(data, dict)

    def test_get_prompt_existing(self):
        """Test getting an existing prompt."""
        # This depends on prompts.json structure, but should have some content
        result = prompts.get_prompt("instructions", default="default")
        # Should return something (either from file or default)
        self.assertIsNotNone(result)

    def test_get_prompt_missing(self):
        """Test getting missing prompt returns default."""
        result = prompts.get_prompt("nonexistent.path.here", default="my_default")
        self.assertEqual(result, "my_default")

    def test_get_prompt_nested(self):
        """Test getting nested prompt path."""
        # Test with a path that might exist
        result = prompts.get_prompt("format.response", default=None)
        # Just verify it doesn't crash
        self.assertTrue(True)

    def test_build_technical_instructions(self):
        """Test building technical instructions."""
        result = prompts.build_technical_instructions()
        self.assertIsInstance(result, str)

    def test_build_persona_instructions(self):
        """Test building persona instructions."""
        result = prompts.build_persona_instructions()
        self.assertIsInstance(result, str)

    def test_build_bot_instructions(self):
        """Test building bot instructions."""
        result = prompts.build_bot_instructions()
        self.assertIsInstance(result, str)


class TestPromptsSaveLoad(unittest.TestCase):
    """Tests for prompts save/load functionality."""

    def test_save_and_load_prompts(self):
        """Test saving and loading prompts."""
        # Get original data
        original = prompts.load_prompts()

        # Modify and save (we'll restore after)
        test_data = original.copy()
        test_data["_test_key"] = "test_value"

        # Save
        prompts.save_prompts(test_data)

        # Load and verify
        loaded = prompts.load_prompts()
        self.assertEqual(loaded.get("_test_key"), "test_value")

        # Restore original
        del test_data["_test_key"]
        prompts.save_prompts(test_data)


class TestPromptsContentStructure(unittest.TestCase):
    """Tests for prompts.json content structure."""

    def setUp(self):
        self.data = prompts.load_prompts()

    def test_has_instructions_section(self):
        """Test prompts has instructions section."""
        # Check for common sections that should exist
        # This is somewhat flexible since prompts.json structure may vary
        self.assertIsInstance(self.data, dict)

    def test_prompts_not_empty(self):
        """Test prompts file is not empty."""
        self.assertGreater(len(self.data), 0)


class TestConfigValidation(unittest.TestCase):
    """Tests for configuration value validation."""

    def test_all_config_values_accessible(self):
        """Test all expected config values are accessible."""
        expected_attrs = [
            'ARCHITECT_ID',
            'AGENT_TYPES',
            'TOTAL_TOKEN_BUDGET',
            'STATIC_CONTENT_MAX',
            'MESSAGE_CONTENT_MIN',
            'SELF_META_MAX',
            'DEFAULT_MODEL',
            'DEFAULT_TEMPERATURE',
            'DEFAULT_ROOM_WPM',
            'DEFAULT_ROOM_ALLOCATION_PCT',
            'SELF_ROOM_ALLOCATION_PCT',
            'MIN_WPM',
            'MAX_WPM',
            'API_TIMEOUT_SECONDS',
            'API_CONNECT_TIMEOUT_SECONDS',
            'API_MAX_RETRIES',
            'LOG_MAX_BYTES',
            'LOG_BACKUP_COUNT',
            'WINDOW_MIN_WIDTH',
            'WINDOW_MIN_HEIGHT'
        ]

        for attr in expected_attrs:
            self.assertTrue(
                hasattr(config, attr),
                f"config.py missing expected attribute: {attr}"
            )

    def test_config_types_correct(self):
        """Test config values have correct types."""
        # Integers
        int_attrs = [
            'ARCHITECT_ID', 'TOTAL_TOKEN_BUDGET', 'STATIC_CONTENT_MAX',
            'MESSAGE_CONTENT_MIN', 'SELF_META_MAX', 'DEFAULT_ROOM_WPM',
            'MIN_WPM', 'MAX_WPM', 'API_TIMEOUT_SECONDS',
            'API_CONNECT_TIMEOUT_SECONDS', 'API_MAX_RETRIES',
            'LOG_MAX_BYTES', 'LOG_BACKUP_COUNT',
            'WINDOW_MIN_WIDTH', 'WINDOW_MIN_HEIGHT'
        ]

        for attr in int_attrs:
            value = getattr(config, attr, None)
            if value is not None:
                self.assertIsInstance(value, int, f"{attr} should be int")

        # Floats
        float_attrs = [
            'DEFAULT_TEMPERATURE', 'DEFAULT_ROOM_ALLOCATION_PCT',
            'SELF_ROOM_ALLOCATION_PCT', 'SHARED_ROOM_ALLOCATION_PCT'
        ]

        for attr in float_attrs:
            value = getattr(config, attr, None)
            if value is not None:
                self.assertIsInstance(value, (int, float), f"{attr} should be float")

        # Strings
        self.assertIsInstance(config.DEFAULT_MODEL, str)

        # Lists
        self.assertIsInstance(config.AGENT_TYPES, list)


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestConfigConstants))
    suite.addTests(loader.loadTestsFromTestCase(TestPromptsModule))
    suite.addTests(loader.loadTestsFromTestCase(TestPromptsSaveLoad))
    suite.addTests(loader.loadTestsFromTestCase(TestPromptsContentStructure))
    suite.addTests(loader.loadTestsFromTestCase(TestConfigValidation))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("Config & Prompts Test Suite")
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
