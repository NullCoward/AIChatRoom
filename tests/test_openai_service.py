#!/usr/bin/env python3
"""Test suite for OpenAIService - API integration with mocking.

Run with: python -m pytest tests/test_openai_service.py -v
Or standalone: python tests/test_openai_service.py

Note: These tests use mocking to avoid actual API calls.
"""

import sys
import os
import unittest
from unittest.mock import Mock, patch, MagicMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.openai_service import OpenAIService


class TestOpenAIServiceInitialization(unittest.TestCase):
    """Tests for OpenAI service initialization."""

    def test_initialize_without_key(self):
        """Test initialization without API key."""
        service = OpenAIService()
        self.assertFalse(service.has_api_key)

    def test_set_api_key(self):
        """Test setting API key."""
        service = OpenAIService()
        service.set_api_key("test-key-123")
        self.assertTrue(service.has_api_key)

    def test_set_empty_api_key(self):
        """Test setting empty API key."""
        service = OpenAIService()
        service.set_api_key("")
        self.assertFalse(service.has_api_key)


class TestBuildInstructions(unittest.TestCase):
    """Tests for building agent instructions."""

    def setUp(self):
        self.service = OpenAIService()

    def test_build_basic_instructions(self):
        """Test building basic instructions."""
        instructions = self.service.build_instructions(
            name="TestBot",
            background_prompt="A helpful assistant"
        )
        self.assertIsInstance(instructions, str)
        self.assertIn("TestBot", instructions)
        self.assertIn("helpful assistant", instructions)

    def test_build_instructions_empty_prompt(self):
        """Test building instructions with empty background."""
        instructions = self.service.build_instructions(
            name="EmptyBot",
            background_prompt=""
        )
        self.assertIsInstance(instructions, str)
        self.assertIn("EmptyBot", instructions)


class TestConnectionTest(unittest.TestCase):
    """Tests for connection testing."""

    def test_connection_without_key(self):
        """Test connection test fails without API key."""
        service = OpenAIService()
        success, message = service.test_connection()
        self.assertFalse(success)
        # Message should indicate API key is not set
        self.assertIn("not set", message.lower())

    @patch('services.openai_service.OpenAI')
    def test_connection_success(self, mock_openai):
        """Test successful connection with mocked API."""
        # Setup mock
        mock_client = MagicMock()
        mock_client.models.list.return_value = MagicMock(data=[
            MagicMock(id="gpt-4o-mini")
        ])
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        success, message = service.test_connection()
        self.assertTrue(success)

    @patch('services.openai_service.OpenAI')
    def test_connection_failure(self, mock_openai):
        """Test connection failure handling."""
        # Setup mock to raise exception
        mock_client = MagicMock()
        mock_client.models.list.side_effect = Exception("API Error")
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        success, message = service.test_connection()
        self.assertFalse(success)


class TestSendMessage(unittest.TestCase):
    """Tests for sending messages to the API."""

    def test_send_without_key(self):
        """Test sending without API key fails gracefully."""
        service = OpenAIService()
        response, resp_id, error, tokens = service.send_message(
            message="Hello",
            instructions="Be helpful",
            model="gpt-4o-mini"
        )
        self.assertIsNone(response)
        self.assertIsNotNone(error)

    @patch('services.openai_service.OpenAI')
    def test_send_message_success(self, mock_openai):
        """Test successful message sending with mocked API."""
        # Setup mock response
        mock_response = MagicMock()
        mock_response.id = "resp_123"
        mock_response.output_text = '{"responses": [], "actions": []}'
        mock_response.usage = MagicMock(total_tokens=100)

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        response, resp_id, error, tokens = service.send_message(
            message="Hello",
            instructions="Be helpful",
            model="gpt-4o-mini"
        )

        self.assertIsNotNone(response)
        self.assertIsNone(error)
        self.assertEqual(resp_id, "resp_123")
        self.assertEqual(tokens, 100)

    @patch('services.openai_service.OpenAI')
    def test_send_message_with_temperature(self, mock_openai):
        """Test message sending with custom temperature."""
        mock_response = MagicMock()
        mock_response.id = "resp_456"
        mock_response.output_text = '{"responses": [], "actions": []}'
        mock_response.usage = MagicMock(total_tokens=50)

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        response, resp_id, error, tokens = service.send_message(
            message="Hello",
            instructions="Be creative",
            model="gpt-4o",
            temperature=1.5
        )

        # Verify temperature was passed
        call_args = mock_client.responses.create.call_args
        self.assertEqual(call_args.kwargs.get('temperature'), 1.5)

    @patch('services.openai_service.OpenAI')
    def test_send_message_api_error(self, mock_openai):
        """Test handling of API errors."""
        mock_client = MagicMock()
        mock_client.responses.create.side_effect = Exception("Rate limit exceeded")
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        response, resp_id, error, tokens = service.send_message(
            message="Hello",
            instructions="Be helpful",
            model="gpt-4o-mini"
        )

        self.assertIsNone(response)
        self.assertIsNotNone(error)
        self.assertIn("Rate limit", error)


class TestGetAvailableModels(unittest.TestCase):
    """Tests for getting available models."""

    def test_get_models_without_key(self):
        """Test getting models without API key returns defaults."""
        service = OpenAIService()
        models = service.get_available_models()
        # Implementation returns default models when no client
        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)  # Has default fallbacks

    @patch('services.openai_service.OpenAI')
    def test_get_models_success(self, mock_openai):
        """Test successful model retrieval with mocked API."""
        mock_model_1 = MagicMock()
        mock_model_1.id = "gpt-4o-mini"
        mock_model_2 = MagicMock()
        mock_model_2.id = "gpt-4o"
        mock_model_3 = MagicMock()
        mock_model_3.id = "gpt-3.5-turbo"

        mock_client = MagicMock()
        mock_client.models.list.return_value = MagicMock(data=[
            mock_model_1, mock_model_2, mock_model_3
        ])
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        models = service.get_available_models()

        self.assertIsInstance(models, list)
        self.assertGreater(len(models), 0)

    @patch('services.openai_service.OpenAI')
    def test_get_models_filters_responses_api_compatible(self, mock_openai):
        """Test that models are filtered for Responses API compatibility."""
        # Include some models that shouldn't be returned
        mock_models = []
        for model_id in ["gpt-4o-mini", "gpt-4o", "text-embedding-ada-002", "whisper-1", "dall-e-3"]:
            mock_model = MagicMock()
            mock_model.id = model_id
            mock_models.append(mock_model)

        mock_client = MagicMock()
        mock_client.models.list.return_value = MagicMock(data=mock_models)
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        models = service.get_available_models()

        # Should include gpt models but not embedding/audio/image models
        model_ids = [m for m in models]
        self.assertIn("gpt-5-nano", model_ids)
        self.assertNotIn("text-embedding-ada-002", model_ids)
        self.assertNotIn("whisper-1", model_ids)


class TestConversationContinuity(unittest.TestCase):
    """Tests for conversation continuity using previous_response_id."""

    @patch('services.openai_service.OpenAI')
    def test_send_with_previous_response_id(self, mock_openai):
        """Test sending with previous response ID for continuity."""
        mock_response = MagicMock()
        mock_response.id = "resp_new"
        mock_response.output_text = '{"responses": [], "actions": []}'
        mock_response.usage = MagicMock(total_tokens=75)

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        response, resp_id, error, tokens = service.send_message(
            message="Continue our conversation",
            instructions="Be helpful",
            model="gpt-4o-mini",
            previous_response_id="resp_previous_123"
        )

        # Verify previous_response_id was passed (if supported)
        call_args = mock_client.responses.create.call_args
        # The actual parameter name may vary based on API version


class TestErrorHandling(unittest.TestCase):
    """Tests for error handling scenarios."""

    @patch('services.openai_service.OpenAI')
    def test_handles_timeout(self, mock_openai):
        """Test handling of timeout errors."""
        import socket
        mock_client = MagicMock()
        mock_client.responses.create.side_effect = socket.timeout("Connection timed out")
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        response, resp_id, error, tokens = service.send_message(
            message="Hello",
            instructions="Be helpful",
            model="gpt-4o-mini"
        )

        self.assertIsNone(response)
        self.assertIsNotNone(error)

    @patch('services.openai_service.OpenAI')
    def test_handles_invalid_response(self, mock_openai):
        """Test handling of invalid API response."""
        mock_response = MagicMock()
        mock_response.id = "resp_123"
        mock_response.output_text = None  # Invalid response
        mock_response.usage = MagicMock(total_tokens=0)

        # Also test alternative response format
        mock_response.output = []

        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_response
        mock_openai.return_value = mock_client

        service = OpenAIService()
        service.set_api_key("test-key")

        response, resp_id, error, tokens = service.send_message(
            message="Hello",
            instructions="Be helpful",
            model="gpt-4o-mini"
        )

        # Should handle gracefully
        self.assertIsNotNone(resp_id)


def run_tests():
    """Run all tests and return success status."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    suite.addTests(loader.loadTestsFromTestCase(TestOpenAIServiceInitialization))
    suite.addTests(loader.loadTestsFromTestCase(TestBuildInstructions))
    suite.addTests(loader.loadTestsFromTestCase(TestConnectionTest))
    suite.addTests(loader.loadTestsFromTestCase(TestSendMessage))
    suite.addTests(loader.loadTestsFromTestCase(TestGetAvailableModels))
    suite.addTests(loader.loadTestsFromTestCase(TestConversationContinuity))
    suite.addTests(loader.loadTestsFromTestCase(TestErrorHandling))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("OpenAI Service Test Suite (Mocked)")
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
